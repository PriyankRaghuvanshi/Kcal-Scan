"""
Push delivery store: logs for each push send, tickets, receipts.
JSON-backed, env-overridable path.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PUSH_DELIVERY_STORE_VERSION = "v1"
_MAX_DELIVERIES = 10000
_LOCK = threading.Lock()

STATUS_QUEUED = "queued"
STATUS_SENT = "sent"
STATUS_TICKET_ERROR = "ticket_error"
STATUS_RECEIPT_OK = "receipt_ok"
STATUS_RECEIPT_ERROR = "receipt_error"
STATUS_TOKEN_DEACTIVATED = "token_deactivated"
STATUS_DRY_RUN = "dry_run"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _store_path() -> Path:
    override = _normalize_space(os.getenv("PUSH_DELIVERY_STORE_PATH", ""))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "push_delivery_store.json"


def _empty_store() -> Dict[str, Any]:
    return {"version": PUSH_DELIVERY_STORE_VERSION, "deliveries": []}


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", PUSH_DELIVERY_STORE_VERSION)
            data.setdefault("deliveries", [])
            if isinstance(data.get("deliveries"), list):
                return data
    except Exception:
        pass
    return _empty_store()


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=True, indent=2, sort_keys=True)


def create_delivery_record(
    *,
    user_id: str,
    expo_push_token: str,
    alert_id: str,
    alert_type: str,
    place_id: str,
    place_name: str,
    best_item_name: str,
    title: str,
    body: str,
    payload_data: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Create a new delivery record with status queued."""
    delivery_id = str(uuid.uuid4())
    now = _now_iso()
    record = {
        "delivery_id": delivery_id,
        "user_id": _normalize_space(user_id),
        "expo_push_token": _normalize_space(expo_push_token),
        "alert_id": _normalize_space(alert_id),
        "alert_type": _normalize_space(alert_type),
        "place_id": _normalize_space(place_id),
        "place_name": _normalize_space(place_name),
        "best_item_name": _normalize_space(best_item_name),
        "title": _normalize_space(title),
        "body": _normalize_space(body),
        "payload_data": payload_data if isinstance(payload_data, dict) else {},
        "dry_run": bool(dry_run),
        "status": STATUS_DRY_RUN if dry_run else STATUS_QUEUED,
        "expo_ticket_id": None,
        "expo_receipt_id": None,
        "error_code": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    with _LOCK:
        store = _load_store()
        deliveries = list(store.get("deliveries") or [])
        if not isinstance(deliveries, list):
            deliveries = []
        deliveries.append(record)
        if len(deliveries) > _MAX_DELIVERIES:
            deliveries = deliveries[-_MAX_DELIVERIES:]
        store["deliveries"] = deliveries
        store["version"] = PUSH_DELIVERY_STORE_VERSION
        _save_store(store)
    return dict(record)


def update_delivery_status(
    delivery_id: str,
    *,
    status: str,
    expo_ticket_id: Optional[str] = None,
    expo_receipt_id: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update a delivery record by delivery_id."""
    with _LOCK:
        store = _load_store()
        deliveries = list(store.get("deliveries") or [])
        for i, d in enumerate(deliveries):
            if not isinstance(d, dict):
                continue
            if _normalize_space(d.get("delivery_id")) == _normalize_space(delivery_id):
                updates = {"status": status, "updated_at": _now_iso()}
                if expo_ticket_id is not None:
                    updates["expo_ticket_id"] = expo_ticket_id
                if expo_receipt_id is not None:
                    updates["expo_receipt_id"] = expo_receipt_id
                if error_code is not None:
                    updates["error_code"] = error_code
                if error_message is not None:
                    updates["error_message"] = error_message
                d.update(updates)
                store["deliveries"] = deliveries
                _save_store(store)
                return dict(d)
    return None


def get_delivery_by_ticket_id(ticket_id: str) -> Optional[Dict[str, Any]]:
    """Find delivery by expo_ticket_id."""
    with _LOCK:
        store = _load_store()
    deliveries = store.get("deliveries") or []
    tid = _normalize_space(ticket_id)
    for d in deliveries:
        if not isinstance(d, dict):
            continue
        if _normalize_space(d.get("expo_ticket_id")) == tid:
            return dict(d)
    return None


def list_pending_receipt_ids(limit: int = 100) -> List[str]:
    """Return ticket IDs that were sent but not yet receipt-checked."""
    with _LOCK:
        store = _load_store()
    deliveries = store.get("deliveries") or []
    out = []
    for d in reversed(deliveries):
        if not isinstance(d, dict):
            continue
        if d.get("status") != STATUS_SENT:
            continue
        ticket_id = d.get("expo_ticket_id")
        if ticket_id and not d.get("expo_receipt_id"):
            out.append(str(ticket_id))
            if len(out) >= max(1, min(500, limit)):
                break
    return out


def mark_token_deactivated_for_delivery(delivery_id: str) -> Optional[Dict[str, Any]]:
    """Mark delivery as token_deactivated (token was invalid)."""
    return update_delivery_status(
        delivery_id,
        status=STATUS_TOKEN_DEACTIVATED,
        error_code="DeviceNotRegistered",
    )


def list_deliveries(
    *,
    user_id: Optional[str] = None,
    alert_type: Optional[str] = None,
    status: Optional[str] = None,
    dry_run: Optional[bool] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """List deliveries with optional filters. Date format: ISO or YYYY-MM-DD."""
    uid = _normalize_space(user_id) if user_id else None
    atype = _normalize_space(alert_type) if alert_type else None
    with _LOCK:
        store = _load_store()
    deliveries = store.get("deliveries") or []
    out = []
    for d in reversed(deliveries):
        if not isinstance(d, dict):
            continue
        if uid and _normalize_space(d.get("user_id")) != uid:
            continue
        if atype and _normalize_space(d.get("alert_type")) != atype:
            continue
        if status and _normalize_space(d.get("status")) != status:
            continue
        if dry_run is not None and d.get("dry_run") != dry_run:
            continue
        created = d.get("created_at") or ""
        if start_date and created < start_date:
            continue
        if end_date and created > end_date:
            continue
        out.append(dict(d))
        if len(out) >= max(1, min(2000, limit)):
            break
    return out


def list_recent_deliveries(
    limit: int = 50,
    *,
    user_id: Optional[str] = None,
    alert_type: Optional[str] = None,
    status: Optional[str] = None,
    dry_run: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Return most recent deliveries (by created_at desc)."""
    return list_deliveries(
        user_id=user_id,
        alert_type=alert_type,
        status=status,
        dry_run=dry_run,
        limit=limit,
    )


def was_recently_sent(user_id: str, expo_push_token: str, alert_id: str, within_hours: float = 6.0) -> bool:
    """Check if same alert was sent to same token recently (for duplicate suppression)."""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).isoformat()
    uid = _normalize_space(user_id)
    token = _normalize_space(expo_push_token)
    aid = _normalize_space(alert_id)
    with _LOCK:
        store = _load_store()
    deliveries = store.get("deliveries") or []
    for d in reversed(deliveries):
        if not isinstance(d, dict):
            continue
        if _normalize_space(d.get("user_id")) != uid:
            continue
        if _normalize_space(d.get("expo_push_token")) != token:
            continue
        if _normalize_space(d.get("alert_id")) != aid:
            continue
        if d.get("status") in (STATUS_SENT, STATUS_RECEIPT_OK):
            created = d.get("created_at") or ""
            if created >= cutoff:
                return True
    return False


def get_recently_sent_place_ids(user_id: str, within_hours: float = 24.0) -> set:
    """Return set of place_ids sent to this user in the last within_hours (for alert variety)."""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).isoformat()
    uid = _normalize_space(user_id)
    with _LOCK:
        store = _load_store()
    deliveries = store.get("deliveries") or []
    out: set = set()
    for d in reversed(deliveries):
        if not isinstance(d, dict):
            continue
        if _normalize_space(d.get("user_id")) != uid:
            continue
        if d.get("status") not in (STATUS_SENT, STATUS_RECEIPT_OK, STATUS_DRY_RUN):
            continue
        created = d.get("created_at") or ""
        if created < cutoff:
            break
        pid = _normalize_space(d.get("place_id") or "")
        if pid:
            out.add(pid)
    return out

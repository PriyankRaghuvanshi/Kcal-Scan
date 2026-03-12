"""
User venue contributions store.
Stores user suggestions for local venues (better order, veg/vegan options, accuracy, etc.).
Used by contribution_review_flow for human-in-the-loop approval.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

CONTRIBUTION_VERSION = "v1"
STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"

CONTRIBUTION_TYPES = (
    "better_order_suggestion",
    "item_not_on_menu",
    "vegetarian_option_missing",
    "vegan_option_missing",
    "recommendation_accurate",
    "recommendation_inaccurate",
    "menu_item_correction",
)

_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_path() -> Path:
    override = str(os.getenv("USER_VENUE_CONTRIBUTIONS_PATH", "") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "user_venue_contributions.json"


def _empty_store() -> Dict[str, Any]:
    return {"version": CONTRIBUTION_VERSION, "contributions": []}


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", CONTRIBUTION_VERSION)
            data.setdefault("contributions", [])
            if isinstance(data.get("contributions"), list):
                return data
    except Exception:
        pass
    return _empty_store()


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def create_contribution(
    *,
    place_id: str = "",
    place_name: str = "",
    area_key: str = "",
    contribution_type: str,
    user_id: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a new contribution. Returns the created record.
    """
    ctype = str(contribution_type or "").strip().lower()
    if ctype not in CONTRIBUTION_TYPES:
        ctype = "better_order_suggestion"

    record = {
        "contribution_id": str(uuid.uuid4()),
        "place_id": str(place_id or "").strip(),
        "place_name": str(place_name or "").strip(),
        "area_key": str(area_key or "").strip().lower(),
        "contribution_type": ctype,
        "user_id": str(user_id or "").strip(),
        "payload": dict(payload or {}),
        "status": STATUS_PENDING,
        "created_at": _now_iso(),
        "reviewed_at": None,
        "reviewer_id": None,
        "reviewer_notes": None,
        "action_applied": None,
    }

    with _LOCK:
        store = _load_store()
        contributions = store.get("contributions") or []
        if not isinstance(contributions, list):
            contributions = []
        contributions.append(record)
        store["contributions"] = contributions
        store["version"] = CONTRIBUTION_VERSION
        _save_store(store)

    return dict(record)


def get_contribution(contribution_id: str) -> Optional[Dict[str, Any]]:
    """Get a contribution by ID."""
    cid = str(contribution_id or "").strip()
    if not cid:
        return None
    store = _load_store()
    for c in (store.get("contributions") or []):
        if isinstance(c, dict) and str(c.get("contribution_id") or "") == cid:
            return dict(c)
    return None


def update_contribution_status(
    contribution_id: str,
    status: str,
    *,
    reviewer_id: str = "",
    reviewer_notes: str = "",
    action_applied: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Update contribution status (accepted/rejected). Returns updated record or None."""
    cid = str(contribution_id or "").strip()
    if not cid or status not in (STATUS_ACCEPTED, STATUS_REJECTED):
        return None

    with _LOCK:
        store = _load_store()
        contributions = store.get("contributions") or []
        for c in contributions:
            if isinstance(c, dict) and str(c.get("contribution_id") or "") == cid:
                c["status"] = status
                c["reviewed_at"] = _now_iso()
                c["reviewer_id"] = str(reviewer_id or "").strip()
                c["reviewer_notes"] = str(reviewer_notes or "").strip()
                if action_applied is not None:
                    c["action_applied"] = dict(action_applied)
                store["version"] = CONTRIBUTION_VERSION
                _save_store(store)
                return dict(c)
    return None


def list_all_contributions(limit: int = 10000) -> List[Dict[str, Any]]:
    """List all contributions (for aggregation). Not filtered by status."""
    store = _load_store()
    contributions = store.get("contributions") or []
    return [dict(c) for c in contributions if isinstance(c, dict)][:limit]


def list_pending(area_key: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """List contributions with status=pending. Optionally filter by area_key."""
    store = _load_store()
    pending = [
        dict(c) for c in (store.get("contributions") or [])
        if isinstance(c, dict) and str(c.get("status") or "").strip() == STATUS_PENDING
    ]
    if area_key:
        area_norm = str(area_key or "").strip().lower()
        pending = [c for c in pending if str(c.get("area_key") or "").strip().lower() == area_norm]
    pending.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
    return pending[:max(1, min(limit, 200))]


def count_by_place(place_id: str, place_name: str, area_key: str) -> tuple:
    """
    Return (total_contributions_for_place, pending_count_for_place).
    Matches by place_id if set, else place_name + area_key.
    """
    store = _load_store()
    contributions = store.get("contributions") or []
    pid = str(place_id or "").strip()
    pname = str(place_name or "").strip().lower()
    area = str(area_key or "").strip().lower()

    total = 0
    pending = 0
    for c in contributions:
        if not isinstance(c, dict):
            continue
        cpid = str(c.get("place_id") or "").strip()
        cname = str(c.get("place_name") or "").strip().lower()
        carea = str(c.get("area_key") or "").strip().lower()
        match = False
        if pid and cpid == pid:
            match = True
        elif pname and carea and cname == pname and carea == area:
            match = True
        if match:
            total += 1
            if str(c.get("status") or "").strip() == STATUS_PENDING:
                pending += 1
    return total, pending

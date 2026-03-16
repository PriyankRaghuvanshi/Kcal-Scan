"""
Goal Coach action funnel tracking — lightweight event log.
Events: shown, clicked, destination_opened, action_completed.
No LLM; best-effort; analytics failure must not break the product path.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

GOAL_COACH_TRACKING_VERSION = "v1"
_MAX_EVENTS = 50000
_LOCK = threading.Lock()

ALLOWED_EVENT_TYPES = {
    "goal_coach_daily_action_shown",
    "goal_coach_daily_action_clicked",
    "goal_coach_weekly_action_shown",
    "goal_coach_weekly_action_clicked",
    "goal_coach_destination_opened",
    "goal_coach_action_completed",
}

ALLOWED_SOURCE_SURFACES = ("daily_coach", "weekly_review", "goal_plan")
ALLOWED_ACTION_TYPES = (
    "open_healthy_nearby",
    "open_scan_camera",
    "open_supplement_scan",
    "open_daily_summary",
    "open_goal_plan",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _norm_lower(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().split())


def _env_path() -> Path:
    override = _normalize_space(os.getenv("GOAL_COACH_ACTION_TRACKING_PATH", ""))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "goal_coach_action_events.json"


def _empty_store() -> Dict[str, Any]:
    return {"version": GOAL_COACH_TRACKING_VERSION, "events": []}


def _load_store() -> Dict[str, Any]:
    path = _env_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            data.setdefault("version", GOAL_COACH_TRACKING_VERSION)
            return data
    except Exception:
        pass
    return _empty_store()


def _save_store(store: Dict[str, Any]) -> None:
    path = _env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=True, indent=2, sort_keys=True)


def _sanitize_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract allowed non-sensitive fields for event row."""
    out: Dict[str, Any] = {}
    for key in (
        "user_id",
        "source_surface",
        "action_type",
        "goal_type",
        "reason",
        "remaining_protein_g",
        "remaining_calories",
        "kickoff_active",
        "subscription_required",
        "preferred_mode",
        "completion_type",
        "place_id",
        "place_name",
    ):
        v = payload.get(key)
        if v is None:
            continue
        if key in ("remaining_protein_g", "remaining_calories") and v is not None:
            try:
                out[key] = int(float(v))
            except (TypeError, ValueError):
                out[key] = v
        elif key in ("kickoff_active", "subscription_required") and v is not None:
            out[key] = bool(v)
        else:
            out[key] = v
    return out


def log_goal_coach_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Log one Goal Coach funnel event. Payload must include event_type and user_id.
    """
    event_type = _norm_lower(payload.get("event_type", ""))
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError("invalid_event_type")

    user_id = _normalize_space(payload.get("user_id"))
    if not user_id:
        raise ValueError("user_id_required")

    meta = _sanitize_metadata(payload)
    source = _norm_lower(meta.get("source_surface", ""))
    if source and source not in ALLOWED_SOURCE_SURFACES:
        meta["source_surface"] = "daily_coach" if "daily" in event_type else "weekly_review" if "weekly" in event_type else ""

    action_type = _norm_lower(meta.get("action_type", ""))
    if action_type and action_type not in ALLOWED_ACTION_TYPES:
        meta["action_type"] = ""

    row: Dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "user_id": user_id,
        "timestamp": _now_iso(),
        **meta,
    }

    with _LOCK:
        store = _load_store()
        events = store.get("events") if isinstance(store.get("events"), list) else []
        store["events"] = events
        events.append(row)
        if len(events) > _MAX_EVENTS:
            store["events"] = events[-_MAX_EVENTS:]
        store["version"] = GOAL_COACH_TRACKING_VERSION
        _save_store(store)

    return dict(row)


def list_goal_coach_events(
    *,
    user_id: str = "",
    event_type: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 500,
) -> List[Dict[str, Any]]:
    uid = _normalize_space(user_id)
    etype = _norm_lower(event_type)
    with _LOCK:
        store = _load_store()
    events = store.get("events") if isinstance(store.get("events"), list) else []
    out: List[Dict[str, Any]] = []
    for e in reversed(events):
        if not isinstance(e, dict):
            continue
        if uid and _normalize_space(e.get("user_id")) != uid:
            continue
        if etype and _norm_lower(e.get("event_type")) != etype:
            continue
        created = str(e.get("timestamp") or e.get("created_at") or "")[:19]
        if start_date and created < start_date:
            continue
        if end_date and created > end_date:
            continue
        out.append(dict(e))
        if len(out) >= max(1, min(10000, int(limit or 500))):
            break
    return out

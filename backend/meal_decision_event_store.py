from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


MEAL_DECISION_EVENT_STORE_VERSION = "v1"
_MAX_EVENTS = 50000
_LOCK = threading.Lock()

ALLOWED_EVENT_TYPES = {
    "recommendation_viewed",
    "recommendation_opened",
    "place_opened",
    "best_item_viewed",
    "swap_viewed",
    "swap_accepted",
    "recommendation_chosen",
    "recommendation_ignored",
}

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _norm_lower(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().split())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return _norm_lower(raw) in _TRUE_VALUES


def _store_path() -> Path:
    override = _normalize_space(os.getenv("MEAL_DECISION_EVENT_STORE_PATH", ""))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "meal_decision_event_store.json"


def _empty_store() -> Dict[str, Any]:
    return {"version": MEAL_DECISION_EVENT_STORE_VERSION, "events": []}


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", MEAL_DECISION_EVENT_STORE_VERSION)
            data.setdefault("events", [])
            if isinstance(data.get("events"), list):
                return data
    except Exception:
        pass
    return _empty_store()


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=True, indent=2, sort_keys=True)


def log_meal_decision_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    user_id = _normalize_space(payload.get("user_id"))
    if not user_id:
        raise ValueError("user_id_required")
    event_type = _norm_lower(payload.get("event_type"))
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError("invalid_event_type")

    row: Dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "user_id": user_id,
        "event_type": event_type,
        "place_id": _normalize_space(payload.get("place_id")),
        "place_name": _normalize_space(payload.get("place_name")),
        "best_item_name": _normalize_space(payload.get("best_item_name")),
        "selected_candidate_source": _normalize_space(payload.get("selected_candidate_source")),
        "recommendation_label": _normalize_space(payload.get("recommendation_label")),
        "confidence_label": _normalize_space(payload.get("confidence_label")),
        "display_rank_score_100": payload.get("display_rank_score_100"),
        "goal": _normalize_space(payload.get("goal")),
        "time_of_day": _normalize_space(payload.get("time_of_day")),
        "created_at": _now_iso(),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }

    with _LOCK:
        store = _load_store()
        events = store.get("events") if isinstance(store.get("events"), list) else []
        store["events"] = events
        events.append(row)
        if len(events) > _MAX_EVENTS:
            store["events"] = events[-_MAX_EVENTS:]
        store["version"] = MEAL_DECISION_EVENT_STORE_VERSION
        _save_store(store)

    return dict(row)


def list_meal_decision_events(
    *,
    user_id: str = "",
    event_type: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    uid = _normalize_space(user_id)
    etype = _normalize_space(event_type)
    with _LOCK:
        store = _load_store()
    events = store.get("events") if isinstance(store.get("events"), list) else []
    out = []
    for e in reversed(events):
        if not isinstance(e, dict):
            continue
        if uid and _normalize_space(e.get("user_id")) != uid:
            continue
        if etype and _norm_lower(e.get("event_type")) != etype:
            continue
        created = e.get("created_at") or ""
        if start_date and created < start_date:
            continue
        if end_date and created > end_date:
            continue
        out.append(dict(e))
        if len(out) >= max(1, min(2000, int(limit or 200))):
            break
    return out


def clear_meal_decision_store_for_tests() -> None:
    if not _env_bool("MEAL_DECISION_ALLOW_CLEAR", default=False):
        return
    with _LOCK:
        _save_store(_empty_store())


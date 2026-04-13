from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MEAL_FEEDBACK_STORE_VERSION = "v1"
_MAX_EVENTS = 20000
_LOCK = threading.Lock()

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _norm_lower(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().split())


def _safe_int(v: Any, default: int | None = None) -> int | None:
    try:
        return int(v)
    except Exception:
        try:
            return int(round(float(v)))
        except Exception:
            return default


def _safe_float(v: Any, default: float | None = None) -> float | None:
    try:
        return float(v)
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    token = _norm_lower(raw)
    return token in _TRUE_VALUES


def _store_path() -> Path:
    override = _normalize_space(os.getenv("MEAL_FEEDBACK_STORE_PATH", ""))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "meal_feedback_store.json"


def _empty_store() -> Dict[str, Any]:
    return {"version": MEAL_FEEDBACK_STORE_VERSION, "events": []}


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", MEAL_FEEDBACK_STORE_VERSION)
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


def _event_id(v: Any) -> str:
    token = _normalize_space(v)
    return token if token else str(uuid.uuid4())


def _merge_event(existing: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    # Only overwrite fields that are present in update and not empty.
    out = dict(existing)
    for k, v in (update or {}).items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        out[k] = v
    out["updated_at"] = _now_iso()
    return out


def upsert_meal_feedback_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept partial submissions. If feedback_id exists, update that event; else create new.
    """
    user_id = _normalize_space(payload.get("user_id"))
    if not user_id:
        raise ValueError("user_id_required")

    feedback_id = _event_id(payload.get("feedback_id") or payload.get("event_id"))
    row: Dict[str, Any] = {
        "feedback_id": feedback_id,
        "user_id": user_id,
        "place_id": _normalize_space(payload.get("place_id")),
        "place_name": _normalize_space(payload.get("place_name")),
        "best_item_name": _normalize_space(payload.get("best_item_name")),
        "selected_item_name": _normalize_space(payload.get("selected_item_name")),
        "selected_candidate_source": _normalize_space(payload.get("selected_candidate_source")),
        "swap_accepted": bool(payload.get("swap_accepted")) if payload.get("swap_accepted") is not None else None,
        "accepted_swap_label": _normalize_space(payload.get("accepted_swap_label")),
        "estimated_calories": _safe_int(payload.get("estimated_calories")),
        "estimated_protein_g": _safe_int(payload.get("estimated_protein_g")),
        "goal": _normalize_space(payload.get("goal")),
        "time_of_day": _normalize_space(payload.get("time_of_day")),
        "fullness_score": _safe_int(payload.get("fullness_score")),
        "craving_score": _safe_int(payload.get("craving_score")),
        "energy_score": _safe_int(payload.get("energy_score")),
        "repeat_intent": bool(payload.get("repeat_intent")) if payload.get("repeat_intent") is not None else None,
        "helped_on_target": bool(payload.get("helped_on_target")) if payload.get("helped_on_target") is not None else None,
        "notes": _normalize_space(payload.get("notes")),
        "created_at": _normalize_space(payload.get("created_at")) or _now_iso(),
    }

    with _LOCK:
        store = _load_store()
        events = store.get("events") if isinstance(store.get("events"), list) else []
        store["events"] = events
        idx = next((i for i, e in enumerate(events) if isinstance(e, dict) and e.get("feedback_id") == feedback_id), -1)
        if idx >= 0:
            events[idx] = _merge_event(events[idx], row)
            saved = events[idx]
        else:
            events.append(row)
            if len(events) > _MAX_EVENTS:
                store["events"] = events[-_MAX_EVENTS:]
            saved = row
        store["version"] = MEAL_FEEDBACK_STORE_VERSION
        _save_store(store)

    return dict(saved)


def list_meal_feedback_events(*, user_id: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    uid = _normalize_space(user_id)
    with _LOCK:
        store = _load_store()
    events = store.get("events") if isinstance(store.get("events"), list) else []
    out = []
    for e in reversed(events):
        if not isinstance(e, dict):
            continue
        if uid and _normalize_space(e.get("user_id")) != uid:
            continue
        out.append(dict(e))
        if len(out) >= max(1, min(1000, int(limit or 200))):
            break
    return out


def get_usual_meal_at_place(user_id: str, place_id: str, *, lookback: int = 200) -> Optional[Dict[str, Any]]:
    """
    Return the user's "usual" item at this place, computed from prior feedback events.
    Picks the most-frequently-recorded `selected_item_name` (falls back to
    `best_item_name`) for (user_id, place_id). Ties broken by most-recent.

    Returns None when:
      - missing user_id / place_id
      - no events match
      - <2 events at this place (one-off — not yet a "usual")

    Shape:
      {
        "item_name": str,
        "estimated_calories": int|None,
        "estimated_protein_g": int|None,
        "times_chosen": int,
        "last_seen_iso": str,
        "source": "selected" | "recommended",
      }
    """
    uid = _normalize_space(user_id)
    pid = _normalize_space(place_id)
    if not uid or not pid:
        return None
    with _LOCK:
        store = _load_store()
    events = store.get("events") if isinstance(store.get("events"), list) else []
    matched = []
    for e in events:
        if not isinstance(e, dict): continue
        if _normalize_space(e.get("user_id")) != uid: continue
        if _normalize_space(e.get("place_id")) != pid: continue
        matched.append(e)
    if len(matched) < 2:
        return None
    # Tally by selected_item_name first, fall back to best_item_name
    from collections import Counter
    selected_counter: Counter = Counter()
    recommended_counter: Counter = Counter()
    last_kcal: Dict[str, Any] = {}
    last_protein: Dict[str, Any] = {}
    last_seen: Dict[str, str] = {}
    for e in matched:
        sel = _normalize_space(e.get("selected_item_name"))
        rec = _normalize_space(e.get("best_item_name"))
        ts = _normalize_space(e.get("created_at"))
        if sel:
            selected_counter[sel] += 1
            last_kcal[sel] = e.get("estimated_calories")
            last_protein[sel] = e.get("estimated_protein_g")
            if ts and ts > last_seen.get(sel, ""):
                last_seen[sel] = ts
        elif rec:
            recommended_counter[rec] += 1
            last_kcal[rec] = e.get("estimated_calories")
            last_protein[rec] = e.get("estimated_protein_g")
            if ts and ts > last_seen.get(rec, ""):
                last_seen[rec] = ts
    counter = selected_counter if selected_counter else recommended_counter
    src = "selected" if selected_counter else "recommended"
    if not counter:
        return None
    # Sort by count DESC, then by recency DESC
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], -last_seen.get(kv[0], "").__hash__()))
    name, times = ranked[0]
    return {
        "item_name": name,
        "estimated_calories": _safe_int(last_kcal.get(name)),
        "estimated_protein_g": _safe_int(last_protein.get(name)),
        "times_chosen": int(times),
        "last_seen_iso": last_seen.get(name, ""),
        "source": src,
    }


def clear_meal_feedback_store_for_tests() -> None:
    """
    Test helper. Only enabled when MEAL_FEEDBACK_ALLOW_CLEAR=1.
    """
    if not _env_bool("MEAL_FEEDBACK_ALLOW_CLEAR", default=False):
        return
    with _LOCK:
        _save_store(_empty_store())


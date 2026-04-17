from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_VERSION = "v1"

_COLLECTIONS = [
    "households",
    "children",
    "child_safe_foods",
    "child_target_foods",
    "meals_served",
    "meal_components",
    "child_meal_outcomes",
    "food_exposures",
    "routine_signals",
    "rescue_sessions",
    "weekly_resets",
    "family_meal_memory",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _safe_str(value: Any) -> str:
    return str(value or "").strip()



def _store_path() -> Path:
    override = _safe_str(os.getenv("FAMILY_HABITS_STORE_PATH"))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "family_habits_store.json"



def _empty_store() -> Dict[str, Any]:
    data = {"version": _VERSION}
    for name in _COLLECTIONS:
        data[name] = []
    return data



def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            base = _empty_store()
            base.update(data)
            for name in _COLLECTIONS:
                if not isinstance(base.get(name), list):
                    base[name] = []
            return base
    except Exception:
        pass
    return _empty_store()



def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")



def _list_rows(collection: str, **filters: str) -> List[Dict[str, Any]]:
    with _LOCK:
        store = _load_store()
    rows = store.get(collection) if isinstance(store.get(collection), list) else []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        matches = True
        for key, expected in filters.items():
            if expected and _safe_str(row.get(key)) != _safe_str(expected):
                matches = False
                break
        if matches:
            out.append(dict(row))
    return out



def _upsert_row(collection: str, id_key: str, row: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        store = _load_store()
        rows = store.get(collection) if isinstance(store.get(collection), list) else []
        store[collection] = rows
        row_id = _safe_str(row.get(id_key)) or str(uuid.uuid4())
        payload = dict(row)
        payload[id_key] = row_id
        payload.setdefault("created_at", _now_iso())
        payload["updated_at"] = _now_iso()
        idx = next((i for i, existing in enumerate(rows) if isinstance(existing, dict) and _safe_str(existing.get(id_key)) == row_id), -1)
        if idx >= 0:
            merged = dict(rows[idx])
            merged.update(payload)
            rows[idx] = merged
            saved = merged
        else:
            rows.append(payload)
            saved = payload
        _save_store(store)
    return dict(saved)



def _append_row(collection: str, row: Dict[str, Any], id_key: str) -> Dict[str, Any]:
    payload = dict(row)
    payload[id_key] = _safe_str(payload.get(id_key)) or str(uuid.uuid4())
    payload.setdefault("created_at", _now_iso())
    payload["updated_at"] = _now_iso()
    with _LOCK:
        store = _load_store()
        rows = store.get(collection) if isinstance(store.get(collection), list) else []
        rows.append(payload)
        store[collection] = rows
        _save_store(store)
    return dict(payload)



def get_household(owner_user_id: str) -> Optional[Dict[str, Any]]:
    rows = _list_rows("households", owner_user_id=owner_user_id)
    return rows[0] if rows else None



def upsert_household(row: Dict[str, Any]) -> Dict[str, Any]:
    return _upsert_row("households", "household_id", row)



def list_children(household_id: str) -> List[Dict[str, Any]]:
    return _list_rows("children", household_id=household_id)



def upsert_child(row: Dict[str, Any]) -> Dict[str, Any]:
    return _upsert_row("children", "child_id", row)



def replace_child_safe_foods(child_id: str, foods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    with _LOCK:
        store = _load_store()
        rows = [row for row in store.get("child_safe_foods", []) if _safe_str(row.get("child_id")) != _safe_str(child_id)]
        for row in foods:
            payload = dict(row)
            payload["safe_food_id"] = _safe_str(payload.get("safe_food_id")) or str(uuid.uuid4())
            payload["child_id"] = child_id
            payload["active"] = True
            payload.setdefault("created_at", _now_iso())
            payload["updated_at"] = _now_iso()
            rows.append(payload)
        store["child_safe_foods"] = rows
        _save_store(store)
    return _list_rows("child_safe_foods", child_id=child_id)



def replace_child_target_foods(child_id: str, foods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    with _LOCK:
        store = _load_store()
        rows = [row for row in store.get("child_target_foods", []) if _safe_str(row.get("child_id")) != _safe_str(child_id)]
        for row in foods:
            payload = dict(row)
            payload["target_food_id"] = _safe_str(payload.get("target_food_id")) or str(uuid.uuid4())
            payload["child_id"] = child_id
            payload["active"] = True
            payload.setdefault("created_at", _now_iso())
            payload["updated_at"] = _now_iso()
            rows.append(payload)
        store["child_target_foods"] = rows
        _save_store(store)
    return _list_rows("child_target_foods", child_id=child_id)



def list_child_safe_foods(household_id: str = "", child_id: str = "") -> List[Dict[str, Any]]:
    rows = _list_rows("child_safe_foods", child_id=child_id) if child_id else _list_rows("child_safe_foods")
    rows = [row for row in rows if row.get("active", True) is not False]
    if not household_id:
        return rows
    children = {row["child_id"] for row in list_children(household_id)}
    return [row for row in rows if _safe_str(row.get("child_id")) in children]



def list_child_target_foods(household_id: str = "", child_id: str = "") -> List[Dict[str, Any]]:
    rows = _list_rows("child_target_foods", child_id=child_id) if child_id else _list_rows("child_target_foods")
    rows = [row for row in rows if row.get("active", True) is not False]
    if not household_id:
        return rows
    children = {row["child_id"] for row in list_children(household_id)}
    return [row for row in rows if _safe_str(row.get("child_id")) in children]



def create_meal_served(row: Dict[str, Any]) -> Dict[str, Any]:
    return _append_row("meals_served", row, "meal_id")



def create_meal_component(row: Dict[str, Any]) -> Dict[str, Any]:
    return _append_row("meal_components", row, "component_id")



def list_meals_served(household_id: str) -> List[Dict[str, Any]]:
    return _list_rows("meals_served", household_id=household_id)



def create_child_meal_outcome(row: Dict[str, Any]) -> Dict[str, Any]:
    return _append_row("child_meal_outcomes", row, "outcome_id")



def list_child_meal_outcomes(household_id: str = "", child_id: str = "") -> List[Dict[str, Any]]:
    rows = _list_rows("child_meal_outcomes", child_id=child_id) if child_id else _list_rows("child_meal_outcomes")
    if not household_id:
        return rows
    meals = {row["meal_id"] for row in list_meals_served(household_id)}
    return [row for row in rows if _safe_str(row.get("meal_id")) in meals]



def create_food_exposure(row: Dict[str, Any]) -> Dict[str, Any]:
    return _append_row("food_exposures", row, "exposure_id")



def list_food_exposures(household_id: str = "", child_id: str = "") -> List[Dict[str, Any]]:
    rows = _list_rows("food_exposures", child_id=child_id) if child_id else _list_rows("food_exposures")
    if not household_id:
        return rows
    children = {row["child_id"] for row in list_children(household_id)}
    return [row for row in rows if _safe_str(row.get("child_id")) in children]



def create_routine_signal(row: Dict[str, Any]) -> Dict[str, Any]:
    return _append_row("routine_signals", row, "signal_id")



def list_routine_signals(household_id: str) -> List[Dict[str, Any]]:
    return _list_rows("routine_signals", household_id=household_id)



def create_rescue_session(row: Dict[str, Any]) -> Dict[str, Any]:
    return _append_row("rescue_sessions", row, "rescue_session_id")



def list_rescue_sessions(household_id: str) -> List[Dict[str, Any]]:
    return _list_rows("rescue_sessions", household_id=household_id)



def create_weekly_reset(row: Dict[str, Any]) -> Dict[str, Any]:
    return _append_row("weekly_resets", row, "weekly_reset_id")



def get_latest_weekly_reset(household_id: str) -> Optional[Dict[str, Any]]:
    rows = list_rescue_sessions(household_id)
    rows = _list_rows("weekly_resets", household_id=household_id)
    rows.sort(key=lambda row: _safe_str(row.get("created_at")), reverse=True)
    return rows[0] if rows else None



def upsert_family_meal_memory(row: Dict[str, Any]) -> Dict[str, Any]:
    return _upsert_row("family_meal_memory", "memory_id", row)



def get_family_meal_memory(household_id: str) -> Optional[Dict[str, Any]]:
    rows = _list_rows("family_meal_memory", household_id=household_id)
    rows.sort(key=lambda row: _safe_str(row.get("updated_at")), reverse=True)
    return rows[0] if rows else None

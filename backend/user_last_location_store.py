"""
User last-known location store for batch Smart Alert sending.
Persisted when user calls /places/healthy or /push/send-smart-alerts with user_id.
"""

from __future__ import annotations

import json
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_LOCK = threading.Lock()


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _store_path() -> Path:
    override = _normalize_space(os.getenv("USER_LAST_LOCATION_STORE_PATH", ""))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "user_last_location_store.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"locations": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("locations"), dict):
            return data
    except Exception:
        pass
    return {"locations": {}}


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=True, indent=2, sort_keys=True)


def upsert_user_location(user_id: str, lat: float, lng: float) -> Dict[str, Any]:
    """
    Store last-known location for a user. Called when user fetches /places/healthy
    or /push/send-smart-alerts with user_id.
    """
    uid = _normalize_space(user_id)
    if not uid:
        return {}
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return {}
    now = _now_iso()
    entry = {"user_id": uid, "lat": float(lat), "lng": float(lng), "updated_at": now}
    with _LOCK:
        store = _load_store()
        locations = dict(store.get("locations") or {})
        locations[uid] = entry
        store["locations"] = locations
        _save_store(store)
    return dict(entry)


def get_user_location(user_id: str) -> Optional[Dict[str, Any]]:
    """Return last-known lat/lng for user, or None if not stored."""
    uid = _normalize_space(user_id)
    if not uid:
        return None
    with _LOCK:
        store = _load_store()
    locations = store.get("locations") or {}
    entry = locations.get(uid)
    if not isinstance(entry, dict):
        return None
    lat = entry.get("lat")
    lng = entry.get("lng")
    if lat is None or lng is None or not (math.isfinite(float(lat)) and math.isfinite(float(lng))):
        return None
    return {"user_id": uid, "lat": float(lat), "lng": float(lng), "updated_at": entry.get("updated_at", "")}


def list_user_ids_with_location(limit: int = 10000) -> list[str]:
    """Return user_ids that have stored location, for batch iteration."""
    with _LOCK:
        store = _load_store()
    locations = store.get("locations") or {}
    if not isinstance(locations, dict):
        return []
    out = []
    for uid, entry in locations.items():
        if not uid or not isinstance(entry, dict):
            continue
        lat = entry.get("lat")
        lng = entry.get("lng")
        if lat is None or lng is None:
            continue
        try:
            if math.isfinite(float(lat)) and math.isfinite(float(lng)):
                out.append(uid)
        except (TypeError, ValueError):
            continue
        if len(out) >= limit:
            break
    return out

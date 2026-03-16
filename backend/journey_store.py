"""
Let's Go journey entries: weight, check-ins (after meal), weekly progress photos.
File-backed store keyed by user_id. Used for daily check-in and progress tracking.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()


def _store_path() -> Path:
    override = (os.getenv("JOURNEY_STORE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "journey_entries.json"


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"version": "1", "users": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", "1")
            data.setdefault("users", {})
            if isinstance(data.get("users"), dict):
                return data
    except Exception:
        pass
    return {"version": "1", "users": {}}


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def _user_data(store: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    uid = (user_id or "").strip()
    if not uid:
        return {}
    users = store.get("users") or {}
    if uid not in users or not isinstance(users[uid], dict):
        users[uid] = {"weight_entries": [], "check_ins": [], "photo_entries": []}
    return users[uid]


def add_weight_entry(user_id: str, value_kg: float, day_iso: Optional[str] = None) -> Dict[str, Any]:
    """Append a weight measurement. day_iso defaults to today (YYYY-MM-DD)."""
    import datetime as dt
    day = (day_iso or "").strip() or dt.date.today().isoformat()
    value = max(0.0, float(value_kg))
    entry = {"day": day[:10], "value_kg": round(value, 1), "ts": dt.datetime.utcnow().isoformat()}
    with _LOCK:
        store = _load_store()
        data = _user_data(store, user_id)
        data.setdefault("weight_entries", [])
        data["weight_entries"].append(entry)
        data["weight_entries"] = sorted(data["weight_entries"], key=lambda x: x.get("day", ""), reverse=True)[:365]
        store.setdefault("users", {})[(user_id or "").strip()] = data
        _save_store(store)
    return entry


def get_weight_entries(user_id: str, limit: int = 90) -> List[Dict[str, Any]]:
    """Return recent weight entries, newest first."""
    with _LOCK:
        store = _load_store()
        data = _user_data(store, user_id)
    entries = (data.get("weight_entries") or [])[: max(1, limit)]
    return list(entries)


def add_check_in(
    user_id: str,
    day_iso: Optional[str] = None,
    analysis_id: Optional[str] = None,
    meal_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a check-in (e.g. after a meal)."""
    import datetime as dt
    day = (day_iso or "").strip() or dt.date.today().isoformat()
    entry = {
        "day": day[:10],
        "ts": dt.datetime.utcnow().isoformat(),
        "analysis_id": (analysis_id or "").strip() or None,
        "meal": (meal_label or "").strip() or None,
    }
    with _LOCK:
        store = _load_store()
        data = _user_data(store, user_id)
        data.setdefault("check_ins", [])
        data["check_ins"].append(entry)
        data["check_ins"] = data["check_ins"][-500:]
        store.setdefault("users", {})[(user_id or "").strip()] = data
        _save_store(store)
    return entry


def get_check_ins(user_id: str, day_iso: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Return check-ins, optionally for a single day. Newest first."""
    with _LOCK:
        store = _load_store()
        data = _user_data(store, user_id)
    entries = data.get("check_ins") or []
    if day_iso:
        day = (day_iso or "")[:10]
        entries = [e for e in entries if (e.get("day") or "")[:10] == day]
    return list(entries)[-limit:][::-1]


def add_photo_entry(
    user_id: str,
    week_start_iso: str,
    uri_or_ref: str,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Append a weekly progress photo reference (app stores image; we store ref/week)."""
    week = (week_start_iso or "")[:10]
    ref = (uri_or_ref or "").strip()
    if not week or not ref:
        return {}
    import datetime as dt
    entry = {
        "week_start": week,
        "uri_or_ref": ref[:512],
        "note": (note or "").strip() or None,
        "ts": dt.datetime.utcnow().isoformat(),
    }
    with _LOCK:
        store = _load_store()
        data = _user_data(store, user_id)
        data.setdefault("photo_entries", [])
        data["photo_entries"].append(entry)
        data["photo_entries"] = sorted(data["photo_entries"], key=lambda x: x.get("week_start", ""), reverse=True)[:52]
        store.setdefault("users", {})[(user_id or "").strip()] = data
        _save_store(store)
    return entry


def get_photo_entries(user_id: str, limit: int = 24) -> List[Dict[str, Any]]:
    """Return weekly photo entries, newest first."""
    with _LOCK:
        store = _load_store()
        data = _user_data(store, user_id)
    return list((data.get("photo_entries") or [])[: max(1, limit)])


def _parse_date(day_iso: str):
    """Return date object or None."""
    import datetime as dt
    try:
        return dt.datetime.strptime((day_iso or "")[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _streak_days(check_ins: List[Dict[str, Any]], today_iso: str) -> int:
    """Consecutive days with at least one check-in ending at today (going backwards)."""
    import datetime as dt
    today = _parse_date(today_iso)
    if not today:
        return 0
    days_with_checkin = set()
    for c in check_ins:
        d = (c.get("day") or "")[:10]
        if d:
            days_with_checkin.add(d)
    if not days_with_checkin:
        return 0
    count = 0
    d = today
    while d.isoformat() in days_with_checkin:
        count += 1
        d = d - dt.timedelta(days=1)
    return count


def _next_check_in_milestone(check_ins_today: int, streak_days: int) -> str:
    """Human-readable next check-in milestone."""
    if check_ins_today == 0 and streak_days == 0:
        return "Log your first meal to start today's check-ins"
    if check_ins_today == 0:
        return "Log a meal today to keep your streak"
    if check_ins_today == 1:
        return "Log another meal to build today's check-ins"
    if check_ins_today == 2:
        return "One more check-in today — you're on fire"
    return "Great — keep logging meals to stay on track"


def get_journey_summary(user_id: str, today_iso: Optional[str] = None) -> Dict[str, Any]:
    """Return counts and latest entries for journey dashboard."""
    import datetime as dt
    today = (today_iso or "").strip() or dt.date.today().isoformat()[:10]
    with _LOCK:
        store = _load_store()
        data = _user_data(store, user_id)
    weights = sorted(data.get("weight_entries") or [], key=lambda x: x.get("day", ""), reverse=True)
    check_ins = data.get("check_ins") or []
    photos = data.get("photo_entries") or []
    check_ins_today = len([c for c in check_ins if (c.get("day") or "")[:10] == today])
    streak_days = _streak_days(check_ins, today)
    return {
        "weight_entries_count": len(weights),
        "latest_weight": weights[0] if weights else None,
        "previous_weight": weights[1] if len(weights) >= 2 else None,
        "check_ins_count": len(check_ins),
        "check_ins_today": check_ins_today,
        "streak_days": streak_days,
        "next_check_in_milestone": _next_check_in_milestone(check_ins_today, streak_days),
        "photo_entries_count": len(photos),
        "latest_photo": photos[0] if photos else None,
    }

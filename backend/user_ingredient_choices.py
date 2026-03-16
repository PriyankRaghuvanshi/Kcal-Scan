"""
User ingredient/clarification choices: remember answers per user and food so we ask less next time.
File-based store (no DB migration). Key: (user_id, food_token) -> { choice_key: value }.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()


def _store_path() -> Path:
    override = (os.getenv("USER_INGREDIENT_CHOICES_STORE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "user_ingredient_choices.json"


def _normalize_token(t: str) -> str:
    return " ".join((t or "").strip().lower().split())[:128]


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"version": "1", "choices": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", "1")
            data.setdefault("choices", {})
            if isinstance(data.get("choices"), dict):
                return data
    except Exception:
        pass
    return {"version": "1", "choices": {}}


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def _user_key(user_id: str, food_token: str) -> str:
    uid = (user_id or "").strip()
    token = _normalize_token(food_token or "")
    if not uid or not token:
        return ""
    return f"{uid}::{token}"


def get_user_ingredient_choices(user_id: str, food_token: str) -> Dict[str, str]:
    """Return stored choices for (user_id, food_token). Keys are e.g. milk_type, sweetener."""
    key = _user_key(user_id, food_token)
    if not key:
        return {}
    with _LOCK:
        store = _load_store()
    choices = (store.get("choices") or {}).get(key)
    if isinstance(choices, dict):
        return {str(k): str(v) for k, v in choices.items() if v is not None}
    return {}


def save_user_ingredient_choices(
    user_id: str,
    food_token: str,
    choices: Dict[str, str],
) -> None:
    """Merge and save choices for (user_id, food_token)."""
    key = _user_key(user_id, food_token)
    if not key or not isinstance(choices, dict):
        return
    merged = {str(k): str(v).strip() for k, v in choices.items() if v is not None and str(v).strip()}
    if not merged:
        return
    with _LOCK:
        store = _load_store()
        by_key = store.setdefault("choices", {})
        existing = by_key.get(key)
        if isinstance(existing, dict):
            merged = {**existing, **merged}
        by_key[key] = merged
        _save_store(store)


def get_food_token_from_item(item: Dict[str, Any]) -> str:
    """Derive a stable food token from an item (e.g. for coffee, smoothie)."""
    name = str((item or {}).get("name") or "").strip().lower()
    if not name:
        return ""
    # Normalize for matching: remove extra spaces, take first 80 chars
    return _normalize_token(name)[:80]

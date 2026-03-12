"""
Push token store: register/unregister Expo push tokens per user.
JSON-backed, env-overridable path. Used by /push/register and /push/unregister.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PUSH_TOKEN_STORE_VERSION = "v1"
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _store_path() -> Path:
    override = _normalize_space(os.getenv("PUSH_TOKEN_STORE_PATH", ""))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "push_token_store.json"


def _empty_store() -> Dict[str, Any]:
    return {"version": PUSH_TOKEN_STORE_VERSION, "tokens": []}


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", PUSH_TOKEN_STORE_VERSION)
            data.setdefault("tokens", [])
            if isinstance(data.get("tokens"), list):
                return data
    except Exception:
        pass
    return _empty_store()


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=True, indent=2, sort_keys=True)


def _token_key(entry: Dict[str, Any]) -> tuple:
    return (
        _normalize_space(entry.get("user_id")),
        _normalize_space(entry.get("expo_push_token")),
    )


def register_push_token(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Register or update a push token. Dedupes by user_id + expo_push_token.
    """
    user_id = _normalize_space(payload.get("user_id"))
    expo_push_token = _normalize_space(payload.get("expo_push_token"))
    if not user_id:
        raise ValueError("user_id required")
    if not expo_push_token or not expo_push_token.startswith("ExponentPushToken["):
        raise ValueError("expo_push_token required and must be Expo token format")

    platform = _normalize_space(payload.get("platform")) or "unknown"
    device_name = _normalize_space(payload.get("device_name")) or ""
    app_version = _normalize_space(payload.get("app_version")) or ""

    now = _now_iso()
    new_entry = {
        "user_id": user_id,
        "expo_push_token": expo_push_token,
        "platform": platform,
        "device_name": device_name,
        "app_version": app_version,
        "active": True,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }

    with _LOCK:
        store = _load_store()
        tokens: List[Dict[str, Any]] = list(store.get("tokens") or [])
        if not isinstance(tokens, list):
            tokens = []

        found_idx: Optional[int] = None
        for i, t in enumerate(tokens):
            if not isinstance(t, dict):
                continue
            if _token_key(t) == (user_id, expo_push_token):
                found_idx = i
                break

        if found_idx is not None:
            existing = tokens[found_idx]
            new_entry["created_at"] = existing.get("created_at", now)
            tokens[found_idx] = new_entry
        else:
            tokens.append(new_entry)

        store["tokens"] = tokens
        store["version"] = PUSH_TOKEN_STORE_VERSION
        _save_store(store)

    return dict(new_entry)


def unregister_push_token(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mark token inactive or remove. Finds by user_id + expo_push_token.
    """
    user_id = _normalize_space(payload.get("user_id"))
    expo_push_token = _normalize_space(payload.get("expo_push_token"))
    if not user_id:
        raise ValueError("user_id required")
    if not expo_push_token:
        raise ValueError("expo_push_token required")

    with _LOCK:
        store = _load_store()
        tokens: List[Dict[str, Any]] = list(store.get("tokens") or [])
        if not isinstance(tokens, list):
            tokens = []

        new_tokens = []
        for t in tokens:
            if not isinstance(t, dict):
                continue
            if _token_key(t) == (user_id, expo_push_token):
                t_copy = dict(t)
                t_copy["active"] = False
                t_copy["updated_at"] = _now_iso()
                new_tokens.append(t_copy)
                continue
            new_tokens.append(t)

        store["tokens"] = new_tokens
        store["version"] = PUSH_TOKEN_STORE_VERSION
        _save_store(store)

    return {"ok": True, "user_id": user_id, "expo_push_token": expo_push_token}


def list_tokens_for_user(user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
    """Return tokens for a user. For future push sending."""
    uid = _normalize_space(user_id)
    with _LOCK:
        store = _load_store()
    tokens = store.get("tokens") or []
    out = []
    for t in tokens:
        if not isinstance(t, dict):
            continue
        if uid and _normalize_space(t.get("user_id")) != uid:
            continue
        if active_only and not t.get("active", True):
            continue
        out.append(dict(t))
    return out


def deactivate_token_by_value(user_id: str, expo_push_token: str) -> bool:
    """Deactivate a token by user_id + expo_push_token. Returns True if found and deactivated."""
    return unregister_push_token({"user_id": user_id, "expo_push_token": expo_push_token}).get("ok", False)


def list_users_with_active_push_tokens(limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Return distinct users with at least one active push token, for batch sending.
    Each row: user_id, active_tokens_count, last_seen_at (most recent), updated_at.
    """
    with _LOCK:
        store = _load_store()
    tokens = store.get("tokens") or []
    if not isinstance(tokens, list):
        return []

    by_user: Dict[str, Dict[str, Any]] = {}
    for t in tokens:
        if not isinstance(t, dict):
            continue
        if not t.get("active", True):
            continue
        token = _normalize_space(t.get("expo_push_token"))
        if not token or not token.startswith("ExponentPushToken["):
            continue
        uid = _normalize_space(t.get("user_id"))
        if not uid:
            continue
        if uid not in by_user:
            by_user[uid] = {
                "user_id": uid,
                "active_tokens_count": 0,
                "last_seen_at": None,
                "updated_at": None,
            }
        by_user[uid]["active_tokens_count"] += 1
        for key in ("last_seen_at", "updated_at"):
            val = t.get(key) or ""
            if val:
                existing = by_user[uid][key]
                if not existing or (val > existing):
                    by_user[uid][key] = val

    out = list(by_user.values())
    out.sort(key=lambda r: (r.get("last_seen_at") or r.get("updated_at") or ""), reverse=True)
    return out[: max(1, min(10000, limit))]

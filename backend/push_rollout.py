"""
Push rollout gating: allowlist and mode checks for safe real-push sending.
"""

from __future__ import annotations

import os
from typing import Set, Tuple

_EXPANDED_IDS: Set[str] | None = None

MODES = ("disabled", "allowlist_only", "all_enabled_users")


def _normalize(v: str) -> str:
    return " ".join(str(v or "").strip().split())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def get_push_test_user_ids() -> Set[str]:
    """Return set of user IDs allowed for real push when mode is allowlist_only."""
    global _EXPANDED_IDS
    if _EXPANDED_IDS is not None:
        return _EXPANDED_IDS
    raw = os.getenv("PUSH_TEST_USER_IDS", "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    _EXPANDED_IDS = set(parts)
    return _EXPANDED_IDS


def get_push_rollout_mode() -> str:
    """Return PUSH_REAL_SEND_MODE: disabled, allowlist_only, all_enabled_users."""
    raw = str(os.getenv("PUSH_REAL_SEND_MODE", "disabled")).strip().lower()
    if raw in MODES:
        return raw
    return "disabled"


def is_user_allowed_for_real_push(user_id: str) -> bool:
    """True if user is in allowlist (when mode is allowlist_only) or mode is all_enabled_users."""
    mode = get_push_rollout_mode()
    if mode == "all_enabled_users":
        return True
    if mode == "allowlist_only":
        uid = _normalize(user_id)
        return uid in get_push_test_user_ids()
    return False


def can_send_real_push(user_id: str, *, dry_run: bool) -> Tuple[bool, str]:
    """
    Returns (allowed, reason).
    Reason examples:
      dry_run
      push_disabled
      rollout_disabled
      allowlist_blocked
      allowed_allowlist
      allowed_global
    """
    if dry_run:
        return (True, "dry_run")

    push_enabled = _env_bool("EXPO_PUSH_SENDING_ENABLED", False)
    if not push_enabled:
        return (False, "push_disabled")

    mode = get_push_rollout_mode()
    if mode == "disabled":
        return (False, "rollout_disabled")
    if mode == "allowlist_only":
        if is_user_allowed_for_real_push(user_id):
            return (True, "allowed_allowlist")
        return (False, "allowlist_blocked")
    if mode == "all_enabled_users":
        return (True, "allowed_global")
    return (False, "rollout_disabled")


def reset_cache_for_tests() -> None:
    """Reset cached allowlist (for tests)."""
    global _EXPANDED_IDS
    _EXPANDED_IDS = None

"""
Push rollout gating: staged rollout modes, active-user eligibility, percentage rollout.
Production-safe defaults. Extends allowlist-only to support iOS release path.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set, Tuple

_EXPANDED_IDS: Set[str] | None = None

MODES = ("disabled", "allowlist_only", "active_users_only", "percentage", "all")


def _normalize(v: str) -> str:
    return " ".join(str(v or "").strip().split())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int, min_val: int = 0, max_val: int = 999) -> int:
    try:
        v = int(os.getenv(name, default))
        return max(min_val, min(max_val, v))
    except (TypeError, ValueError):
        return default


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
    """Return PUSH_REAL_SEND_MODE. Default allowlist_only when sending enabled but mode missing."""
    raw = str(os.getenv("PUSH_REAL_SEND_MODE", "")).strip().lower()
    if raw == "all_enabled_users":
        return "all"
    if raw in MODES:
        return raw
    push_enabled = _env_bool("EXPO_PUSH_SENDING_ENABLED", False)
    if push_enabled:
        return "allowlist_only"
    return "disabled"


def get_rollout_percent() -> int:
    """PUSH_ROLLOUT_PERCENT, clamped 0-100. Default 0."""
    return _env_int("PUSH_ROLLOUT_PERCENT", 0, 0, 100)


def get_active_user_days() -> int:
    """PUSH_ACTIVE_USER_DAYS. Default 7."""
    return _env_int("PUSH_ACTIVE_USER_DAYS", 7, 1, 90)


def get_max_per_6h() -> int:
    """PUSH_MAX_PER_6H. Default 1."""
    return _env_int("PUSH_MAX_PER_6H", 1, 0, 20)


def get_max_per_24h() -> int:
    """PUSH_MAX_PER_24H. Default 2."""
    return _env_int("PUSH_MAX_PER_24H", 2, 0, 50)


def is_user_in_rollout_percentage(user_id: str, percent: int) -> bool:
    """
    Deterministic percentage rollout. user_id hashed into bucket 0-99.
    percent=10 -> buckets 0-9 eligible. Same user always same result.
    """
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    uid = _normalize(user_id)
    if not uid:
        return False
    h = hashlib.sha256(uid.encode("utf-8")).hexdigest()
    bucket = int(h[:8], 16) % 100
    return bucket < percent


def get_user_percentage_bucket(user_id: str) -> int:
    """Return 0-99 bucket for user_id. Deterministic."""
    uid = _normalize(user_id)
    if not uid:
        return 0
    h = hashlib.sha256(uid.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


def is_user_recently_active(user_id: str, within_days: int = 7) -> bool:
    """
    True if user has app activity in last within_days.
    Uses: meal_decision_events (recommendation_opened, etc.) or token last_seen_at/updated_at.
    """
    if not user_id or not within_days:
        return False
    uid = _normalize(user_id)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=within_days)).isoformat()

    try:
        from meal_decision_event_store import list_meal_decision_events
        events = list_meal_decision_events(user_id=uid, limit=100)
        for e in events:
            created = e.get("created_at") or ""
            if created >= cutoff:
                return True
    except Exception:
        pass

    try:
        from push_token_store import list_tokens_for_user
        tokens = list_tokens_for_user(uid, active_only=True)
        for t in tokens:
            for key in ("last_seen_at", "updated_at"):
                ts = t.get(key) or ""
                if ts and ts >= cutoff:
                    return True
    except Exception:
        pass

    return False


def get_user_push_eligibility(user_id: str) -> Dict[str, Any]:
    """
    Return eligibility dict: has_token, active, fatigue_6h, fatigue_24h, in_allowlist,
    percentage_bucket, percentage_allowed, eligibility_reason.
    """
    uid = _normalize(user_id)
    out: Dict[str, Any] = {
        "has_token": False,
        "active": False,
        "fatigue_6h_ok": True,
        "fatigue_24h_ok": True,
        "in_allowlist": False,
        "percentage_bucket": None,
        "percentage_allowed": None,
        "eligibility_reason": "",
    }

    tokens = []
    try:
        from push_token_store import list_tokens_for_user
        tokens = list_tokens_for_user(uid, active_only=True)
        tokens = [t for t in tokens if (t.get("expo_push_token") or "").startswith("ExponentPushToken[")]
    except Exception:
        pass
    out["has_token"] = len(tokens) > 0
    if not out["has_token"]:
        out["eligibility_reason"] = "no_tokens"
        return out

    out["in_allowlist"] = uid in get_push_test_user_ids()
    out["percentage_bucket"] = get_user_percentage_bucket(uid)
    pct = get_rollout_percent()
    out["percentage_allowed"] = is_user_in_rollout_percentage(uid, pct)

    active_days = get_active_user_days()
    out["active"] = is_user_recently_active(uid, within_days=active_days)

    try:
        from push_delivery_store import list_deliveries
        now = datetime.now(timezone.utc)
        cut_6h = (now - timedelta(hours=6)).isoformat()
        cut_24h = (now - timedelta(hours=24)).isoformat()
        recent = list_deliveries(
            user_id=uid,
            dry_run=False,
            start_date=cut_24h,
            limit=100,
        )
        sent = [d for d in recent if d.get("status") in ("sent", "receipt_ok", "receipt_error")]
        count_6h = sum(1 for d in sent if (d.get("created_at") or "") >= cut_6h)
        count_24h = len(sent)
        out["fatigue_6h_ok"] = count_6h < get_max_per_6h()
        out["fatigue_24h_ok"] = count_24h < get_max_per_24h()
        out["recent_sent_6h"] = count_6h
        out["recent_sent_24h"] = count_24h
    except Exception:
        pass

    if not out["eligibility_reason"]:
        if not out["fatigue_6h_ok"]:
            out["eligibility_reason"] = "fatigue_limit_6h"
        elif not out["fatigue_24h_ok"]:
            out["eligibility_reason"] = "fatigue_limit_24h"
        elif out["active"] and out["has_token"]:
            out["eligibility_reason"] = "eligible"
        else:
            out["eligibility_reason"] = "inactive_or_no_token"

    return out


def is_user_allowed_for_real_push(user_id: str) -> bool:
    """True if user is in allowlist (when mode is allowlist_only) or mode allows them."""
    mode = get_push_rollout_mode()
    if mode == "all":
        return True
    if mode == "allowlist_only":
        uid = _normalize(user_id)
        return uid in get_push_test_user_ids()
    if mode == "active_users_only":
        return is_user_recently_active(user_id, within_days=get_active_user_days())
    if mode == "percentage":
        return is_user_in_rollout_percentage(user_id, get_rollout_percent())
    return False


def can_send_real_push(
    user_id: str,
    *,
    dry_run: bool,
    user_activity: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Returns (allowed, reason).
    dry_run always allowed.
    Reasons: dry_run, allowed_allowlist, allowed_active_user, allowed_percentage, allowed_all,
             allowlist_blocked, inactive_user, percentage_blocked, push_disabled, rollout_disabled,
             no_tokens, fatigue_limit_6h, fatigue_limit_24h.
    """
    if dry_run:
        return (True, "dry_run")

    push_enabled = _env_bool("EXPO_PUSH_SENDING_ENABLED", False)
    if not push_enabled:
        return (False, "push_disabled")

    mode = get_push_rollout_mode()
    if mode == "disabled":
        return (False, "rollout_disabled")

    uid = _normalize(user_id)
    if not uid:
        return (False, "invalid_user_id")

    eligibility = user_activity if user_activity else get_user_push_eligibility(uid)

    if not eligibility.get("has_token"):
        return (False, "no_tokens")

    if not eligibility.get("fatigue_6h_ok"):
        return (False, "fatigue_limit_6h")
    if not eligibility.get("fatigue_24h_ok"):
        return (False, "fatigue_limit_24h")

    if mode == "allowlist_only":
        if uid in get_push_test_user_ids():
            return (True, "allowed_allowlist")
        return (False, "allowlist_blocked")

    if mode == "active_users_only":
        if eligibility.get("active"):
            return (True, "allowed_active_user")
        return (False, "inactive_user")

    if mode == "percentage":
        pct = get_rollout_percent()
        if pct <= 0:
            return (False, "rollout_disabled")
        if is_user_in_rollout_percentage(uid, pct):
            return (True, "allowed_percentage")
        return (False, "percentage_blocked")

    if mode == "all":
        return (True, "allowed_all")

    return (False, "rollout_disabled")


def get_rollout_status() -> Dict[str, Any]:
    """Summary for GET /push/rollout/status."""
    mode = get_push_rollout_mode()
    out: Dict[str, Any] = {
        "sending_enabled": _env_bool("EXPO_PUSH_SENDING_ENABLED", False),
        "rollout_mode": mode,
        "rollout_percent": get_rollout_percent(),
        "active_user_days": get_active_user_days(),
        "max_per_6h": get_max_per_6h(),
        "max_per_24h": get_max_per_24h(),
        "allowlist_count": len(get_push_test_user_ids()),
    }

    try:
        from push_delivery_store import list_recent_deliveries, STATUS_SENT, STATUS_RECEIPT_OK, STATUS_RECEIPT_ERROR
        recent = list_recent_deliveries(limit=500, dry_run=False)
        out["recent_sent_count"] = sum(1 for d in recent if d.get("status") in (STATUS_SENT, STATUS_RECEIPT_OK, STATUS_RECEIPT_ERROR))
        out["recent_receipt_ok_count"] = sum(1 for d in recent if d.get("status") == STATUS_RECEIPT_OK)
        out["recent_receipt_error_count"] = sum(1 for d in recent if d.get("status") == STATUS_RECEIPT_ERROR)
        out["recent_no_token_count"] = 0
        out["recent_duplicate_suppressed_count"] = 0
    except Exception:
        out["recent_sent_count"] = None
        out["recent_receipt_ok_count"] = None
        out["recent_receipt_error_count"] = None

    return out


def reset_cache_for_tests() -> None:
    """Reset cached allowlist (for tests)."""
    global _EXPANDED_IDS
    _EXPANDED_IDS = None

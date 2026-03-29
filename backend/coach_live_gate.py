"""
Gating for realtime AI coach "calls" (Pro / Infinite, optional beta allowlist).
Keep PLAN_ORDER in sync with main.PLAN_ORDER.
"""
from __future__ import annotations

import os
from typing import Set, Tuple

# Must match main.DEFAULT_PLAN and main.PLAN_ORDER.
DEFAULT_PLAN = "free"
PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"]

COACH_LIVE_REQUIRED_PLAN = "pro"


def plan_at_least(current: str, required: str) -> bool:
    try:
        return PLAN_ORDER.index((current or DEFAULT_PLAN).lower()) >= PLAN_ORDER.index(required.lower())
    except ValueError:
        return False


def _env_bool(name: str, default: bool = False) -> bool:
    text = str(os.getenv(name, "") or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def coach_live_server_enabled() -> bool:
    return _env_bool("COACH_LIVE_CALL_ENABLED", False)


def coach_live_beta_user_ids() -> Set[str]:
    raw = str(os.getenv("COACH_LIVE_CALL_BETA_USER_IDS", "") or "").strip()
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def coach_live_eligible(user_id: str, current_plan: str) -> Tuple[bool, str, str, bool]:
    """
    Returns (eligible, plan, reason, beta_override).
    reason: feature_disabled | beta_allowlist | plan_ok | upgrade_required
    """
    plan = (current_plan or DEFAULT_PLAN).lower()
    if not coach_live_server_enabled():
        return False, plan, "feature_disabled", False
    uid = str(user_id or "").strip()
    if uid and uid in coach_live_beta_user_ids():
        return True, plan, "beta_allowlist", True
    if plan_at_least(plan, COACH_LIVE_REQUIRED_PLAN):
        return True, plan, "plan_ok", False
    return False, plan, "upgrade_required", False

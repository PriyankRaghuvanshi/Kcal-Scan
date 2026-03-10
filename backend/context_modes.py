"""
Context inference for time-of-day and situational ranking modes.

Deterministic inference from user context: post-workout, late-night,
remaining calories/protein, local hour. No ML, no LLM.
"""
from __future__ import annotations

from typing import Any, Dict


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        x = float(v)
        return int(round(x))
    except Exception:
        return default


# Supported flags
FLAG_POST_WORKOUT_RECOVERY = "post_workout_recovery"
FLAG_LATE_NIGHT_DAMAGE_CONTROL = "late_night_damage_control"
FLAG_LOW_CALORIE_REMAINING = "low_calorie_remaining"
FLAG_HIGH_PROTEIN_RECOVERY_NEEDED = "high_protein_recovery_needed"
FLAG_BREAKFAST_MODE = "breakfast_mode"
FLAG_LUNCH_MODE = "lunch_mode"
FLAG_DINNER_MODE = "dinner_mode"
FLAG_POOR_SLEEP = "poor_sleep_flag"
FLAG_HIGH_CRAVING_RISK = "high_craving_risk_flag"


def infer_context_mode(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Infer primary context mode and flags from user/session context.

    Args:
        context: Dict with optional keys:
            - context_mode_override: str (explicit primary mode, wins if set)
            - post_workout: bool
            - late_night: bool
            - poor_sleep_flag: bool
            - high_craving_risk_flag: bool
            - remaining_calories: float
            - remaining_protein_g: float
            - local_hour: int 0..23

    Returns:
        {
            "context_mode": primary_mode,
            "context_flags": {flag_name: bool, ...},
            "context_reason": "comma,separated,flags"
        }
    """
    override = str(context.get("context_mode_override") or "").strip().lower()
    post_workout = bool(context.get("post_workout"))
    late_night = bool(context.get("late_night"))
    poor_sleep = bool(context.get("poor_sleep_flag"))
    high_craving = bool(context.get("high_craving_risk_flag"))
    remaining_cal = _safe_float(context.get("remaining_calories"), 0.0)
    remaining_protein = _safe_float(context.get("remaining_protein_g"), 0.0)
    local_hour = _safe_int(context.get("local_hour"), 12)

    flags: Dict[str, bool] = {}

    # post_workout_recovery
    flags[FLAG_POST_WORKOUT_RECOVERY] = post_workout or (override == "post_workout_recovery")

    # late_night_damage_control
    flags[FLAG_LATE_NIGHT_DAMAGE_CONTROL] = late_night or (local_hour >= 21)

    # low_calorie_remaining
    flags[FLAG_LOW_CALORIE_REMAINING] = remaining_cal <= 250 and remaining_cal > 0

    # high_protein_recovery_needed
    flags[FLAG_HIGH_PROTEIN_RECOVERY_NEEDED] = remaining_protein >= 35

    # breakfast_mode: 5 <= hour <= 10
    flags[FLAG_BREAKFAST_MODE] = 5 <= local_hour <= 10

    # lunch_mode: 11 <= hour <= 15
    flags[FLAG_LUNCH_MODE] = 11 <= local_hour <= 15

    # dinner_mode: 16 <= hour <= 20
    flags[FLAG_DINNER_MODE] = 16 <= local_hour <= 20

    # optional flags (pass-through)
    flags[FLAG_POOR_SLEEP] = poor_sleep
    flags[FLAG_HIGH_CRAVING_RISK] = high_craving

    # Primary mode: explicit override wins; else priority order
    if override and override in (
        "post_workout_recovery",
        "late_night_damage_control",
        "breakfast_mode",
        "lunch_mode",
        "dinner_mode",
        "default",
    ):
        context_mode = override
    elif flags[FLAG_POST_WORKOUT_RECOVERY]:
        context_mode = "post_workout_recovery"
    elif flags[FLAG_LATE_NIGHT_DAMAGE_CONTROL]:
        context_mode = "late_night_damage_control"
    elif flags[FLAG_BREAKFAST_MODE]:
        context_mode = "breakfast_mode"
    elif flags[FLAG_LUNCH_MODE]:
        context_mode = "lunch_mode"
    elif flags[FLAG_DINNER_MODE]:
        context_mode = "dinner_mode"
    else:
        context_mode = "default"

    active_flags = [k for k, v in flags.items() if v]
    context_reason = ",".join(active_flags) if active_flags else "default"

    return {
        "context_mode": context_mode,
        "context_flags": flags,
        "context_reason": context_reason,
    }

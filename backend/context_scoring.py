"""
Context-aware scoring modifier for situational ranking.

Bounded layer on top of meal-first engine. Adapts to post-workout, late-night,
low calories left, high protein needed, breakfast/lunch/dinner, optional
poor-sleep / high-craving-risk. No ML, no LLM. Cap: context_net_100 in [-8, +8].
"""
from __future__ import annotations

from typing import Any, Dict

from context_modes import (
    FLAG_BREAKFAST_MODE,
    FLAG_DINNER_MODE,
    FLAG_HIGH_CRAVING_RISK,
    FLAG_HIGH_PROTEIN_RECOVERY_NEEDED,
    FLAG_LATE_NIGHT_DAMAGE_CONTROL,
    FLAG_LOW_CALORIE_REMAINING,
    FLAG_LUNCH_MODE,
    FLAG_POOR_SLEEP,
    FLAG_POST_WORKOUT_RECOVERY,
)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _text_lower(item_name: str, place_name: str = "") -> str:
    return f"{str(item_name or '').strip().lower()} {str(place_name or '').strip().lower()}"


# Recovery-friendly meal tokens
RECOVERY_POSITIVE = (
    "grilled", "tandoori", "eggs", "egg", "wrap", "sub", "dal", "protein",
    "chicken", "turkey", "fish", "tofu", "paneer", "bowl", "idli", "dosa", "sambar",
)
RECOVERY_NEGATIVE = ("sugary", "juice", "pastry", "dessert", "muffin", "donut")
BREAKFAST_POSITIVE = ("eggs", "egg", "omelette", "idli", "sambar", "yogurt", "wrap", "protein")
BREAKFAST_NEGATIVE = ("pastry", "muffin", "coffee only", "dessert", "donut")
COMBO_HEAVY = ("combo", "pizza+side", "burger+fries", "burger and fries", "meal deal", "bucket")
DESSERT_HEAVY = ("dessert", "pastry", "sugary", "creamy curry", "stuffed", "cheesy dip")


def _is_recovery_friendly(text: str) -> bool:
    return any(t in text for t in RECOVERY_POSITIVE)


def _is_recovery_negative(text: str) -> bool:
    return any(t in text for t in RECOVERY_NEGATIVE)


def _is_breakfast_friendly(text: str) -> bool:
    return any(t in text for t in BREAKFAST_POSITIVE)


def _is_breakfast_negative(text: str) -> bool:
    return any(t in text for t in BREAKFAST_NEGATIVE)


def _is_combo_heavy(text: str) -> bool:
    return any(t in text for t in COMBO_HEAVY)


def _is_dessert_heavy(text: str) -> bool:
    return any(t in text for t in DESSERT_HEAVY)


def compute_context_modifier(
    place_profile: Dict[str, Any],
    context_info: Dict[str, Any],
    user_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute bounded context modifier for a place.

    Args:
        place_profile: Place/meal profile with meal_fitness_score_100, estimated_calories,
            estimated_protein_g, food_quality_score_100, protein_density_score_100, etc.
        context_info: From infer_context_mode (context_mode, context_flags, context_reason)
            plus raw inputs (remaining_calories, remaining_protein_g).
        user_context: Full user context (for compatibility; context_info has what we need).

    Returns:
        {
            "context_bonus_100": int,
            "context_penalty_100": int,
            "context_net_100": int,
            "context_mode": str,
            "context_reason": str,
            "context_applied": bool,
            "context_components": dict,
        }
        context_net_100 is clamped to [-8, +8].
    """
    flags = context_info.get("context_flags") or {}
    remaining_cal = _safe_float(context_info.get("remaining_calories"), 0.0)
    remaining_protein = _safe_float(context_info.get("remaining_protein_g"), 0.0)

    meal_fitness = _safe_float(place_profile.get("meal_fitness_score_100"), 50.0)
    est_cal = _safe_float(place_profile.get("estimated_calories"), 520.0)
    est_protein = _safe_float(place_profile.get("estimated_protein_g"), 32.0)
    food_quality = _safe_float(place_profile.get("food_quality_score_100"), 50.0)
    protein_density = _safe_float(place_profile.get("protein_density_score_100"), 50.0)
    satiety = _safe_float(
        (place_profile.get("score_breakdown") or {}).get("satiety"),
        50.0,
    )

    item_name = str(
        place_profile.get("recommended_order")
        or place_profile.get("best_order")
        or ""
    ).strip() or "Lighter menu option"
    place_name = str(place_profile.get("name") or "")
    text = _text_lower(item_name, place_name)

    components: Dict[str, int] = {}
    bonus = 0
    penalty = 0

    # A. Post-workout recovery
    if flags.get(FLAG_POST_WORKOUT_RECOVERY):
        if est_protein >= 40:
            bonus += 3
            components["post_workout"] = 3
        elif est_protein >= 30:
            bonus += 2
            components["post_workout"] = 2
        elif protein_density >= 70:
            bonus += 2
            components["post_workout"] = 2
        elif _is_recovery_friendly(text):
            bonus += 1
            components["post_workout"] = 1
        elif est_protein < 20:
            penalty += 2
            components["post_workout"] = -2
        elif _is_recovery_negative(text):
            penalty += 2
            components["post_workout"] = -2
        elif any(t in text for t in ("pastry", "dessert")):
            penalty += 3
            components["post_workout"] = -3

    # B. Late-night damage control
    if flags.get(FLAG_LATE_NIGHT_DAMAGE_CONTROL):
        ln_bonus = 0
        ln_penalty = 0
        if est_cal <= 450:
            ln_bonus += 2
        if satiety >= 60:
            ln_bonus += 2
        elif satiety >= 50:
            ln_bonus += 1
        if est_protein >= 20:
            ln_bonus += 1
        if food_quality >= 60 and not _is_combo_heavy(text):
            ln_bonus += 1
        if _is_combo_heavy(text):
            ln_penalty += 3
        if _is_dessert_heavy(text):
            ln_penalty += 3
        if satiety < 40 and est_cal > 500:
            ln_penalty += 2
        ln_net = ln_bonus - ln_penalty
        bonus += ln_bonus
        penalty += ln_penalty
        if ln_net != 0:
            components["late_night"] = ln_net

    # C. Low calories remaining
    if flags.get(FLAG_LOW_CALORIE_REMAINING) and remaining_cal > 0:
        if est_cal <= remaining_cal:
            bonus += 2
            components["low_cal_remaining"] = 2
        elif est_cal <= remaining_cal + 50:
            bonus += 1
            components["low_cal_remaining"] = 1
        elif est_cal > remaining_cal + 200:
            penalty += 5
            components["low_cal_remaining"] = -5
        elif est_cal > remaining_cal + 100:
            penalty += 3
            components["low_cal_remaining"] = -3

    # D. High protein recovery needed
    if flags.get(FLAG_HIGH_PROTEIN_RECOVERY_NEEDED):
        # Avoid double-counting with post_workout
        if not flags.get(FLAG_POST_WORKOUT_RECOVERY):
            if est_protein >= 40:
                bonus += 3
                components["high_protein_needed"] = 3
            elif est_protein >= 30:
                bonus += 2
                components["high_protein_needed"] = 2
            elif protein_density >= 70:
                bonus += 2
                components["high_protein_needed"] = 2
            elif est_protein < 15:
                penalty += 2
                components["high_protein_needed"] = -2
            elif remaining_protein >= 40 and est_protein < 20:
                penalty += 3
                components["high_protein_needed"] = -3

    # E. Breakfast mode
    if flags.get(FLAG_BREAKFAST_MODE):
        if _is_breakfast_friendly(text):
            bonus += 2
            components["breakfast"] = 2
        elif _is_breakfast_negative(text):
            penalty += 2
            components["breakfast"] = -2

    # F. Lunch mode
    if flags.get(FLAG_LUNCH_MODE):
        if est_protein >= 25 and satiety >= 55 and food_quality >= 55:
            bonus += 2
            components["lunch"] = 2
        elif est_protein >= 20 and satiety >= 50:
            bonus += 1
            components["lunch"] = 1

    # G. Dinner mode
    if flags.get(FLAG_DINNER_MODE):
        dn_bonus = 0
        dn_penalty = 0
        if est_protein >= 25 and food_quality >= 55 and not _is_combo_heavy(text):
            dn_bonus += 2
        elif est_protein >= 20 and food_quality >= 50 and not _is_combo_heavy(text):
            dn_bonus += 1
        if _is_combo_heavy(text) or (est_cal > 800 and _is_dessert_heavy(text)):
            dn_penalty += 3
        elif est_cal > 700 and _is_combo_heavy(text):
            dn_penalty += 2
        bonus += dn_bonus
        penalty += dn_penalty
        if dn_bonus - dn_penalty != 0:
            components["dinner"] = dn_bonus - dn_penalty

    # H. Optional flags
    if flags.get(FLAG_POOR_SLEEP):
        if satiety >= 55 and not _is_dessert_heavy(text):
            bonus += 1
            components["poor_sleep"] = 1
    if flags.get(FLAG_HIGH_CRAVING_RISK):
        hc_net = 0
        if satiety >= 55 and not _is_combo_heavy(text):
            hc_net += 1
        if _is_combo_heavy(text) and food_quality < 45:
            hc_net -= 2
        elif _is_combo_heavy(text):
            hc_net -= 1
        if hc_net != 0:
            bonus += max(0, hc_net)
            penalty += max(0, -hc_net)
            components["high_craving"] = hc_net

    # Safeguards: context must not rescue weak meals
    if meal_fitness < 50:
        bonus = min(bonus, 2)
    if food_quality < 40:
        bonus = int(bonus * 0.5)
    if protein_density < 35 and (flags.get(FLAG_POST_WORKOUT_RECOVERY) or flags.get(FLAG_HIGH_PROTEIN_RECOVERY_NEEDED)):
        bonus = max(0, bonus - 1)

    net = bonus - penalty
    net = max(-8, min(8, int(round(net))))

    if net > 0:
        context_bonus_100 = net
        context_penalty_100 = 0
        reason_str = "positive:" + ",".join(k for k, v in components.items() if v > 0)
    elif net < 0:
        context_bonus_100 = 0
        context_penalty_100 = -net
        reason_str = "negative:" + ",".join(k for k, v in components.items() if v < 0)
    else:
        context_bonus_100 = 0
        context_penalty_100 = 0
        reason_str = "neutral"

    return {
        "context_bonus_100": context_bonus_100,
        "context_penalty_100": context_penalty_100,
        "context_net_100": net,
        "context_mode": str(context_info.get("context_mode") or "default"),
        "context_reason": reason_str,
        "context_applied": net != 0,
        "context_components": components,
    }

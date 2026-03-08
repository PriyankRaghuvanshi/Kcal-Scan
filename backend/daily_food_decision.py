from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from lunch_decision import _place_profile
from nutrition_mode import NutritionMode
from personalization_profiles import (
    normalize_personalization_goal,
    personalization_goal_value,
)


DAILY_DECISION_VERSION = "v2"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return int(default)


def _safe_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _meal_window_for_hour(hour: int) -> str:
    h = int(max(0, min(23, int(hour))))
    if 5 <= h <= 10:
        return "breakfast"
    if 11 <= h <= 14:
        return "lunch"
    if 15 <= h <= 17:
        return "snack"
    if 18 <= h <= 22:
        return "dinner"
    return "snack"


def _headline_for_window(window: str) -> str:
    token = str(window or "").strip().lower()
    if token == "breakfast":
        return "Best breakfast near you"
    if token == "lunch":
        return "Best lunch near you"
    if token == "dinner":
        return "Best dinner near you"
    return "Best snack right now"


def _decision_type_for_window(window: str) -> str:
    token = str(window or "").strip().lower()
    if token == "breakfast":
        return "best_breakfast"
    if token == "dinner":
        return "best_dinner"
    if token == "snack":
        return "best_next_snack"
    return "best_next_meal"


def _build_profiles(
    *,
    nearby_places: List[Dict[str, Any]],
    origin_lat: float,
    origin_lng: float,
    mode: NutritionMode,
    personalization_goal: Any,
    remaining_calories: Any,
    remaining_protein_g: Any,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for place in nearby_places or []:
        if not isinstance(place, dict):
            continue
        try:
            profile = _place_profile(
                place,
                origin_lat=float(_safe_float(origin_lat, 0.0) or 0.0),
                origin_lng=float(_safe_float(origin_lng, 0.0) or 0.0),
                mode=mode,
                personalization_goal=personalization_goal,
                remaining_calories=remaining_calories,
                remaining_protein_g=remaining_protein_g,
            )
            out.append(profile)
        except Exception:
            # Place-level errors should never break decisioning.
            continue
    return out


def _context_adjusted_rank(
    profile: Dict[str, Any],
    *,
    meal_window: str,
    remaining_calories: Optional[float],
    remaining_protein_g: Optional[float],
    cut_mode: bool,
) -> float:
    calories = float(_safe_float(profile.get("estimated_calories"), 0.0) or 0.0)
    protein = float(_safe_float(profile.get("estimated_protein_g"), 0.0) or 0.0)
    distance = float(_safe_float(profile.get("distance_meters"), 0.0) or 0.0)
    fit = profile.get("fit_for_today")

    health = _clamp(_safe_float(profile.get("health_score"), 0.0), 0.0, 100.0)
    daily_fit = _clamp(_safe_float(profile.get("daily_fit_score"), 0.0), 0.0, 1.0) * 100.0
    order_conf = _clamp(_safe_float(profile.get("order_confidence"), 0.0), 0.0, 1.0) * 100.0
    protein_density = _clamp((protein / max(1.0, calories)) * 1500.0, 0.0, 100.0)
    fit_bonus = 10.0 if fit is True else -10.0 if fit is False else 0.0
    distance_penalty = min(18.0, distance / 200.0)

    score = (health * 0.34) + (daily_fit * 0.24) + (order_conf * 0.18) + (protein_density * 0.24)
    score += fit_bonus
    score -= distance_penalty

    window = str(meal_window or "").strip().lower()
    if window == "breakfast":
        if calories <= 600:
            score += 6.0
        if protein >= 28:
            score += 4.0
    elif window == "snack":
        if calories <= 420:
            score += 9.0
        elif calories >= 620:
            score -= 8.0
    elif window == "dinner":
        if calories <= 650:
            score += 6.0
        elif calories >= 820:
            score -= 10.0

    if remaining_calories is not None:
        rem_cal = max(0.0, float(remaining_calories))
        if rem_cal <= 500:
            if calories <= max(260.0, rem_cal):
                score += 10.0
            elif calories > rem_cal + 120.0:
                score -= 14.0
        elif rem_cal >= 900 and protein >= 32:
            score += 3.0

    if remaining_protein_g is not None:
        rem_protein = max(0.0, float(remaining_protein_g))
        if rem_protein >= 45:
            score += min(14.0, protein / 3.5)
        elif rem_protein >= 25:
            score += min(8.0, protein / 5.0)

    if cut_mode:
        if calories <= 620 and protein >= 30:
            score += 7.0
        if calories >= 780:
            score -= 10.0

    return float(round(_clamp(score, 0.0, 100.0), 2))


def _to_recommendation(
    profile: Dict[str, Any],
    *,
    decision_type: str,
    headline: str,
    reason_fallback: str,
) -> Dict[str, Any]:
    return {
        "decision_type": str(decision_type or "").strip(),
        "headline": str(headline or "").strip(),
        "place_name": str(profile.get("name") or "Nearby option").strip(),
        "place_id": str(profile.get("place_id") or "").strip(),
        "recommended_order": str(profile.get("recommended_order") or "Lighter menu option").strip(),
        "estimated_calories": int(max(0, _safe_int(profile.get("estimated_calories"), 0))),
        "estimated_protein_g": int(max(0, _safe_int(profile.get("estimated_protein_g"), 0))),
        "fit_for_today": profile.get("fit_for_today"),
        "why_this_works": str(profile.get("short_reason") or reason_fallback).strip(),
        "decision_confidence": round(_clamp(_safe_float(profile.get("decision_confidence"), 0.62), 0.2, 0.95), 2),
    }


def _pick_primary(
    profiles: List[Dict[str, Any]],
    *,
    meal_window: str,
    remaining_calories: Optional[float],
    remaining_protein_g: Optional[float],
    cut_mode: bool,
) -> Optional[Dict[str, Any]]:
    if not profiles:
        return None
    ranked = sorted(
        profiles,
        key=lambda row: _context_adjusted_rank(
            row,
            meal_window=meal_window,
            remaining_calories=remaining_calories,
            remaining_protein_g=remaining_protein_g,
            cut_mode=cut_mode,
        ),
        reverse=True,
    )
    return ranked[0]


def _pick_protein_catchup(
    profiles: List[Dict[str, Any]],
    *,
    skip_place: str,
) -> Optional[Dict[str, Any]]:
    candidates = [
        row
        for row in profiles
        if str(row.get("name") or "").strip() and str(row.get("name") or "").strip() != skip_place
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            _safe_float(row.get("estimated_protein_g"), 0.0),
            -_safe_float(row.get("estimated_calories"), 9_999.0),
            _safe_float(row.get("daily_fit_score"), 0.0),
        ),
        reverse=True,
    )
    return candidates[0]


def _pick_lighter_recovery(
    profiles: List[Dict[str, Any]],
    *,
    skip_place: str,
) -> Optional[Dict[str, Any]]:
    candidates = [
        row
        for row in profiles
        if str(row.get("name") or "").strip() and str(row.get("name") or "").strip() != skip_place
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            _safe_float(row.get("estimated_calories"), 9_999.0),
            -_safe_float(row.get("estimated_protein_g"), 0.0),
            _safe_float(row.get("distance_meters"), 9_999_999.0),
        )
    )
    return candidates[0]


def build_daily_decision_response(
    *,
    nearby_places: List[Dict[str, Any]],
    origin_lat: float,
    origin_lng: float,
    remaining_calories: Any = None,
    remaining_protein_g: Any = None,
    target_calories: Any = None,
    consumed_calories: Any = None,
    target_protein_g: Any = None,
    consumed_protein_g: Any = None,
    current_hour: Any = None,
    goal: Any = None,
    cut_mode: bool = False,
) -> Dict[str, Any]:
    resolved_goal = normalize_personalization_goal(goal)
    goal_value = personalization_goal_value(resolved_goal)
    mode = NutritionMode.CUT if bool(cut_mode) else NutritionMode.DEFAULT

    rem_cal = _safe_optional_float(remaining_calories)
    rem_protein = _safe_optional_float(remaining_protein_g)

    if rem_cal is None:
        t_cal = _safe_optional_float(target_calories)
        c_cal = _safe_optional_float(consumed_calories)
        if t_cal is not None and c_cal is not None:
            rem_cal = max(0.0, float(t_cal) - float(c_cal))
    if rem_protein is None:
        t_protein = _safe_optional_float(target_protein_g)
        c_protein = _safe_optional_float(consumed_protein_g)
        if t_protein is not None and c_protein is not None:
            rem_protein = max(0.0, float(t_protein) - float(c_protein))

    now_hour = _safe_int(current_hour, dt.datetime.now().hour)
    now_hour = int(max(0, min(23, now_hour)))
    meal_window = _meal_window_for_hour(now_hour)

    profiles = _build_profiles(
        nearby_places=nearby_places,
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        mode=mode,
        personalization_goal=resolved_goal,
        remaining_calories=rem_cal,
        remaining_protein_g=rem_protein,
    )

    primary = _pick_primary(
        profiles,
        meal_window=meal_window,
        remaining_calories=rem_cal,
        remaining_protein_g=rem_protein,
        cut_mode=bool(cut_mode),
    )

    next_best_meal = None
    next_best_snack = None
    protein_catchup_option = None
    lighter_recovery_option = None
    secondary: List[Dict[str, Any]] = []

    if primary:
        headline = _headline_for_window(meal_window)
        primary_decision_type = _decision_type_for_window(meal_window)
        if rem_cal is not None and rem_cal <= 420:
            headline = "Lighter option right now"
            primary_decision_type = "lighter_recovery"
        elif rem_protein is not None and rem_protein >= 40:
            headline = "Strong protein option right now"
            primary_decision_type = "protein_catchup"

        primary_recommendation = _to_recommendation(
            primary,
            decision_type=primary_decision_type,
            headline=headline,
            reason_fallback="Best macro fit for your day right now.",
        )

        if primary_decision_type in {"best_next_meal", "best_breakfast", "best_dinner", "best_next_snack"}:
            next_best_meal = primary_recommendation if primary_decision_type != "best_next_snack" else None
            next_best_snack = primary_recommendation if primary_decision_type == "best_next_snack" else None
        elif primary_decision_type == "lighter_recovery":
            lighter_recovery_option = primary_recommendation
        elif primary_decision_type == "protein_catchup":
            protein_catchup_option = primary_recommendation

        skip_name = str(primary.get("name") or "").strip()

        if rem_protein is not None and rem_protein >= 25:
            catchup = _pick_protein_catchup(profiles, skip_place=skip_name)
            if catchup:
                protein_catchup_option = _to_recommendation(
                    catchup,
                    decision_type="protein_catchup",
                    headline="Protein catch-up option",
                    reason_fallback="Helps close your protein gap with practical calories.",
                )
                secondary.append(protein_catchup_option)

        if rem_cal is not None and rem_cal <= 650:
            recovery = _pick_lighter_recovery(profiles, skip_place=skip_name)
            if recovery:
                lighter_recovery_option = _to_recommendation(
                    recovery,
                    decision_type="lighter_recovery",
                    headline="Lighter recovery option",
                    reason_fallback="Easier to fit if calories are tight.",
                )
                secondary.append(lighter_recovery_option)

        if meal_window == "snack" and not next_best_snack:
            snack = _pick_lighter_recovery(profiles, skip_place="")
            if snack:
                next_best_snack = _to_recommendation(
                    snack,
                    decision_type="best_next_snack",
                    headline="Best snack right now",
                    reason_fallback="Smaller calories with useful protein.",
                )

    else:
        primary_recommendation = {
            "decision_type": "best_next_meal",
            "headline": "Best option for your day right now",
            "place_name": "",
            "recommended_order": "Try scanning a menu nearby for a better next pick.",
            "estimated_calories": 0,
            "estimated_protein_g": 0,
            "fit_for_today": None,
            "why_this_works": "Still gathering nearby options.",
            "decision_confidence": 0.32,
        }

    if next_best_meal is None and primary_recommendation and primary_recommendation.get("decision_type") != "best_next_snack":
        next_best_meal = primary_recommendation

    deduped_secondary: List[Dict[str, Any]] = []
    seen = set()
    for row in secondary:
        key = (
            str(row.get("decision_type") or "").strip().lower(),
            str(row.get("place_name") or "").strip().lower(),
            str(row.get("recommended_order") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped_secondary.append(row)
        if len(deduped_secondary) >= 2:
            break

    return {
        "title": "What should I eat next?",
        "subtitle": "Best option for your day right now",
        "meal_window": meal_window,
        "decision_context": {
            "current_hour": now_hour,
            "goal": goal_value,
            "remaining_calories": None if rem_cal is None else round(max(0.0, rem_cal), 1),
            "remaining_protein_g": None if rem_protein is None else round(max(0.0, rem_protein), 1),
            "cut_mode": bool(cut_mode),
        },
        "primary_recommendation": primary_recommendation,
        "secondary_recommendations": deduped_secondary,
        "next_best_meal": next_best_meal,
        "next_best_snack": next_best_snack,
        "protein_catchup_option": protein_catchup_option,
        "lighter_recovery_option": lighter_recovery_option,
        "decision_version": DAILY_DECISION_VERSION,
    }


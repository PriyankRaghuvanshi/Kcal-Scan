from __future__ import annotations

from typing import Any, Dict, List

from healthy_order_recommender import suggest_best_order_for_place
from healthy_place_scoring import score_healthy_place
from menu_item_scoring import recommend_menu_items_for_place


DAILY_COACH_VERSION = "v1"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def build_daily_context(
    target_calories: float,
    consumed_calories: float,
    target_protein_g: float,
    consumed_protein_g: float,
) -> Dict[str, float]:
    tc = max(0.0, _safe_float(target_calories, 2000.0))
    cc = max(0.0, _safe_float(consumed_calories, 0.0))
    tp = max(0.0, _safe_float(target_protein_g, 150.0))
    cp = max(0.0, _safe_float(consumed_protein_g, 0.0))

    return {
        "target_calories": round(tc, 1),
        "consumed_calories": round(cc, 1),
        "remaining_calories": round(max(0.0, tc - cc), 1),
        "target_protein_g": round(tp, 1),
        "consumed_protein_g": round(cp, 1),
        "remaining_protein_g": round(max(0.0, tp - cp), 1),
    }


def _place_profile(place: Dict[str, Any]) -> Dict[str, Any]:
    payload = place if isinstance(place, dict) else {}

    scoring = score_healthy_place(payload)
    health_score_10pt = float(_safe_float(scoring.get("health_score"), 5.0) or 5.0)
    health_score = int(round(_clamp(health_score_10pt * 10.0, 10.0, 100.0)))

    order = suggest_best_order_for_place(payload, health_score=health_score_10pt)
    menu = recommend_menu_items_for_place(payload, health_score=health_score_10pt)

    top_menu_item = menu.get("top_menu_item") if isinstance(menu.get("top_menu_item"), dict) else None

    best_order = str((top_menu_item or {}).get("item_name") or order.get("best_order") or "Lighter menu option")
    est_calories = int(
        _safe_float(
            (top_menu_item or {}).get("estimated_calories"),
            _safe_float(order.get("estimated_calories"), 520),
        )
        or 520
    )
    est_protein = int(
        _safe_float(
            (top_menu_item or {}).get("estimated_protein_g"),
            _safe_float(order.get("estimated_protein_g"), 32),
        )
        or 32
    )

    return {
        "name": str(payload.get("name") or "").strip(),
        "lat": float(_safe_float(payload.get("lat"), 0.0) or 0.0),
        "lng": float(_safe_float(payload.get("lng"), 0.0) or 0.0),
        "address": str(payload.get("address") or payload.get("vicinity") or "").strip(),
        "rating": float(_safe_float(payload.get("rating"), 0.0) or 0.0),
        "health_score": health_score,
        "health_score_10pt": round(_clamp(health_score_10pt, 1.0, 10.0), 1),
        "best_order": best_order,
        "estimated_calories": int(max(0, est_calories)),
        "estimated_protein_g": int(max(0, est_protein)),
        "short_reason": str((top_menu_item or {}).get("short_reason") or order.get("short_reason") or "Balanced option for today's goals."),
    }


def _fit_decision(place_profile: Dict[str, Any], daily_context: Dict[str, float]) -> Dict[str, Any]:
    remaining_cal = float(_safe_float(daily_context.get("remaining_calories"), 0.0) or 0.0)
    remaining_protein = float(_safe_float(daily_context.get("remaining_protein_g"), 0.0) or 0.0)

    est_cal = float(_safe_float(place_profile.get("estimated_calories"), 520.0) or 520.0)
    est_protein = float(_safe_float(place_profile.get("estimated_protein_g"), 32.0) or 32.0)

    if remaining_cal <= 0:
        return {
            "fit_for_today": False,
            "fit_reason": "Daily calorie budget already reached.",
            "warning": "This option exceeds today's remaining calorie budget.",
            "fit_score": 0.0,
        }

    fits_calories = est_cal <= remaining_cal

    if fits_calories and remaining_protein > 0 and est_protein >= min(remaining_protein, 35.0):
        reason = "High protein and fits your remaining calories."
    elif fits_calories:
        reason = "Fits your remaining calories today."
    else:
        reason = "Too calorie-dense for your remaining budget."

    warning = ""
    if not fits_calories:
        warning = "Calorie-dense for your remaining budget."

    calorie_fit_score = 0.0
    if remaining_cal > 0:
        ratio = est_cal / remaining_cal
        # Prefer options that are neither too tiny nor too heavy for a next-meal suggestion.
        calorie_fit_score = max(0.0, 1.0 - abs(ratio - 0.45))

    protein_fit_score = 1.0
    if remaining_protein > 0:
        protein_fit_score = min(1.0, est_protein / max(1.0, remaining_protein))

    fit_score = (
        (1.0 if fits_calories else 0.0) * 45.0
        + calorie_fit_score * 25.0
        + protein_fit_score * 20.0
        + (float(_safe_float(place_profile.get("health_score"), 50.0)) / 100.0) * 10.0
    )

    return {
        "fit_for_today": bool(fits_calories),
        "fit_reason": reason,
        "warning": warning,
        "fit_score": round(_clamp(fit_score, 0.0, 100.0), 1),
    }


def build_daily_fatloss_coach_response(
    nearby_places: List[Dict[str, Any]],
    target_calories: float,
    consumed_calories: float,
    target_protein_g: float,
    consumed_protein_g: float,
    limit: int = 5,
) -> Dict[str, Any]:
    daily_context = build_daily_context(
        target_calories=target_calories,
        consumed_calories=consumed_calories,
        target_protein_g=target_protein_g,
        consumed_protein_g=consumed_protein_g,
    )

    ranked: List[Dict[str, Any]] = []
    calorie_dense_warnings: List[str] = []

    for place in (nearby_places or []):
        if not isinstance(place, dict):
            continue

        prof = _place_profile(place)
        fit = _fit_decision(prof, daily_context)

        row = {
            "name": prof.get("name"),
            "health_score": int(_safe_float(prof.get("health_score"), 50) or 50),
            "fit_for_today": bool(fit["fit_for_today"]),
            "fit_reason": str(fit["fit_reason"]),
            "best_order": str(prof.get("best_order") or "Lighter menu option"),
            "estimated_calories": int(_safe_float(prof.get("estimated_calories"), 520) or 520),
            "estimated_protein_g": int(_safe_float(prof.get("estimated_protein_g"), 32) or 32),
            "short_reason": str(prof.get("short_reason") or "Better fit for your day."),
            "fit_score": float(_safe_float(fit.get("fit_score"), 0.0) or 0.0),
        }

        if fit.get("warning"):
            row["warning"] = str(fit["warning"])
            calorie_dense_warnings.append(f"{row['name']}: {row['warning']}")

        ranked.append(row)

    ranked.sort(
        key=lambda x: (
            1 if bool(x.get("fit_for_today")) else 0,
            float(_safe_float(x.get("fit_score"), 0.0) or 0.0),
            float(_safe_float(x.get("health_score"), 0.0) or 0.0),
        ),
        reverse=True,
    )

    max_items = max(1, min(10, int(_safe_float(limit, 5) or 5)))

    return {
        "daily_context": daily_context,
        "best_next_meals_nearby": ranked[:max_items],
        "fit_for_today_recommendations_available": bool(ranked),
        "calorie_dense_warnings": calorie_dense_warnings[:max_items],
        "daily_coach_version": DAILY_COACH_VERSION,
    }

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Optional

from day_coach import build_day_coach_payload
from healthy_order_recommender import suggest_best_order_for_place
from healthy_place_scoring import score_healthy_place
from llm_explanation_copy import maybe_rewrite_explanation_copy
from menu_item_scoring import recommend_menu_items_for_place
from recommendation_safety import has_strong_menu_evidence, sanitize_recommended_item
from nutrition_mode import NutritionMode
from personalization_profiles import (
    normalize_personalization_goal,
    personalization_goal_value,
)
from place_today_decision import evaluate_place_for_today
from restaurant_reality_check import build_restaurant_reality_check
from share_card_formatter import build_best_order_share_card
from swap_intelligence import build_swap_suggestions


LUNCH_DECISION_VERSION = "v1"

_TRACKING_EVENTS = {
    "shown": "recommendation_shown",
    "clicked": "recommendation_clicked",
    "place_selected": "place_selected",
    "share_opened": "share_card_opened",
    "share_triggered": "share_action_triggered",
    "followed": "recommendation_followed",
}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _safe_optional_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _norm_text(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _cuisine_hint_from_place(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    primary = str(payload.get("primary_type") or payload.get("primaryType") or "").strip()
    if primary:
        return primary.replace("_", " ")

    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    out = []
    for token in types:
        text = str(token or "").strip().lower()
        if text and text not in {"restaurant", "food", "point_of_interest", "establishment", "meal_takeaway"}:
            out.append(text.replace("_", " "))
    return ", ".join(out[:3])


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    r = 6371000.0
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dlat = p2 - p1
    dlng = math.radians(float(lng2) - float(lng1))
    a = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return int(max(0.0, r * c))


def _menu_item(menu_payload: Dict[str, Any]) -> Dict[str, Any]:
    item = menu_payload.get("top_menu_item")
    return item if isinstance(item, dict) else {}


def _fit_for_today_from_decision(decision_today: str) -> Optional[bool]:
    token = str(decision_today or "").strip().upper()
    if not token:
        return None
    if token == "NO":
        return False
    return True


def _build_share_subtitle(
    *,
    short_reason: str,
    fit_for_today: Optional[bool],
    cut_mode_active: bool,
) -> str:
    if fit_for_today is True and cut_mode_active:
        return "High protein and better calorie control for your cut."
    if fit_for_today is True:
        return "Fits today's macros with strong protein support."
    if fit_for_today is False:
        return "Harder to fit today without strict swaps."
    text = str(short_reason or "").strip()
    return text if text else "Smart eating-out recommendation for right now."


def _tracking_payload(place_id: str, item: str, card_type: str) -> Dict[str, Any]:
    return {
        "place_id": str(place_id or "").strip(),
        "item": str(item or "").strip(),
        "card_type": str(card_type or "").strip(),
        "events": dict(_TRACKING_EVENTS),
    }


def _rewrite_card_copy(
    *,
    profile: Dict[str, Any],
    why_this_works: str,
    short_reason: str,
    typical_order_calories: Any = None,
) -> Dict[str, Any]:
    rewritten = maybe_rewrite_explanation_copy(
        place_name=str(profile.get("name") or "").strip(),
        cuisine=str(profile.get("cuisine_hint") or "").strip(),
        recommended_order=str(profile.get("recommended_order") or "").strip(),
        estimated_calories=profile.get("estimated_calories"),
        estimated_protein_g=profile.get("estimated_protein_g"),
        typical_order_calories=typical_order_calories,
        goal=str(profile.get("personalization_goal") or "").strip(),
        confidence=profile.get("decision_confidence"),
        recommendation_source=profile.get("menu_item_source"),
        menu_item_confidence=profile.get("menu_item_confidence"),
        today_fit=profile.get("decision_today"),
        has_reality_check=bool(profile.get("reality_check")),
        base_why_this_works=why_this_works,
        base_short_reason=short_reason,
    )
    return {
        "why_this_works": str(rewritten.get("why_this_works") or why_this_works),
        "short_reason": str(rewritten.get("short_reason") or short_reason),
        "copy_method": str(rewritten.get("copy_method") or "deterministic"),
        "copy_confidence": round(_clamp(_safe_float(rewritten.get("copy_confidence"), 0.6), 0.2, 0.95), 2),
        "copy_version": str(rewritten.get("copy_version") or "v1"),
    }


def _place_profile(
    place: Dict[str, Any],
    *,
    origin_lat: float,
    origin_lng: float,
    mode: NutritionMode,
    personalization_goal: Any,
    remaining_calories: Any,
    remaining_protein_g: Any,
) -> Dict[str, Any]:
    goal_value = personalization_goal_value(personalization_goal)
    scoring = score_healthy_place(place, mode=mode, personalization_goal=personalization_goal)
    health_score_10pt = _clamp(_safe_float(scoring.get("health_score"), 5.0), 1.0, 10.0)
    health_score = int(round(health_score_10pt * 10.0))

    order = suggest_best_order_for_place(
        place,
        health_score=health_score_10pt,
        mode=mode,
        personalization_goal=personalization_goal,
    )
    menu = recommend_menu_items_for_place(
        place,
        health_score=health_score_10pt,
        mode=mode,
        personalization_goal=personalization_goal,
    )
    top_item = dict(_menu_item(menu))
    menu_context_text = " ".join(
        [
            _cuisine_hint_from_place(place),
            str(place.get("name") or ""),
            " ".join(str(t or "") for t in (place.get("types") if isinstance(place.get("types"), list) else [])),
        ]
    ).strip()

    top_item_source = str(
        top_item.get("menu_item_source")
        or menu.get("menu_source_resolved")
        or menu.get("menu_items_source_resolved")
        or menu.get("menu_source")
        or ""
    ).strip().lower()
    top_item_conf = float(_safe_float(top_item.get("menu_item_confidence"), top_item.get("confidence")) or 0.0)
    top_item_evidence = has_strong_menu_evidence(
        menu_item_source=top_item_source,
        menu_item_confidence=top_item_conf,
        source_url=top_item.get("source_url"),
        extraction_method=top_item.get("extraction_method"),
        parse_method=top_item.get("parse_method"),
        raw_text_snippet=top_item.get("raw_text_snippet"),
    )
    top_item_safety = sanitize_recommended_item(
        item_name=top_item.get("item_name"),
        context_text=menu_context_text,
        menu_item_source=top_item_source or "heuristic",
        menu_item_confidence=top_item_conf if top_item_conf > 0 else 0.45,
        strong_menu_evidence=top_item_evidence,
        display_label=top_item.get("display_label"),
        order_type=top_item.get("order_type"),
    )
    if top_item:
        top_item["item_name"] = str(top_item_safety.get("item_name") or top_item.get("item_name") or "")
        top_item["menu_item_source"] = str(top_item_safety.get("menu_item_source") or top_item_source or "heuristic")
        top_item["menu_item_confidence"] = round(
            _clamp(_safe_float(top_item_safety.get("menu_item_confidence"), top_item_conf), 0.2, 0.97),
            2,
        )
        if str(top_item_safety.get("display_label") or "").strip():
            top_item["display_label"] = str(top_item_safety.get("display_label"))
        if str(top_item_safety.get("order_type") or "").strip():
            top_item["order_type"] = str(top_item_safety.get("order_type"))
        top_item["menu_item_safety_reason"] = str(top_item_safety.get("safety_reason") or "")

    estimated_calories = int(
        _safe_float(top_item.get("estimated_calories"), _safe_float(order.get("estimated_calories"), 520))
        or 520
    )
    estimated_protein_g = int(
        _safe_float(top_item.get("estimated_protein_g"), _safe_float(order.get("estimated_protein_g"), 32))
        or 32
    )

    decision = evaluate_place_for_today(
        estimated_calories=estimated_calories,
        estimated_protein_g=estimated_protein_g,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        health_score=health_score_10pt,
    )

    lat = float(_safe_float(place.get("lat"), 0.0) or 0.0)
    lng = float(_safe_float(place.get("lng"), 0.0) or 0.0)
    distance_meters = _haversine_meters(origin_lat, origin_lng, lat, lng) if lat and lng else 0

    place_name = str(place.get("name") or "Unknown place").strip() or "Unknown place"
    place_id = str(place.get("place_id") or place.get("id") or "").strip()

    decision_today = str(decision.get("decision_today") or "")
    fit_for_today = _fit_for_today_from_decision(decision_today)

    fits_remaining_calories = decision.get("fits_remaining_calories")
    fits_remaining_protein = decision.get("fits_remaining_protein")

    protein_density = _clamp((estimated_protein_g / max(1.0, float(estimated_calories))) * 1400.0, 20.0, 100.0)
    decision_multiplier = {"YES": 1.0, "MAYBE": 0.66, "NO": 0.26}.get(decision_today, 0.62)
    order_confidence = float(
        _safe_float(
            top_item.get("order_confidence"),
            _safe_float(top_item.get("confidence"), _safe_float(order.get("order_confidence"), 0.52)),
        )
        or 0.52
    )
    menu_item_source = str(top_item.get("menu_item_source") or "heuristic").strip().lower() or "heuristic"
    menu_item_confidence = float(_safe_float(top_item.get("menu_item_confidence"), order_confidence) or order_confidence)
    source_rank_weight = float(
        _safe_float(top_item.get("source_rank_weight"), 1.0 if menu_item_source == "real_menu" else 0.95 if menu_item_source == "user_scan" else 0.8 if menu_item_source == "llm_inferred" else 0.65)
        or 0.65
    )

    fit_score = (
        (health_score * 0.46)
        + (protein_density * 0.23)
        + (decision_multiplier * 26.0)
        + (order_confidence * 14.0)
        + (source_rank_weight * 10.0)
        - min(8.0, distance_meters / 420.0)
    )
    if menu_item_source == "heuristic":
        fit_score -= 8.0
    elif menu_item_source == "llm_inferred":
        fit_score -= 3.0

    if mode == NutritionMode.CUT:
        if estimated_calories <= 600 and estimated_protein_g >= 32:
            fit_score += 4.0
        elif estimated_calories >= 760:
            fit_score -= 6.0

    daily_fit_score = round(_clamp(fit_score / 100.0, 0.0, 1.0), 2)

    place_text = _norm_text(
        " ".join(
            [
                place_name,
                str(place.get("vicinity") or place.get("address") or ""),
                " ".join(str(t or "") for t in (place.get("types") if isinstance(place.get("types"), list) else [])),
            ]
        )
    )

    weak_option = any(
        token in place_text
        for token in (
            "burger",
            "fast_food",
            "fast food",
            "fried",
            "pizza",
            "donut",
            "dessert",
            "combo",
            "bucket",
        )
    )

    recommended_order = str(
        top_item.get("item_name")
        or order.get("personalized_best_order")
        or order.get("best_order_for_cut")
        or order.get("best_order")
        or "Lighter menu option"
    )
    top_item["item_name"] = recommended_order
    order_type = str(top_item.get("order_type") or order.get("order_type") or "").strip().lower()
    if order_type not in {"exact", "likely", "estimated"}:
        if menu_item_source == "real_menu" and menu_item_confidence >= 0.72:
            order_type = "exact"
        elif menu_item_confidence >= 0.56:
            order_type = "likely"
        else:
            order_type = "estimated"
    swap_suggestion = str(
        top_item.get("swap_suggestion")
        or order.get("swap_suggestion")
        or order.get("better_swap")
        or "Skip heavy sides and add a lighter side."
    )
    skip_items = (
        top_item.get("skip_items")
        if isinstance(top_item.get("skip_items"), list)
        else order.get("skip_items")
        if isinstance(order.get("skip_items"), list)
        else []
    )
    add_items = (
        top_item.get("add_items")
        if isinstance(top_item.get("add_items"), list)
        else order.get("add_items")
        if isinstance(order.get("add_items"), list)
        else []
    )
    swap_suggestions = build_swap_suggestions(
        swap_suggestion=swap_suggestion,
        skip_items=skip_items,
        add_items=add_items,
        better_swap=order.get("better_swap"),
        place_context=" ".join(
            [
                place_name,
                str(place.get("vicinity") or place.get("address") or ""),
                str(place.get("primary_type") or place.get("primaryType") or ""),
                " ".join(str(t or "") for t in (place.get("types") if isinstance(place.get("types"), list) else [])),
            ]
        ),
        menu_item_source=menu_item_source,
        menu_item_confidence=menu_item_confidence,
        max_items=3,
    )
    recommended_order_label = str(top_item.get("display_label") or "").strip() or "Estimated Best Fit"

    short_reason = str(
        top_item.get("short_reason")
        or order.get("short_reason")
        or "Balanced choice for your lunch goals."
    )

    reality_check = build_restaurant_reality_check(
        place,
        recommended_order={
            "item_name": str(top_item.get("item_name") or recommended_order),
            "estimated_calories": int(max(0, estimated_calories)),
            "estimated_protein_g": int(max(0, estimated_protein_g)),
            "confidence": float(_safe_float(top_item.get("confidence"), order_confidence) or order_confidence),
        },
        context={
            "top_menu_item": top_item,
            "top_menu_items": menu.get("top_menu_items") if isinstance(menu.get("top_menu_items"), list) else [],
            "health_score": health_score,
            "mode": mode.value,
            "fit_for_today": fit_for_today,
            "goal": goal_value,
        },
    )

    share_card = build_best_order_share_card(
        place_name=place_name,
        health_score=health_score,
        best_order=recommended_order,
        estimated_calories=estimated_calories,
        estimated_protein_g=estimated_protein_g,
        subtitle=_build_share_subtitle(
            short_reason=short_reason,
            fit_for_today=fit_for_today,
            cut_mode_active=(mode == NutritionMode.CUT),
        ),
        recommended_badges=scoring.get("recommended_badges") if isinstance(scoring.get("recommended_badges"), list) else [],
        order_strategy_tags=(
            top_item.get("recommendation_tags")
            if isinstance(top_item.get("recommendation_tags"), list)
            else order.get("order_strategy_tags") if isinstance(order.get("order_strategy_tags"), list) else []
        ),
        cut_friendly=bool(top_item.get("cut_friendly") or order.get("cut_friendly")),
        fat_loss_friendly=bool(scoring.get("fat_loss_friendly", False)),
        calories_saved=reality_check.get("calories_saved") if isinstance(reality_check, dict) else None,
    )

    return {
        "name": place_name,
        "place_id": place_id,
        "lat": lat,
        "lng": lng,
        "distance_meters": int(distance_meters),
        "health_score": int(_clamp(health_score, 1, 100)),
        "health_score_10pt": round(health_score_10pt, 1),
        "recommended_order": recommended_order,
        "recommended_order_label": recommended_order_label,
        "order_type": order_type,
        "swap_suggestion": swap_suggestion,
        "swap_suggestions": swap_suggestions,
        "skip_items": skip_items if isinstance(skip_items, list) else [],
        "add_items": add_items if isinstance(add_items, list) else [],
        "estimated_calories": int(max(0, estimated_calories)),
        "estimated_protein_g": int(max(0, estimated_protein_g)),
        "short_reason": short_reason,
        "badges": scoring.get("recommended_badges") if isinstance(scoring.get("recommended_badges"), list) else [],
        "decision_today": decision_today,
        "decision_reason": str(decision.get("decision_reason") or ""),
        "fits_remaining_calories": fits_remaining_calories,
        "fits_remaining_protein": fits_remaining_protein,
        "fit_for_today": fit_for_today,
        "daily_fit_score": daily_fit_score,
        "decision_confidence": float(_safe_float(decision.get("decision_confidence"), order_confidence) or order_confidence),
        "order_confidence": float(_clamp(order_confidence, 0.35, 0.95)),
        "menu_item_source": menu_item_source,
        "menu_item_confidence": round(_clamp(menu_item_confidence, 0.2, 0.95), 2),
        "source_rank_weight": round(_clamp(source_rank_weight, 0.0, 1.1), 2),
        "menu_item_safety_reason": str(top_item.get("menu_item_safety_reason") or ""),
        "fit_score": float(round(_clamp(fit_score, 0.0, 100.0), 2)),
        "weak_option": bool(weak_option),
        "top_menu_items": menu.get("top_menu_items") if isinstance(menu.get("top_menu_items"), list) else [],
        "share_card": share_card,
        "reality_check": reality_check,
        "cuisine_hint": _cuisine_hint_from_place(place),
        "personalization_goal": personalization_goal_value(personalization_goal),
    }


def _pick_best(profiles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not profiles:
        return None

    ordered = sorted(
        profiles,
        key=lambda row: (
            1 if row.get("fit_for_today") is True else 0,
            float(_safe_float(row.get("source_rank_weight"), 0.65) or 0.65),
            float(_safe_float(row.get("fit_score"), 0.0) or 0.0),
            float(_safe_float(row.get("decision_confidence"), 0.0) or 0.0),
            float(_safe_float(row.get("health_score"), 0.0) or 0.0),
        ),
        reverse=True,
    )
    return ordered[0]


def _pick_better_alternative(profiles: List[Dict[str, Any]], best: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    leftovers = [p for p in profiles if p.get("name") != best.get("name")]
    if not leftovers:
        return None

    non_weak_fit = [
        p
        for p in leftovers
        if not bool(p.get("weak_option")) and p.get("fit_for_today") is not False
    ]
    candidates = non_weak_fit or leftovers

    candidates.sort(
        key=lambda row: (
            1 if row.get("fit_for_today") is True else 0,
            float(_safe_float(row.get("source_rank_weight"), 0.65) or 0.65),
            float(_safe_float(row.get("health_score"), 0.0) or 0.0),
            float(_safe_float(row.get("daily_fit_score"), 0.0) or 0.0),
            -float(_safe_float(row.get("distance_meters"), 0.0) or 0.0),
        ),
        reverse=True,
    )
    return candidates[0]


def _pick_hard_to_fit(profiles: List[Dict[str, Any]], chosen_names: List[str]) -> Optional[Dict[str, Any]]:
    leftovers = [p for p in profiles if str(p.get("name") or "") not in chosen_names]
    if not leftovers:
        return None

    hard = [p for p in leftovers if p.get("fit_for_today") is False]
    source = hard or leftovers

    source.sort(
        key=lambda row: (
            1 if bool(row.get("weak_option")) else 0,
            float(_safe_float(row.get("estimated_calories"), 0.0) or 0.0),
            -float(_safe_float(row.get("health_score"), 0.0) or 0.0),
        ),
        reverse=True,
    )
    return source[0]


def _card_badges(profile: Dict[str, Any], *, is_best: bool = False) -> List[str]:
    badges: List[str] = []

    if profile.get("fit_for_today") is True:
        badges.append("Fits today's macros")
    if int(_safe_float(profile.get("estimated_protein_g"), 0.0) or 0) >= 35:
        badges.append("High protein")
    if is_best and float(_safe_float(profile.get("daily_fit_score"), 0.0) or 0.0) >= 0.75:
        badges.append("Coach pick")

    for raw in profile.get("badges") if isinstance(profile.get("badges"), list) else []:
        val = str(raw or "").strip()
        if not val or val in badges:
            continue
        badges.append(val)
        if len(badges) >= 2:
            break

    if not badges:
        badges.append("Better macro balance")
    return badges[:2]


def _typical_calorie_range(profile: Dict[str, Any]) -> str:
    top_items = profile.get("top_menu_items") if isinstance(profile.get("top_menu_items"), list) else []
    values = [
        int(_safe_float(item.get("estimated_calories"), 0.0) or 0)
        for item in top_items
        if isinstance(item, dict)
    ]
    values = [v for v in values if v > 0]
    if values:
        return f"{min(values)}-{max(values)} kcal"

    base = int(_safe_float(profile.get("estimated_calories"), 900.0) or 900)
    low = max(350, base - 180)
    high = min(1500, base + 180)
    return f"{low}-{high} kcal"


def _build_best_card(profile: Dict[str, Any]) -> Dict[str, Any]:
    recommended_order = str(profile.get("recommended_order") or "Lighter menu option")
    reality_check = profile.get("reality_check") if isinstance(profile.get("reality_check"), dict) else {}
    calories_saved = int(_safe_float(reality_check.get("calories_saved"), 0.0) or 0)
    why_this_works = str(profile.get("short_reason") or "Strong protein-calorie balance for your lunch.")
    if calories_saved >= 180:
        why_this_works = f"You save {calories_saved} calories with this smarter pick."

    typical_calories = None
    if isinstance(reality_check.get("typical_order"), dict):
        typical_calories = (reality_check.get("typical_order") or {}).get("estimated_calories")
    rewritten = _rewrite_card_copy(
        profile=profile,
        why_this_works=why_this_works,
        short_reason=str(profile.get("short_reason") or why_this_works),
        typical_order_calories=typical_calories,
    )

    reality_payload = dict(reality_check) if isinstance(reality_check, dict) else {}
    if reality_payload:
        reality_payload["short_reason"] = rewritten["short_reason"]
        reality_payload["copy_method"] = rewritten["copy_method"]
        reality_payload["copy_confidence"] = rewritten["copy_confidence"]
        reality_payload["copy_version"] = rewritten["copy_version"]

    return {
        "card_type": "best_right_now",
        "label": "🥇 BEST RIGHT NOW",
        "place_name": profile.get("name"),
        "place_id": str(profile.get("place_id") or ""),
        "distance_meters": int(_safe_float(profile.get("distance_meters"), 0.0) or 0),
        "recommended_order": recommended_order,
        "recommended_order_label": str(profile.get("recommended_order_label") or "Estimated Best Fit"),
        "swap_suggestion": str(profile.get("swap_suggestion") or ""),
        "swap_suggestions": (
            profile.get("swap_suggestions") if isinstance(profile.get("swap_suggestions"), list) else []
        )[:3],
        "estimated_calories": int(_safe_float(profile.get("estimated_calories"), 0.0) or 0),
        "estimated_protein_g": int(_safe_float(profile.get("estimated_protein_g"), 0.0) or 0),
        "fit_for_today": profile.get("fit_for_today"),
        "fits_remaining_calories": profile.get("fits_remaining_calories"),
        "fits_remaining_protein": profile.get("fits_remaining_protein"),
        "daily_fit_score": float(_safe_float(profile.get("daily_fit_score"), 0.0) or 0.0),
        "badges": _card_badges(profile, is_best=True),
        "why_this_works": rewritten["why_this_works"],
        "decision_reason": str(profile.get("decision_reason") or ""),
        "cta_label": "Navigate",
        "health_score": int(_safe_float(profile.get("health_score"), 0.0) or 0),
        "decision_confidence": round(_clamp(_safe_float(profile.get("decision_confidence"), 0.62), 0.35, 0.95), 2),
        "place_lat": float(_safe_float(profile.get("lat"), 0.0) or 0.0),
        "place_lng": float(_safe_float(profile.get("lng"), 0.0) or 0.0),
        "share_card": profile.get("share_card") if isinstance(profile.get("share_card"), dict) else None,
        "reality_check": reality_payload if reality_payload else None,
        "reality_check_share_card": (
            reality_check.get("share_card") if isinstance(reality_check.get("share_card"), dict) else None
        ) if isinstance(reality_check, dict) else None,
        "copy_method": rewritten["copy_method"],
        "copy_confidence": rewritten["copy_confidence"],
        "copy_version": rewritten["copy_version"],
        "tracking": _tracking_payload(str(profile.get("place_id") or ""), recommended_order, "best_right_now"),
    }


def _build_better_card(profile: Dict[str, Any]) -> Dict[str, Any]:
    reality_check = profile.get("reality_check") if isinstance(profile.get("reality_check"), dict) else {}
    calories_saved = int(_safe_float(reality_check.get("calories_saved"), 0.0) or 0)
    explanation = str(profile.get("short_reason") or "Cleaner macros than nearby combo options.")
    if calories_saved >= 140:
        explanation = f"You save {calories_saved} calories versus a typical order."
    elif not explanation.lower().startswith("better"):
        explanation = f"A more macro-friendly option than typical fast-food meals. {explanation}"

    recommended_order = str(profile.get("recommended_order") or "Lighter menu option")

    typical_calories = None
    if isinstance(reality_check.get("typical_order"), dict):
        typical_calories = (reality_check.get("typical_order") or {}).get("estimated_calories")
    rewritten = _rewrite_card_copy(
        profile=profile,
        why_this_works=explanation,
        short_reason=str(profile.get("short_reason") or explanation),
        typical_order_calories=typical_calories,
    )

    reality_payload = dict(reality_check) if isinstance(reality_check, dict) else {}
    if reality_payload:
        reality_payload["short_reason"] = rewritten["short_reason"]
        reality_payload["copy_method"] = rewritten["copy_method"]
        reality_payload["copy_confidence"] = rewritten["copy_confidence"]
        reality_payload["copy_version"] = rewritten["copy_version"]

    return {
        "card_type": "better_alternative",
        "label": "🥈 BETTER ALTERNATIVE",
        "place_name": profile.get("name"),
        "place_id": str(profile.get("place_id") or ""),
        "distance_meters": int(_safe_float(profile.get("distance_meters"), 0.0) or 0),
        "recommended_order": recommended_order,
        "recommended_order_label": str(profile.get("recommended_order_label") or "Suggested Lighter Option"),
        "swap_suggestion": str(profile.get("swap_suggestion") or ""),
        "swap_suggestions": (
            profile.get("swap_suggestions") if isinstance(profile.get("swap_suggestions"), list) else []
        )[:3],
        "estimated_calories": int(_safe_float(profile.get("estimated_calories"), 0.0) or 0),
        "estimated_protein_g": int(_safe_float(profile.get("estimated_protein_g"), 0.0) or 0),
        "fit_for_today": profile.get("fit_for_today"),
        "fits_remaining_calories": profile.get("fits_remaining_calories"),
        "fits_remaining_protein": profile.get("fits_remaining_protein"),
        "daily_fit_score": float(_safe_float(profile.get("daily_fit_score"), 0.0) or 0.0),
        "badges": ["Better swap"],
        "why_this_works": rewritten["why_this_works"],
        "decision_reason": str(profile.get("decision_reason") or ""),
        "cta_label": "Navigate",
        "health_score": int(_safe_float(profile.get("health_score"), 0.0) or 0),
        "decision_confidence": round(_clamp(_safe_float(profile.get("decision_confidence"), 0.58), 0.35, 0.95), 2),
        "place_lat": float(_safe_float(profile.get("lat"), 0.0) or 0.0),
        "place_lng": float(_safe_float(profile.get("lng"), 0.0) or 0.0),
        "share_card": profile.get("share_card") if isinstance(profile.get("share_card"), dict) else None,
        "reality_check": reality_payload if reality_payload else None,
        "reality_check_share_card": (
            reality_check.get("share_card") if isinstance(reality_check.get("share_card"), dict) else None
        ) if isinstance(reality_check, dict) else None,
        "copy_method": rewritten["copy_method"],
        "copy_confidence": rewritten["copy_confidence"],
        "copy_version": rewritten["copy_version"],
        "tracking": _tracking_payload(str(profile.get("place_id") or ""), recommended_order, "better_alternative"),
    }


def _build_hard_card(profile: Dict[str, Any], remaining_calories: Optional[float]) -> Dict[str, Any]:
    reality_check = profile.get("reality_check") if isinstance(profile.get("reality_check"), dict) else {}
    reason = str(profile.get("decision_reason") or "Possible, but hard to stay on target here today.")
    if "calorie" not in reason.lower():
        reason = "Possible, but difficult to stay within your calorie target."

    recommended_order = str(profile.get("recommended_order") or "Use lighter alternatives today")

    typical_calories = None
    if isinstance(reality_check.get("typical_order"), dict):
        typical_calories = (reality_check.get("typical_order") or {}).get("estimated_calories")
    rewritten = _rewrite_card_copy(
        profile=profile,
        why_this_works=reason,
        short_reason=reason,
        typical_order_calories=typical_calories,
    )

    reality_payload = dict(reality_check) if isinstance(reality_check, dict) else {}
    if reality_payload:
        reality_payload["short_reason"] = rewritten["short_reason"]
        reality_payload["copy_method"] = rewritten["copy_method"]
        reality_payload["copy_confidence"] = rewritten["copy_confidence"]
        reality_payload["copy_version"] = rewritten["copy_version"]

    return {
        "card_type": "hard_to_fit_today",
        "label": "⚠️ HARD TO FIT TODAY",
        "place_name": profile.get("name"),
        "place_id": str(profile.get("place_id") or ""),
        "typical_calorie_range": _typical_calorie_range(profile),
        "remaining_calories": None if remaining_calories is None else int(max(0.0, remaining_calories)),
        "recommended_order": recommended_order,
        "swap_suggestion": str(profile.get("swap_suggestion") or ""),
        "swap_suggestions": (
            profile.get("swap_suggestions") if isinstance(profile.get("swap_suggestions"), list) else []
        )[:3],
        "estimated_calories": int(_safe_float(profile.get("estimated_calories"), 0.0) or 0),
        "estimated_protein_g": int(_safe_float(profile.get("estimated_protein_g"), 0.0) or 0),
        "fit_for_today": False,
        "fits_remaining_calories": profile.get("fits_remaining_calories"),
        "fits_remaining_protein": profile.get("fits_remaining_protein"),
        "daily_fit_score": float(_safe_float(profile.get("daily_fit_score"), 0.0) or 0.0),
        "why_this_works": rewritten["why_this_works"],
        "decision_reason": reason,
        "cta_label": "View alternatives",
        "health_score": int(_safe_float(profile.get("health_score"), 0.0) or 0),
        "decision_confidence": round(_clamp(_safe_float(profile.get("decision_confidence"), 0.56), 0.35, 0.95), 2),
        "place_lat": float(_safe_float(profile.get("lat"), 0.0) or 0.0),
        "place_lng": float(_safe_float(profile.get("lng"), 0.0) or 0.0),
        "share_card": profile.get("share_card") if isinstance(profile.get("share_card"), dict) else None,
        "reality_check": reality_payload if reality_payload else None,
        "reality_check_share_card": (
            reality_check.get("share_card") if isinstance(reality_check.get("share_card"), dict) else None
        ) if isinstance(reality_check, dict) else None,
        "copy_method": rewritten["copy_method"],
        "copy_confidence": rewritten["copy_confidence"],
        "copy_version": rewritten["copy_version"],
        "tracking": _tracking_payload(str(profile.get("place_id") or ""), recommended_order, "hard_to_fit_today"),
    }


def _summary_line(remaining_cal: Optional[float], remaining_protein: Optional[float]) -> str:
    if remaining_cal is not None and remaining_protein is not None:
        return "Based on your remaining calories and protein"
    if remaining_cal is not None:
        return "Based on your remaining calories today"
    if remaining_protein is not None:
        return "Based on your remaining protein target"
    return "Based on nearby menu quality and smart swaps"


def build_lunch_decision_response(
    *,
    nearby_places: List[Dict[str, Any]],
    origin_lat: float,
    origin_lng: float,
    remaining_calories: Any = None,
    remaining_protein_g: Any = None,
    goal: Any = None,
    cut_mode: bool = False,
    target_calories: Any = None,
    consumed_calories: Any = None,
    target_protein_g: Any = None,
    consumed_protein_g: Any = None,
    current_hour: Any = None,
) -> Dict[str, Any]:
    resolved_mode = NutritionMode.CUT if bool(cut_mode) else NutritionMode.DEFAULT
    resolved_goal = normalize_personalization_goal(goal)
    goal_value = personalization_goal_value(resolved_goal)

    remaining_cal = _safe_optional_float(remaining_calories)
    remaining_protein = _safe_optional_float(remaining_protein_g)

    profiles = [
        _place_profile(
            place,
            origin_lat=float(_safe_float(origin_lat, 0.0) or 0.0),
            origin_lng=float(_safe_float(origin_lng, 0.0) or 0.0),
            mode=resolved_mode,
            personalization_goal=resolved_goal,
            remaining_calories=remaining_cal,
            remaining_protein_g=remaining_protein,
        )
        for place in (nearby_places or [])
        if isinstance(place, dict)
    ]

    cards: List[Dict[str, Any]] = []

    best = _pick_best(profiles)
    if best:
        cards.append(_build_best_card(best))

    if best:
        better = _pick_better_alternative(profiles, best)
        if better:
            cards.append(_build_better_card(better))

        chosen_names = [str(best.get("name") or "")]
        if len(cards) >= 2:
            chosen_names.append(str(cards[1].get("place_name") or ""))

        hard = _pick_hard_to_fit(profiles, chosen_names)
        if hard:
            cards.append(_build_hard_card(hard, remaining_cal))

    selected = cards[0] if cards else {}
    selected_place_lat = _safe_optional_float(selected.get("place_lat"))
    selected_place_lng = _safe_optional_float(selected.get("place_lng"))
    day_coach = build_day_coach_payload(
        lunch_cards=cards,
        target_calories=target_calories,
        consumed_calories=consumed_calories,
        remaining_calories=remaining_cal,
        target_protein_g=target_protein_g,
        consumed_protein_g=consumed_protein_g,
        remaining_protein_g=remaining_protein,
        goal=goal_value,
        cut_mode=bool(cut_mode),
        current_hour=current_hour,
    )

    response = {
        "title": "What should I eat right now?",
        "subtitle": "Best lunch near you",
        "summary_line": _summary_line(remaining_cal, remaining_protein),
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "decision_context": {
            "remaining_calories": None if remaining_cal is None else round(max(0.0, remaining_cal), 1),
            "remaining_protein_g": None if remaining_protein is None else round(max(0.0, remaining_protein), 1),
            "goal": goal_value,
            "cut_mode": bool(cut_mode),
        },
        # Cards are returned in final display order so mobile can render directly.
        "cards": cards[:3],
        # Additive map-integration hints for preselecting the top lunch pick.
        "selected_place_id": str(selected.get("place_id") or "").strip(),
        "selected_place_name": str(selected.get("place_name") or "").strip(),
        "selected_place_lat": selected_place_lat,
        "selected_place_lng": selected_place_lng,
        "tracking_hooks": dict(_TRACKING_EVENTS),
        "lunch_decision_version": LUNCH_DECISION_VERSION,
        "day_coach": day_coach,
    }

    if response["cards"] and isinstance(response["cards"][0].get("share_card"), dict):
        response["top_share_card"] = response["cards"][0]["share_card"]
    if response["cards"] and isinstance(response["cards"][0].get("reality_check_share_card"), dict):
        response["top_reality_check_share_card"] = response["cards"][0]["reality_check_share_card"]

    return response

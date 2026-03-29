from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Optional

from day_coach import build_day_coach_payload
from healthy_order_recommender import suggest_best_order_for_place
from healthy_place_scoring import score_healthy_place
from llm_explanation_copy import maybe_rewrite_explanation_copy
from llm_menu_reasoning import (
    CONF_EXACT_ITEM,
    CONF_REASONING_FULL,
    apply_contextual_overlay,
    candidate_item_name,
    candidate_calories,
    candidate_protein,
)
from menu_item_scoring import recommend_menu_items_for_place
from recommendation_safety import (
    has_strong_menu_evidence,
    honest_no_menu_order_copy,
    sanitize_recommended_item,
    should_use_honest_no_menu_order_copy,
)
from nutrition_mode import NutritionMode
from personalization_profiles import (
    normalize_personalization_goal,
    personalization_goal_value,
)
from place_today_decision import evaluate_place_for_today
from ranked_place_builder import build_ranked_place_profile
from restaurant_reality_check import build_restaurant_reality_check
from share_card_formatter import build_best_order_share_card
from swap_intelligence import build_swap_suggestions
from best_order_evidence import decision_card_evidence_fields, evidence_flag_enabled


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
    current_hour: Optional[int] = None,
    use_llm_place_context: bool = True,
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
        use_llm_copy=use_llm_place_context,
        allow_llm_macro=use_llm_place_context,
    )
    menu = recommend_menu_items_for_place(
        place,
        health_score=health_score_10pt,
        mode=mode,
        personalization_goal=personalization_goal,
        use_llm_place_context=use_llm_place_context,
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

    # Extract LLM reasoning candidates from the menu bundle (structural, cached).
    # Then apply the contextual overlay with the current user's macro state so that
    # protein_catchup_option and lighter_recovery_option are user-specific, not cached.
    llm_candidates = (
        menu.get("llm_reasoning_candidates")
        if use_llm_place_context and isinstance(menu.get("llm_reasoning_candidates"), dict)
        else {}
    )
    if use_llm_place_context and llm_candidates.get("llm_reasoning_used") and not llm_candidates.get("contextual_overlay_applied"):
        try:
            llm_candidates = apply_contextual_overlay(
                llm_candidates,
                remaining_calories=_safe_optional_float(remaining_calories),
                remaining_protein_g=_safe_optional_float(remaining_protein_g),
                cut_mode=(mode == NutritionMode.CUT),
                current_hour=current_hour,
            )
        except Exception:
            pass
    llm_best = llm_candidates.get("best_choice_here") if isinstance(llm_candidates.get("best_choice_here"), dict) else {}
    llm_swap = llm_candidates.get("better_swap") if isinstance(llm_candidates.get("better_swap"), dict) else {}

    # Use LLM reasoning best_choice as final fallback before the generic label.
    # Apply CONF_EXACT_ITEM (0.65) to stay consistent with the prompt rule and
    # with the menu_scan.py best_choice threshold.
    llm_best_name = candidate_item_name(llm_best, min_confidence=CONF_EXACT_ITEM) if llm_best else ""

    recommended_order = str(
        top_item.get("item_name")
        or order.get("personalized_best_order")
        or order.get("best_order_for_cut")
        or order.get("best_order")
        or llm_best_name
        or "Lighter menu option"
    )
    top_item["item_name"] = recommended_order
    if should_use_honest_no_menu_order_copy(
        strong_menu_evidence=top_item_evidence,
        menu_item_source=menu_item_source,
        menu_item_confidence=menu_item_confidence,
    ):
        honest_order, honest_lbl = honest_no_menu_order_copy(menu_context_text)
        recommended_order = honest_order
        top_item["item_name"] = recommended_order
        top_item["display_label"] = honest_lbl
        top_item["honest_no_menu_copy"] = True
    order_type = str(top_item.get("order_type") or order.get("order_type") or "").strip().lower()
    if order_type not in {"exact", "likely", "estimated"}:
        if menu_item_source == "real_menu" and menu_item_confidence >= 0.72:
            order_type = "exact"
        elif menu_item_source == "llm_reasoning" and menu_item_confidence >= CONF_EXACT_ITEM:
            order_type = "likely"
        elif menu_item_confidence >= 0.56:
            order_type = "likely"
        else:
            order_type = "estimated"

    # Use LLM reasoning swap_tip when the heuristic swap is generic.
    llm_swap_tip = str(llm_swap.get("swap_tip") or "").strip() if llm_swap else ""
    swap_suggestion = str(
        top_item.get("swap_suggestion")
        or order.get("swap_suggestion")
        or order.get("better_swap")
        or llm_swap_tip
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
            "llm_reasoning_candidates": llm_candidates,
        },
        use_llm_copy=use_llm_place_context,
        allow_llm_macro=use_llm_place_context,
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

    # Canonical ranking from single builder (no duplicate logic)
    place_for_ranking = {
        "name": place_name,
        "cuisine_hint": _cuisine_hint_from_place(place),
        "recommended_order": recommended_order,
        "best_order": recommended_order,
        "decision_today": decision_today,
        "fit_for_today": fit_for_today,
        "estimated_calories": estimated_calories,
        "estimated_protein_g": estimated_protein_g,
        "menu_item_confidence": menu_item_confidence,
        "order_confidence": order_confidence,
        "distance_meters": distance_meters,
        "menu_item_source": menu_item_source,
        "health_score": health_score_10pt,
        "fit_today_score_100": decision.get("fit_today_score_100"),
        "calorie_fit_score_100": decision.get("calorie_fit_score_100"),
        "protein_fit_score_100": decision.get("protein_fit_score_100"),
        "overshoot_penalty_100": decision.get("overshoot_penalty_100"),
    }
    user_context = {
        "remaining_protein_g": remaining_protein_g,
        "cut_mode": mode == NutritionMode.CUT,
        "goal": goal_value,
    }
    ranking_fields = build_ranked_place_profile(place_for_ranking, user_context)
    if ranking_fields.get("best_item_is_generic_fallback") and recommended_order_label.lower() in ("best order", "estimated best fit"):
        recommended_order_label = "Suggested healthier pick"
    matched_chain_key = str(
        top_item.get("matched_chain_key")
        or top_item.get("chain_key")
        or place.get("matched_chain_key")
        or place.get("chain_key")
        or ""
    ).strip().lower()
    chain_features = place.get("chain_features") if isinstance(place.get("chain_features"), dict) else {}

    return {
        "name": place_name,
        "place_id": place_id,
        "lat": lat,
        "lng": lng,
        "distance_meters": int(distance_meters),
        "health_score": int(_clamp(health_score, 1, 100)),
        "health_score_10pt": round(health_score_10pt, 1),
        **ranking_fields,
        "candidate_source_label": menu_item_source.replace("_", " ").title(),
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
        "source_updated_at": str(top_item.get("last_ingested_at") or place.get("last_ingested_at") or "").strip(),
        "menu_item_safety_reason": str(top_item.get("menu_item_safety_reason") or ""),
        "matched_chain_key": matched_chain_key,
        "chain_key": matched_chain_key,
        "country_code": str(place.get("country_code") or "").strip().upper(),
        "chain_status": str(place.get("chain_status") or "").strip().lower(),
        "chain_features": chain_features,
        "fit_score": float(round(_clamp(fit_score, 0.0, 100.0), 2)),
        "weak_option": bool(weak_option),
        "top_menu_items": menu.get("top_menu_items") if isinstance(menu.get("top_menu_items"), list) else [],
        "share_card": share_card,
        "reality_check": reality_check,
        "cuisine_hint": _cuisine_hint_from_place(place),
        "personalization_goal": personalization_goal_value(personalization_goal),
    }


def _fit_for_today_strength(decision_today: str) -> float:
    d = str(decision_today or "").strip().upper()
    return 1.0 if d == "YES" else (0.5 if d == "MAYBE" else 0.0)


def _pick_best(profiles: List[Dict[str, Any]], *, goal: str = "") -> Optional[Dict[str, Any]]:
    if not profiles:
        return None

    # Meal-first: eligibility_band, meal_fitness_score_100, fit_for_today_strength, confidence, protein_density, distance, venue_prior
    def _sort_key(row: Dict[str, Any]) -> tuple:
        band = int(_safe_float(row.get("eligibility_band"), 1))
        meal_score = float(_safe_float(row.get("meal_fitness_score_100") or row.get("display_rank_score_100"), 0.0) or 0.0)
        fit_strength = _fit_for_today_strength(row.get("decision_today"))
        conf = float(_safe_float(row.get("decision_confidence") or row.get("order_confidence"), 0.5) or 0.5)
        protein_density = _clamp(
            (float(_safe_float(row.get("estimated_protein_g"), 0.0) or 0.0) / max(1.0, float(_safe_float(row.get("estimated_calories"), 520.0) or 520.0)) * 1400.0),
            0.0, 100.0,
        )
        dist = float(_safe_float(row.get("distance_meters"), 99999.0) or 99999.0)
        venue_prior = float(_safe_float(row.get("venue_prior_score_100") or row.get("health_score"), 0.0) or 0.0)
        return (band, meal_score, fit_strength, conf, protein_density, -dist, venue_prior)

    ordered = sorted(profiles, key=_sort_key, reverse=True)
    best = ordered[0]
    # Hero constraint: if top candidate is band < 2 or generic, caller can show "Best available option" section
    if int(_safe_float(best.get("eligibility_band"), 1)) < 2 or best.get("best_item_is_generic_fallback"):
        best["hero_available"] = False
    else:
        best["hero_available"] = True
    return best


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

    card = {
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
    if evidence_flag_enabled():
        try:
            card.update(decision_card_evidence_fields(profile))
        except Exception:
            pass
    return card


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

    card = {
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
    if evidence_flag_enabled():
        try:
            card.update(decision_card_evidence_fields(profile))
        except Exception:
            pass
    return card


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

    card = {
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
    if evidence_flag_enabled():
        try:
            card.update(decision_card_evidence_fields(profile))
        except Exception:
            pass
    return card


def _summary_line(remaining_cal: Optional[float], remaining_protein: Optional[float]) -> str:
    if remaining_cal is not None and remaining_protein is not None:
        return "Based on your remaining calories and protein"
    if remaining_cal is not None:
        return "Based on your remaining calories today"
    if remaining_protein is not None:
        return "Based on your remaining protein target"
    return "Based on nearby menu quality and smart swaps"


def _place_by_id(nearby_places: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for p in (nearby_places or []):
        if not isinstance(p, dict):
            continue
        pid = str(p.get("place_id") or p.get("id") or "").strip()
        if pid and pid not in out:
            out[pid] = p
    return out


def _decision_from_snapshot_profile(
    prof: Dict[str, Any],
    *,
    remaining_calories: Optional[float],
    remaining_protein_g: Optional[float],
) -> Dict[str, Any]:
    est_cal = int(_safe_float(prof.get("estimated_calories"), 520.0) or 520)
    est_prot = int(_safe_float(prof.get("estimated_protein_g"), 32.0) or 32)
    health_10pt = float(_safe_float(prof.get("health_score_10pt"), 5.0) or 5.0)
    # Snapshot profiles may only have health_score_100; fall back if needed.
    if (not health_10pt or health_10pt <= 0.0) and prof.get("health_score") is not None:
        health_10pt = float(_safe_float(prof.get("health_score"), 50.0) or 50.0) / 10.0
    return evaluate_place_for_today(
        estimated_calories=est_cal,
        estimated_protein_g=est_prot,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        health_score=health_10pt,
    )


def _profile_from_snapshot_and_place(
    prof: Dict[str, Any],
    place: Dict[str, Any],
    *,
    origin_lat: float,
    origin_lng: float,
    remaining_calories: Optional[float],
    remaining_protein_g: Optional[float],
    goal_value: str,
    cut_mode: bool,
    resolved_mode: NutritionMode,
    use_llm_place_context: bool,
) -> Dict[str, Any]:
    """
    Build a lunch-decision "profile" dict without re-scoring / re-enriching.

    We reuse snapshot estimates (best_order + macros + menu evidence) and only
    add the missing contract fields (reality_check/share_card + ranked labels).
    """
    place_name = str(place.get("name") or prof.get("name") or "Nearby place").strip() or "Nearby place"
    place_id = str(place.get("place_id") or place.get("id") or prof.get("place_id") or "").strip()
    lat = float(_safe_float(place.get("lat"), _safe_float(prof.get("lat"), 0.0)) or 0.0)
    lng = float(_safe_float(place.get("lng"), _safe_float(prof.get("lng"), 0.0)) or 0.0)
    distance_meters = int(_safe_float(prof.get("distance_meters"), 0.0) or 0)
    if not distance_meters and lat and lng:
        distance_meters = _haversine_meters(float(origin_lat), float(origin_lng), lat, lng)

    top_item = prof.get("top_menu_item") if isinstance(prof.get("top_menu_item"), dict) else {}
    recommended_order = str(prof.get("best_order") or top_item.get("item_name") or "Lighter menu option").strip()
    estimated_calories = int(_safe_float(prof.get("estimated_calories"), _safe_float(top_item.get("estimated_calories"), 520.0)) or 520)
    estimated_protein_g = int(_safe_float(prof.get("estimated_protein_g"), _safe_float(top_item.get("estimated_protein_g"), 32.0)) or 32)
    order_confidence = float(_safe_float(prof.get("order_confidence"), 0.46) or 0.46)
    menu_item_confidence = float(_safe_float(top_item.get("menu_item_confidence"), _safe_float(top_item.get("confidence"), order_confidence)) or order_confidence)
    menu_item_source = str(top_item.get("menu_item_source") or "heuristic").strip().lower()
    source_url = str(top_item.get("source_url") or top_item.get("url") or "").strip()
    extraction_method = str(top_item.get("extraction_method") or "").strip()
    parse_method = str(top_item.get("parse_method") or "").strip()

    decision = evaluate_place_for_today(
        estimated_calories=estimated_calories,
        estimated_protein_g=estimated_protein_g,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        health_score=float(_safe_float(prof.get("health_score_10pt"), 5.0) or 5.0),
    )
    decision_today = str(decision.get("decision_today") or "")
    fit_for_today = _fit_for_today_from_decision(decision_today)

    # Canonical ranking labels/fields (no menu/scoring work here).
    place_for_ranking = {
        "name": place_name,
        "cuisine_hint": _cuisine_hint_from_place(place) or _cuisine_hint_from_place(prof),
        "recommended_order": recommended_order,
        "best_order": recommended_order,
        "decision_today": decision_today,
        "fit_for_today": fit_for_today,
        "estimated_calories": estimated_calories,
        "estimated_protein_g": estimated_protein_g,
        "menu_item_confidence": menu_item_confidence,
        "order_confidence": order_confidence,
        "distance_meters": distance_meters,
        "menu_item_source": menu_item_source,
        "health_score": float(_safe_float(prof.get("health_score_10pt"), 5.0) or 5.0),
        "fit_today_score_100": decision.get("fit_today_score_100"),
        "calorie_fit_score_100": decision.get("calorie_fit_score_100"),
        "protein_fit_score_100": decision.get("protein_fit_score_100"),
        "overshoot_penalty_100": decision.get("overshoot_penalty_100"),
    }
    user_context = {
        "remaining_protein_g": remaining_protein_g,
        "cut_mode": bool(cut_mode),
        "goal": str(goal_value or "").strip(),
    }
    try:
        ranking_fields = build_ranked_place_profile(place_for_ranking, user_context)
    except Exception:
        ranking_fields = {}

    short_reason = str(
        (top_item.get("short_reason") if isinstance(top_item, dict) else "")
        or prof.get("short_reason")
        or ranking_fields.get("rank_reason_short")
        or "Smart eating-out recommendation for right now."
    ).strip()

    # Reality check + share card (LLM disabled in API paths today).
    reality_check = build_restaurant_reality_check(
        place,
        recommended_order={
            "item_name": recommended_order,
            "estimated_calories": int(max(0, estimated_calories)),
            "estimated_protein_g": int(max(0, estimated_protein_g)),
            "confidence": float(_safe_float(menu_item_confidence, order_confidence) or order_confidence),
            "menu_item_source": menu_item_source,
            "menu_item_confidence": float(_safe_float(menu_item_confidence, order_confidence) or order_confidence),
        },
        context={
            "top_menu_item": top_item,
            "health_score": float(_safe_float(prof.get("health_score_10pt"), 5.0) or 5.0),
            "mode": resolved_mode.value,
            "fit_for_today": fit_for_today,
            "goal": goal_value,
        },
        use_llm_copy=bool(use_llm_place_context),
        allow_llm_macro=bool(use_llm_place_context),
    )
    share_card = build_best_order_share_card(
        place_name=place_name,
        health_score=float(_safe_float(prof.get("health_score_10pt"), 5.0) or 5.0),
        best_order=recommended_order,
        estimated_calories=estimated_calories,
        estimated_protein_g=estimated_protein_g,
        subtitle=_build_share_subtitle(
            short_reason=short_reason,
            fit_for_today=fit_for_today,
            cut_mode_active=(resolved_mode == NutritionMode.CUT),
        ),
        recommended_badges=[],
        order_strategy_tags=[],
        cut_friendly=bool(cut_mode),
        fat_loss_friendly=bool(cut_mode),
        calories_saved=(reality_check.get("calories_saved") if isinstance(reality_check, dict) else None),
    )

    # Preserve fields expected by card builders + response contract.
    # NOTE: recommended_order_label historically uses a human label; reuse recommendation_label as the safest proxy.
    recommended_order_label = str(ranking_fields.get("recommendation_label") or "Estimated Best Fit")
    daily_fit_score = round(float(_safe_float(ranking_fields.get("meal_fitness_score_100"), 0.0) or 0.0) / 100.0, 2)
    matched_chain_key = str(
        top_item.get("matched_chain_key")
        or top_item.get("chain_key")
        or prof.get("matched_chain_key")
        or prof.get("chain_key")
        or place.get("chain_key")
        or ""
    ).strip().lower()
    chain_status = str(prof.get("chain_status") or place.get("chain_status") or "").strip().lower()
    chain_features = (
        prof.get("chain_features")
        if isinstance(prof.get("chain_features"), dict)
        else (place.get("chain_features") if isinstance(place.get("chain_features"), dict) else {})
    )

    return {
        "name": place_name,
        "place_id": place_id,
        "lat": lat,
        "lng": lng,
        "distance_meters": int(distance_meters),
        "recommended_order": recommended_order,
        "recommended_order_label": recommended_order_label,
        "swap_suggestion": str(top_item.get("swap_suggestion") or ""),
        "swap_suggestions": (top_item.get("swap_suggestions") if isinstance(top_item.get("swap_suggestions"), list) else [])[:3],
        "estimated_calories": int(max(0, estimated_calories)),
        "estimated_protein_g": int(max(0, estimated_protein_g)),
        "short_reason": short_reason,
        "decision_today": decision_today,
        "decision_reason": str(decision.get("decision_reason") or ""),
        "fits_remaining_calories": decision.get("fits_remaining_calories"),
        "fits_remaining_protein": decision.get("fits_remaining_protein"),
        "fit_for_today": fit_for_today,
        "daily_fit_score": daily_fit_score,
        "decision_confidence": float(_safe_float(decision.get("decision_confidence"), order_confidence) or order_confidence),
        "order_confidence": float(_clamp(order_confidence, 0.35, 0.95)),
        "menu_item_source": menu_item_source,
        "menu_item_confidence": round(_clamp(menu_item_confidence, 0.2, 0.95), 2),
        "source_url": source_url,
        "source_updated_at": str(top_item.get("last_ingested_at") or prof.get("last_ingested_at") or "").strip(),
        "extraction_method": extraction_method,
        "parse_method": parse_method,
        "candidate_source_label": menu_item_source.replace("_", " ").title(),
        "matched_chain_key": matched_chain_key,
        "chain_key": matched_chain_key,
        "country_code": str(place.get("country_code") or prof.get("country_code") or "").strip().upper(),
        "chain_status": chain_status,
        "chain_features": chain_features,
        "health_score": int(_clamp(_safe_float(prof.get("health_score"), 50.0) or 50.0, 1, 100)),
        "health_score_10pt": round(float(_safe_float(prof.get("health_score_10pt"), 5.0) or 5.0), 1),
        **(ranking_fields or {}),
        "share_card": share_card,
        "reality_check": reality_check,
        "personalization_goal": goal_value,
    }

def build_lunch_decision_response_from_snapshot(
    *,
    nearby_places: List[Dict[str, Any]],
    snapshot: Dict[str, Any],
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
    use_llm_place_context: bool = True,
) -> Dict[str, Any]:
    """
    Snapshot-based /places/lunch-decision builder.

    Preserves response shape but selects decision cards from a single canonical
    ranked dataset (snapshot.ranked_places), with best_here vs best_nearby support.

    To keep the change incremental + safe, we only run full enrichment (_place_profile)
    for the 2-3 selected cards, not for every nearby place.
    """
    resolved_mode = NutritionMode.CUT if bool(cut_mode) else NutritionMode.DEFAULT
    resolved_goal = normalize_personalization_goal(goal)
    goal_value = personalization_goal_value(resolved_goal)

    remaining_cal = _safe_optional_float(remaining_calories)
    remaining_protein = _safe_optional_float(remaining_protein_g)
    resolved_hour = int(current_hour) if current_hour is not None and str(current_hour).strip().lstrip("-").isdigit() else None

    ranked_places = snapshot.get("ranked_places") if isinstance(snapshot, dict) else None
    ranked: List[Dict[str, Any]] = ranked_places if isinstance(ranked_places, list) else []
    best_here = snapshot.get("best_here") if isinstance(snapshot, dict) else None
    best_nearby = snapshot.get("best_nearby") if isinstance(snapshot, dict) else None

    by_id = _place_by_id(nearby_places)

    def _pid(summary: Any) -> str:
        if not isinstance(summary, dict):
            return ""
        return str(summary.get("place_id") or "").strip()

    best_here_id = _pid(best_here)
    best_nearby_id = _pid(best_nearby)
    top_ranked_id = str(ranked[0].get("place_id") or "").strip() if ranked else ""

    # Card selection from canonical ranked list:
    # - If we appear to be at a venue, "best_right_now" becomes that venue's best option.
    # - Otherwise it is the overall best nearby.
    best_id = best_here_id or best_nearby_id or top_ranked_id

    # Better alternative: prefer best_nearby if best_id is best_here and differs; else next ranked.
    better_id = ""
    if best_id and best_here_id and best_id == best_here_id and best_nearby_id and best_nearby_id != best_id:
        better_id = best_nearby_id
    else:
        for prof in ranked[1:]:
            pid = str(prof.get("place_id") or "").strip()
            if pid and pid != best_id:
                better_id = pid
                break

    # Hard-to-fit: pick first ranked candidate that evaluates to NO today (excluding chosen).
    hard_id = ""
    chosen = {pid for pid in (best_id, better_id) if pid}
    for prof in ranked:
        pid = str(prof.get("place_id") or "").strip()
        if not pid or pid in chosen:
            continue
        decision = _decision_from_snapshot_profile(
            prof,
            remaining_calories=remaining_cal,
            remaining_protein_g=remaining_protein,
        )
        if str(decision.get("decision_today") or "").strip().upper() == "NO":
            hard_id = pid
            break

    prof_by_id: Dict[str, Dict[str, Any]] = {}
    for p in ranked:
        if isinstance(p, dict):
            pid = str(p.get("place_id") or "").strip()
            if pid and pid not in prof_by_id:
                prof_by_id[pid] = p

    def _profile_for(pid: str) -> Optional[Dict[str, Any]]:
        if not pid:
            return None
        raw = by_id.get(pid)
        prof = prof_by_id.get(pid)
        if not isinstance(raw, dict) or not isinstance(prof, dict):
            return None
        try:
            return _profile_from_snapshot_and_place(
                prof,
                raw,
                origin_lat=float(_safe_float(origin_lat, 0.0) or 0.0),
                origin_lng=float(_safe_float(origin_lng, 0.0) or 0.0),
                remaining_calories=remaining_cal,
                remaining_protein_g=remaining_protein,
                goal_value=goal_value,
                cut_mode=bool(cut_mode),
                resolved_mode=resolved_mode,
                use_llm_place_context=use_llm_place_context,
            )
        except Exception:
            return None

    cards: List[Dict[str, Any]] = []
    best_profile = _profile_for(best_id)
    if best_profile:
        cards.append(_build_best_card(best_profile))

    better_profile = _profile_for(better_id) if best_profile else None
    if better_profile:
        cards.append(_build_better_card(better_profile))

    hard_profile = _profile_for(hard_id) if best_profile else None
    if hard_profile:
        cards.append(_build_hard_card(hard_profile, remaining_cal))

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
        "cards": cards[:3],
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
    use_llm_place_context: bool = True,
    snapshot: Optional[Dict[str, Any]] = None,
    use_snapshot: bool = False,
) -> Dict[str, Any]:
    if use_snapshot and isinstance(snapshot, dict):
        return build_lunch_decision_response_from_snapshot(
            nearby_places=nearby_places,
            snapshot=snapshot,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            remaining_calories=remaining_calories,
            remaining_protein_g=remaining_protein_g,
            goal=goal,
            cut_mode=cut_mode,
            target_calories=target_calories,
            consumed_calories=consumed_calories,
            target_protein_g=target_protein_g,
            consumed_protein_g=consumed_protein_g,
            current_hour=current_hour,
            use_llm_place_context=use_llm_place_context,
        )

    resolved_mode = NutritionMode.CUT if bool(cut_mode) else NutritionMode.DEFAULT
    resolved_goal = normalize_personalization_goal(goal)
    goal_value = personalization_goal_value(resolved_goal)

    remaining_cal = _safe_optional_float(remaining_calories)
    remaining_protein = _safe_optional_float(remaining_protein_g)

    resolved_hour = int(current_hour) if current_hour is not None and str(current_hour).strip().lstrip("-").isdigit() else None
    profiles = [
        _place_profile(
            place,
            origin_lat=float(_safe_float(origin_lat, 0.0) or 0.0),
            origin_lng=float(_safe_float(origin_lng, 0.0) or 0.0),
            mode=resolved_mode,
            personalization_goal=resolved_goal,
            remaining_calories=remaining_cal,
            remaining_protein_g=remaining_protein,
            current_hour=resolved_hour,
            use_llm_place_context=use_llm_place_context,
        )
        for place in (nearby_places or [])
        if isinstance(place, dict)
    ]

    cards: List[Dict[str, Any]] = []

    best = _pick_best(profiles, goal=goal)
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

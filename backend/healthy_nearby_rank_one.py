"""
Per-place ranking for GET /places/healthy. Extracted so multiple places can be
scored in parallel (asyncio.to_thread) without duplicating request latency.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from context_modes import infer_context_mode
from diet_filters import normalize_diet_preference
from healthy_order_recommender import suggest_best_order_for_place
from healthy_place_scoring import (
    HEALTHY_PLACE_SCORING_VERSION,
    best_options_for_place,
    score_healthy_place,
)
from menu_item_scoring import recommend_menu_items_for_place
from nutrition_mode import NutritionMode
from personal_response_summary import get_personal_meal_memory
from personalization_profiles import PersonalizationGoal, get_personalized_reason
from place_today_decision import evaluate_place_for_today
from ranked_place_builder import build_ranked_place_profile
from recommendation_safety import (
    has_strong_menu_evidence,
    honest_no_menu_order_copy,
    sanitize_recommended_item,
    should_use_honest_no_menu_order_copy,
)
from restaurant_reality_check import build_restaurant_reality_check
from share_card_formatter import build_best_order_share_card
from swap_intelligence import build_swap_suggestions
from venue_intelligence_cache import cache_to_menu_payload, get as venue_cache_get


def _safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _best_options_for_place(place: Dict[str, Any]) -> List[str]:
    try:
        out = best_options_for_place(place)
        return out if isinstance(out, list) and out else ["Protein-forward meal", "Lower-oil whole-food option"]
    except Exception:
        return ["Protein-forward meal", "Lower-oil whole-food option"]


def _compute_health_score(place: Dict[str, Any]) -> float:
    try:
        scored = score_healthy_place(place)
        return round(float(_safe_float(scored.get("health_score"), 5.0) or 5.0), 1)
    except Exception:
        return 5.0


@dataclass(frozen=True)
class HealthyNearbyRankContext:
    lat: float
    lng: float
    cut_mode: bool
    goal: str
    nutrition_mode: NutritionMode
    personalization_goal: Optional[PersonalizationGoal]
    personalization_goal_value_str: str
    diet_preference_val: str
    remaining_calories: Optional[float]
    remaining_protein_g: Optional[float]
    post_workout: bool
    late_night: bool
    poor_sleep_flag: bool
    high_craving_risk_flag: bool
    context_mode: str
    local_hour: Optional[int]
    user_id: str
    # Preloaded once per /places/healthy request — avoids N× disk lock in parallel rank workers
    feedback_events_prefetch: Optional[List[Dict[str, Any]]] = None
    decision_events_prefetch: Optional[List[Dict[str, Any]]] = None


def rank_one_healthy_nearby_place(p: Dict[str, Any], ctx: HealthyNearbyRankContext) -> Dict[str, Any]:
    cut_mode = ctx.cut_mode
    lat = ctx.lat
    lng = ctx.lng
    goal = ctx.goal
    nutrition_mode = ctx.nutrition_mode
    personalization_goal = ctx.personalization_goal
    personalization_goal_value_str = ctx.personalization_goal_value_str
    diet_preference_val = ctx.diet_preference_val
    remaining_calories = ctx.remaining_calories
    remaining_protein_g = ctx.remaining_protein_g
    post_workout = ctx.post_workout
    late_night = ctx.late_night
    poor_sleep_flag = ctx.poor_sleep_flag
    high_craving_risk_flag = ctx.high_craving_risk_flag
    context_mode = ctx.context_mode
    local_hour = ctx.local_hour
    user_id = ctx.user_id

    place_id = str(p.get("place_id") or p.get("id") or "").strip()
    cached = venue_cache_get(place_id) if place_id else None
    if cached:
        try:
            menu_recommendations = cache_to_menu_payload(cached, p)
        except Exception:
            cached = None
    if not cached:
        try:
            menu_recommendations = recommend_menu_items_for_place(
                p,
                mode=nutrition_mode,
                personalization_goal=personalization_goal,
                use_llm_place_context=False,
                diet_preference=diet_preference_val,
            )
        except Exception:
            menu_recommendations = {
                "menu_item_scoring_available": False,
                "menu_items_source": "heuristic",
                "menu_source": "heuristic",
                "menu_confidence": 0.0,
                "extraction_method": "",
                "parse_method": "",
                "source_url": "",
                "top_menu_items": [],
                "best_menu_items": [],
                "top_menu_item": None,
                "top_item": "",
                "cut_mode_active": bool(cut_mode),
            }

    try:
        scoring = score_healthy_place(
            p,
            mode=nutrition_mode,
            personalization_goal=personalization_goal,
            menu_payload=menu_recommendations,
        )
    except Exception:
        scoring = {
            "health_score": _compute_health_score(p),
            "best_options": _best_options_for_place(p),
            "score_breakdown": None,
            "fat_loss_friendly": False,
            "recommended_badges": [],
            "nutrition_data_available": False,
            "scoring_version": HEALTHY_PLACE_SCORING_VERSION,
            "cut_mode_active": bool(cut_mode),
            "cut_friendly": False,
            "cut_warning": "",
        }

    fallback_score = 5.0
    score = float(_safe_float(scoring.get("health_score"), fallback_score) or fallback_score)
    options = scoring.get("best_options") if isinstance(scoring.get("best_options"), list) else _best_options_for_place(p)

    try:
        order_suggestion = suggest_best_order_for_place(
            p,
            health_score=score,
            mode=nutrition_mode,
            use_llm_copy=False,
            allow_llm_macro=False,
            diet_preference=diet_preference_val,
        )
    except Exception:
        order_suggestion = {}

    best_order = str(order_suggestion.get("best_order") or "Lighter menu option")
    estimated_calories = int(_safe_float(order_suggestion.get("estimated_calories"), 520) or 520)
    estimated_protein_g = int(_safe_float(order_suggestion.get("estimated_protein_g"), 32) or 32)
    top_menu_item = dict(menu_recommendations.get("top_menu_item")) if isinstance(menu_recommendations.get("top_menu_item"), dict) else {}
    top_menu_source = str(
        top_menu_item.get("menu_item_source")
        or menu_recommendations.get("menu_source_resolved")
        or menu_recommendations.get("menu_items_source_resolved")
        or menu_recommendations.get("menu_source")
        or menu_recommendations.get("menu_items_source")
        or "heuristic"
    ).strip().lower()
    top_menu_conf = float(
        _safe_float(
            top_menu_item.get("menu_item_confidence"),
            _safe_float(top_menu_item.get("confidence"), 0.0),
        )
        or 0.0
    )
    menu_context_text = " ".join(
        [
            str(p.get("name") or ""),
            str(p.get("vicinity") or p.get("address") or ""),
            " ".join(str(t or "") for t in (p.get("types") if isinstance(p.get("types"), list) else [])),
        ]
    ).strip()
    top_menu_evidence = has_strong_menu_evidence(
        menu_item_source=top_menu_source,
        menu_item_confidence=top_menu_conf,
        source_url=top_menu_item.get("source_url") or menu_recommendations.get("source_url"),
        extraction_method=top_menu_item.get("extraction_method") or menu_recommendations.get("extraction_method"),
        parse_method=top_menu_item.get("parse_method") or menu_recommendations.get("parse_method"),
        raw_text_snippet=top_menu_item.get("raw_text_snippet"),
    )
    top_menu_safety = sanitize_recommended_item(
        item_name=top_menu_item.get("item_name"),
        context_text=menu_context_text,
        menu_item_source=top_menu_source,
        menu_item_confidence=top_menu_conf if top_menu_conf > 0 else 0.45,
        strong_menu_evidence=top_menu_evidence,
        display_label=top_menu_item.get("display_label"),
        order_type=top_menu_item.get("order_type"),
    )
    if top_menu_item:
        top_menu_item["item_name"] = str(top_menu_safety.get("item_name") or top_menu_item.get("item_name") or "")
        top_menu_item["menu_item_source"] = str(top_menu_safety.get("menu_item_source") or top_menu_source or "heuristic")
        top_menu_item["menu_item_confidence"] = round(
            float(_safe_float(top_menu_safety.get("menu_item_confidence"), top_menu_conf) or top_menu_conf),
            2,
        )
        top_menu_item["display_label"] = str(top_menu_safety.get("display_label") or top_menu_item.get("display_label") or "")
        top_menu_item["order_type"] = str(top_menu_safety.get("order_type") or top_menu_item.get("order_type") or "")
        top_menu_item["menu_item_safety_reason"] = str(top_menu_safety.get("safety_reason") or "")
        top_menu_item["menu_item_strong_evidence"] = bool(top_menu_evidence)
    top_menu_source = str(top_menu_item.get("menu_item_source") or top_menu_source or "heuristic").strip().lower()
    top_menu_conf = float(
        _safe_float(
            top_menu_item.get("menu_item_confidence"),
            top_menu_conf,
        )
        or 0.0
    )
    top_menu_source_weight = float(
        _safe_float(
            top_menu_item.get("source_rank_weight"),
            1.0 if top_menu_source == "real_menu" else 0.95 if top_menu_source == "user_scan" else 0.8 if top_menu_source == "llm_inferred" else 0.65,
        )
        or 0.65
    )
    if top_menu_item and not top_menu_item.get("source_rank_weight"):
        top_menu_item["source_rank_weight"] = round(float(_safe_float(top_menu_source_weight, 0.65) or 0.65), 2)
    top_menu_order_type = str(top_menu_item.get("order_type") or "").strip().lower()
    if top_menu_order_type not in {"exact", "likely", "estimated"}:
        if top_menu_source in {
            "real_menu",
            "menu_intelligence_store",
            "structured_menu",
            "scraped_menu",
            "website_menu",
            "website_text",
            "review_text",
            "ocr_menu",
            "user_scan",
        } and top_menu_conf >= 0.72:
            top_menu_order_type = "exact"
        elif top_menu_conf >= 0.56:
            top_menu_order_type = "likely"
        else:
            top_menu_order_type = "estimated"
    top_menu_name = str(top_menu_item.get("item_name") or "").strip()
    # Provenance-first gate: item_provenance is the canonical "this is a real menu item" signal
    # (computed in menu_item_scoring). Source whitelist stays as legacy fallback for paths where
    # provenance is absent (older cache rows).
    top_item_provenance = str(menu_recommendations.get("item_provenance") or "").strip().lower()
    provenance_trusted = top_item_provenance in {"exact_chain_menu", "exact_menu"}
    provenance_rejected = top_item_provenance in {"heuristic_suggestion", "heuristic", "generic_fallback"}
    strong_real_menu = bool(
        top_menu_name
        and not provenance_rejected
        and top_menu_source in {
            "real_menu",
            "menu_intelligence_store",
            "structured_menu",
            "scraped_menu",
            "website_menu",
            "website_text",
            "review_text",
            "ocr_menu",
            "user_scan",
        }
        and top_menu_conf >= 0.45
    )
    strong_inferred_menu = bool(
        top_menu_name
        and not provenance_rejected
        and top_menu_source == "llm_inferred"
        and top_menu_conf >= 0.76
        and top_menu_order_type in {"likely", "exact"}
    )
    use_menu_order = bool(
        top_menu_name
        and (
            provenance_trusted
            or strong_real_menu
            or strong_inferred_menu
        )
    )
    if use_menu_order:
        best_order = top_menu_name
        estimated_calories = int(_safe_float(top_menu_item.get("estimated_calories"), estimated_calories) or estimated_calories)
        estimated_protein_g = int(_safe_float(top_menu_item.get("estimated_protein_g"), estimated_protein_g) or estimated_protein_g)
    final_order_confidence = round(
        float(
            _safe_float(
                top_menu_conf if use_menu_order else order_suggestion.get("order_confidence"),
                _safe_float(order_suggestion.get("order_confidence"), 0.46),
            )
            or 0.46
        ),
        2,
    )
    order_type = top_menu_order_type if use_menu_order else str(order_suggestion.get("order_type") or "estimated")
    if order_type not in {"exact", "likely", "estimated"}:
        order_type = "estimated"
    swap_suggestion = str(
        (top_menu_item.get("swap_suggestion") if use_menu_order else "")
        or order_suggestion.get("swap_suggestion")
        or order_suggestion.get("better_swap")
        or "Skip heavy sides and add a lighter side."
    )
    skip_items = (
        top_menu_item.get("skip_items")
        if use_menu_order and isinstance(top_menu_item.get("skip_items"), list)
        else order_suggestion.get("skip_items")
        if isinstance(order_suggestion.get("skip_items"), list)
        else []
    )
    add_items = (
        top_menu_item.get("add_items")
        if use_menu_order and isinstance(top_menu_item.get("add_items"), list)
        else order_suggestion.get("add_items")
        if isinstance(order_suggestion.get("add_items"), list)
        else []
    )
    swap_suggestions = build_swap_suggestions(
        swap_suggestion=swap_suggestion,
        skip_items=skip_items if isinstance(skip_items, list) else [],
        add_items=add_items if isinstance(add_items, list) else [],
        better_swap=order_suggestion.get("better_swap"),
        place_context=" ".join(
            [
                str(p.get("name") or ""),
                str(p.get("vicinity") or p.get("address") or ""),
                " ".join(str(t or "") for t in (p.get("types") if isinstance(p.get("types"), list) else [])),
            ]
        ),
        menu_item_source=(
            top_menu_item.get("menu_item_source")
            or menu_recommendations.get("menu_source_resolved")
            or menu_recommendations.get("menu_items_source_resolved")
            or menu_recommendations.get("menu_source")
            or menu_recommendations.get("menu_items_source")
            or "heuristic"
        ),
        menu_item_confidence=(
            top_menu_item.get("menu_item_confidence")
            or top_menu_item.get("confidence")
            or final_order_confidence
        ),
        max_items=3,
    )
    decision_estimated_calories = int(
        _safe_float(top_menu_item.get("estimated_calories"), estimated_calories) or estimated_calories
    )
    decision_estimated_protein_g = int(
        _safe_float(top_menu_item.get("estimated_protein_g"), estimated_protein_g) or estimated_protein_g
    )
    short_reason = str(
        (top_menu_item.get("short_reason") if use_menu_order else "")
        or order_suggestion.get("short_reason")
        or "Balanced default when menu details are limited."
    )
    order_strategy_tags = (
        order_suggestion.get("order_strategy_tags")
        if isinstance(order_suggestion.get("order_strategy_tags"), list)
        else ["high_protein", "better_swap", "fat_loss_friendly"]
    )
    recommended_badges = (
        scoring.get("recommended_badges")
        if isinstance(scoring.get("recommended_badges"), list)
        else []
    )

    personalized_health_score = None
    personalized_best_order = ""
    personalized_reason = ""

    if personalization_goal:
        try:
            personalized_scoring = score_healthy_place(
                p,
                mode=nutrition_mode,
                personalization_goal=personalization_goal,
                menu_payload=menu_recommendations,
            )
            personalized_health_score = round(
                max(1.0, min(10.0, float(_safe_float(personalized_scoring.get("health_score"), score) or score))),
                1,
            )
        except Exception:
            personalized_health_score = round(max(1.0, min(10.0, score)), 1)

        try:
            personalized_order = suggest_best_order_for_place(
                p,
                health_score=float(personalized_health_score),
                mode=nutrition_mode,
                personalization_goal=personalization_goal,
                diet_preference=diet_preference_val,
            )
            personalized_best_order = str(
                personalized_order.get("personalized_best_order")
                or personalized_order.get("best_order")
                or best_order
            )
            personalized_reason = str(
                personalized_order.get("personalized_reason")
                or get_personalized_reason(personalization_goal)
                or ""
            )
        except Exception:
            personalized_best_order = best_order
            personalized_reason = str(get_personalized_reason(personalization_goal) or "")

    if (not use_menu_order) and should_use_honest_no_menu_order_copy(
        strong_menu_evidence=top_menu_evidence,
        menu_item_source=top_menu_source,
        menu_item_confidence=top_menu_conf,
    ):
        ho, _honest_lbl = honest_no_menu_order_copy(menu_context_text)
        best_order = ho
        if str(personalized_best_order or "").strip():
            personalized_best_order = ho

    decision_today = evaluate_place_for_today(
        estimated_calories=decision_estimated_calories,
        estimated_protein_g=decision_estimated_protein_g,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        health_score=score,
    )
    covered_chain_key = str(
        menu_recommendations.get("covered_chain_key")
        or menu_recommendations.get("chain_key")
        or p.get("chain_key")
        or ""
    ).strip()
    item_provenance = str(menu_recommendations.get("item_provenance") or "").strip().lower() or None
    if not item_provenance and covered_chain_key:
        _trusted_sources = {"chain_registry", "ingested_chain_item"}
        _source_hint = str(top_menu_item.get("menu_item_source") or "").strip().lower()
        if not _source_hint:
            _source_hint = str(
                menu_recommendations.get("menu_source_resolved")
                or menu_recommendations.get("menu_items_source_resolved")
                or menu_recommendations.get("menu_source")
                or menu_recommendations.get("menu_items_source")
                or ""
            ).strip().lower()
        if _source_hint in _trusted_sources and str(top_menu_item.get("item_name") or "").strip():
            item_provenance = "exact_chain_menu"
        else:
            item_provenance = "heuristic_suggestion"
    covered_chain_neutral = bool(menu_recommendations.get("covered_chain_neutral", item_provenance == "heuristic_suggestion"))
    fit_for_today = (str(decision_today.get("decision_today") or "").strip().upper() != "NO")
    place_name = str(p.get("name") or "Unknown place").strip()
    cuisine_hint = ", ".join(
        str(t or "").replace("_", " ") for t in (p.get("types") or [])[:3]
        if t and str(t) not in {"restaurant", "food", "point_of_interest", "establishment", "meal_takeaway"}
    )
    _lat = float(_safe_float(p.get("lat"), 0.0) or 0.0)
    _lng = float(_safe_float(p.get("lng"), 0.0) or 0.0)
    _dist_m = int(max(0, (math.hypot((_lat - float(lat)) * 111320, (_lng - float(lng)) * 111320 * max(0.7, math.cos(math.radians(_lat)))) * 1000))) if (_lat and _lng) else 2000
    place_for_ranking = {
        "name": place_name,
        "cuisine_hint": cuisine_hint,
        "recommended_order": best_order,
        "best_order": best_order,
        "decision_today": decision_today.get("decision_today"),
        "fit_for_today": fit_for_today,
        "estimated_calories": estimated_calories,
        "estimated_protein_g": estimated_protein_g,
        "menu_item_confidence": final_order_confidence,
        "order_confidence": final_order_confidence,
        "distance_meters": _dist_m,
        "menu_item_source": top_menu_source,
        "item_provenance": item_provenance,
        "covered_chain_key": covered_chain_key or None,
        "covered_chain_neutral": covered_chain_neutral,
        "health_score": score,
        "fit_today_score_100": decision_today.get("fit_today_score_100"),
        "calorie_fit_score_100": decision_today.get("calorie_fit_score_100"),
        "protein_fit_score_100": decision_today.get("protein_fit_score_100"),
        "overshoot_penalty_100": decision_today.get("overshoot_penalty_100"),
        "chain_key": menu_recommendations.get("chain_key"),
        "chain_id": menu_recommendations.get("chain_id"),
        "chain_name": menu_recommendations.get("chain_name"),
        "item_provenance": menu_recommendations.get("item_provenance"),
        "covered_chain_key": menu_recommendations.get("covered_chain_key"),
        "covered_chain_neutral": menu_recommendations.get("covered_chain_neutral"),
        "can_show_verified_badge": menu_recommendations.get("can_show_verified_badge"),
        "covered_chain_display_name": menu_recommendations.get("covered_chain_display_name"),
        "covered_chain_menu_url": menu_recommendations.get("covered_chain_menu_url"),
    }
    context_info_raw = {
        "remaining_calories": remaining_calories,
        "remaining_protein_g": remaining_protein_g,
        "post_workout": bool(post_workout),
        "late_night": bool(late_night),
        "poor_sleep_flag": bool(poor_sleep_flag),
        "high_craving_risk_flag": bool(high_craving_risk_flag),
        "context_mode_override": (context_mode or "").strip() or None,
        "local_hour": int(local_hour) if local_hour is not None else 12,
    }
    ctx_modes = infer_context_mode(context_info_raw)
    context_info = {**context_info_raw, **ctx_modes}
    user_context_meal = {
        "remaining_protein_g": remaining_protein_g,
        "cut_mode": bool(cut_mode),
        "goal": personalization_goal_value_str,
        "context_info": context_info,
        "diet_preference": diet_preference_val,
    }
    mem_dict = None
    if str(user_id or "").strip():
        try:
            mem = get_personal_meal_memory(
                user_id=user_id,
                place_id=str(p.get("place_id") or p.get("id") or ""),
                place_name=place_name,
                item_name=best_order,
                goal=goal,
                time_of_day="",
                _feedback_events=ctx.feedback_events_prefetch,
                _decision_events=ctx.decision_events_prefetch,
            )
            mem_dict = mem.to_dict()
            user_context_meal["personal_memory"] = mem
        except Exception:
            mem_dict = None

    ranking_fields = build_ranked_place_profile(place_for_ranking, user_context_meal)

    reality_check = build_restaurant_reality_check(
        p,
        recommended_order={
            "item_name": str(top_menu_item.get("item_name") or order_suggestion.get("best_order") or best_order),
            "estimated_calories": int(max(0, decision_estimated_calories)),
            "estimated_protein_g": int(max(0, decision_estimated_protein_g)),
            "confidence": float(
                _safe_float(
                    top_menu_item.get("confidence"),
                    _safe_float(final_order_confidence, 0.52),
                )
                or 0.52
            ),
            "menu_item_source": str(
                top_menu_item.get("menu_item_source")
                or menu_recommendations.get("menu_items_source")
                or "heuristic"
            ),
            "menu_item_confidence": float(
                _safe_float(
                    top_menu_item.get("menu_item_confidence"),
                    _safe_float(top_menu_item.get("confidence"), _safe_float(final_order_confidence, 0.52)),
                )
                or 0.52
            ),
            "order_type": order_type,
            "swap_suggestion": swap_suggestion,
            "swap_suggestions": swap_suggestions,
            "skip_items": skip_items if isinstance(skip_items, list) else [],
            "add_items": add_items if isinstance(add_items, list) else [],
        },
        context={
            "top_menu_item": top_menu_item,
            "top_menu_items": (
                menu_recommendations.get("top_menu_items")
                if isinstance(menu_recommendations.get("top_menu_items"), list)
                else []
            ),
            "health_score": score,
            "mode": nutrition_mode.value,
            "goal": personalization_goal_value_str,
        },
        use_llm_copy=False,
        allow_llm_macro=False,
    )

    return {
        "place_id": str(p.get("place_id") or p.get("id") or ""),
        "name": p.get("name"),
        "lat": p.get("lat"),
        "lng": p.get("lng"),
        "health_score": round(max(1.0, min(10.0, score)), 1),
        "best_options": options,
        "address": p.get("vicinity"),
        "rating": p.get("rating"),
        "score_breakdown": scoring.get("score_breakdown"),
        "fat_loss_friendly": bool(scoring.get("fat_loss_friendly")),
        "recommended_badges": recommended_badges,
        "nutrition_data_available": bool(scoring.get("nutrition_data_available", False)),
        "menu_health_signals": scoring.get("menu_health_signals") if isinstance(scoring.get("menu_health_signals"), dict) else None,
        "menu_distribution_score": float(_safe_float(scoring.get("menu_distribution_score"), 0.0) or 0.0),
        "menu_dominance": float(_safe_float(scoring.get("menu_dominance"), 0.0) or 0.0),
        "scoring_version": str(scoring.get("scoring_version") or HEALTHY_PLACE_SCORING_VERSION),
        "best_order": best_order,
        "better_swap": str(
            (top_menu_item.get("swap_suggestion") if use_menu_order else "")
            or order_suggestion.get("better_swap")
            or "Pick water and keep sauces on the side"
        ),
        "swap_suggestion": swap_suggestion,
        "swap_suggestions": swap_suggestions,
        "best_item_swaps": (
            top_menu_item.get("best_item_swaps")
            if use_menu_order and isinstance(top_menu_item.get("best_item_swaps"), list)
            else []
        ),
        "skip_items": skip_items if isinstance(skip_items, list) else [],
        "add_items": add_items if isinstance(add_items, list) else [],
        "order_type": order_type,
        "avoid_if_cutting": order_suggestion.get("avoid_if_cutting", "Large fried combo meals"),
        "estimated_calories": estimated_calories,
        "estimated_protein_g": estimated_protein_g,
        "estimated_carbs_g": int(_safe_float(order_suggestion.get("estimated_carbs_g"), 45) or 45),
        "estimated_fat_g": int(_safe_float(order_suggestion.get("estimated_fat_g"), 18) or 18),
        "estimated_satiety": str(order_suggestion.get("estimated_satiety") or "medium"),
        "macro_confidence": round(float(_safe_float(order_suggestion.get("macro_confidence"), 0.52) or 0.52), 2),
        "macro_estimation_version": str(order_suggestion.get("macro_estimation_version") or "v1"),
        "order_confidence": final_order_confidence,
        "short_reason": short_reason,
        "order_strategy_tags": order_strategy_tags,
        "recommendation_version": str(order_suggestion.get("recommendation_version") or "v1"),
        "cut_mode_active": bool(order_suggestion.get("cut_mode_active", bool(cut_mode))),
        "cut_friendly": bool(order_suggestion.get("cut_friendly", scoring.get("cut_friendly", False))),
        "cut_warning": str(order_suggestion.get("cut_warning") or scoring.get("cut_warning") or ""),
        "best_order_for_cut": str(order_suggestion.get("best_order_for_cut") or order_suggestion.get("best_order") or "Lighter menu option"),
        "personalization_goal": personalization_goal_value_str,
        "personalized_health_score": personalized_health_score,
        "personalized_best_order": personalized_best_order,
        "personalized_reason": personalized_reason,
        "menu_item_scoring_available": bool(menu_recommendations.get("menu_item_scoring_available", False)),
        "menu_items_source": str(menu_recommendations.get("menu_items_source") or "heuristic"),
        "menu_source": str(menu_recommendations.get("menu_source") or menu_recommendations.get("menu_items_source") or "heuristic"),
        "menu_items_source_resolved": str(
            menu_recommendations.get("menu_items_source_resolved")
            or menu_recommendations.get("menu_source_resolved")
            or menu_recommendations.get("menu_items_source")
            or "heuristic"
        ),
        "menu_source_resolved": str(
            menu_recommendations.get("menu_source_resolved")
            or menu_recommendations.get("menu_items_source_resolved")
            or menu_recommendations.get("menu_source")
            or menu_recommendations.get("menu_items_source")
            or "heuristic"
        ),
        "menu_source_priority": int(_safe_float(menu_recommendations.get("menu_source_priority"), 1) or 1),
        "menu_confidence": float(_safe_float(menu_recommendations.get("menu_confidence"), 0.0) or 0.0),
        "menu_item_source": str(top_menu_item.get("menu_item_source") or ""),
        "menu_item_confidence": float(_safe_float(top_menu_item.get("menu_item_confidence"), 0.0) or 0.0),
        "source_rank_weight": float(_safe_float(top_menu_item.get("source_rank_weight"), 0.0) or 0.0),
        "menu_item_safety_reason": str(top_menu_item.get("menu_item_safety_reason") or ""),
        "restaurant_rank_reason": "",
        "extraction_method": str(menu_recommendations.get("extraction_method") or ""),
        "parse_method": str(menu_recommendations.get("parse_method") or ""),
        "source_url": str(menu_recommendations.get("source_url") or ""),
        "top_menu_items": menu_recommendations.get("top_menu_items") if isinstance(menu_recommendations.get("top_menu_items"), list) else [],
        "best_menu_items": menu_recommendations.get("best_menu_items") if isinstance(menu_recommendations.get("best_menu_items"), list) else [],
        "top_menu_item": menu_recommendations.get("top_menu_item") if isinstance(menu_recommendations.get("top_menu_item"), dict) else None,
        "chain_key": menu_recommendations.get("chain_key"),
        "chain_id": menu_recommendations.get("chain_id"),
        "item_provenance": item_provenance,
        "covered_chain_key": covered_chain_key or None,
        "covered_chain_neutral": covered_chain_neutral,
        "covered_chain_display_name": str(menu_recommendations.get("covered_chain_display_name") or ""),
        "covered_chain_menu_url": str(menu_recommendations.get("covered_chain_menu_url") or ""),
        "top_item": str(menu_recommendations.get("top_item") or ""),
        "diet_preference": diet_preference_val,
        "_diet_excluded_candidate_count": p.get("_diet_excluded_candidate_count"),
        "decision_today": decision_today.get("decision_today"),
        "decision_reason": str(decision_today.get("decision_reason") or ""),
        "fits_remaining_calories": decision_today.get("fits_remaining_calories"),
        "fits_remaining_protein": decision_today.get("fits_remaining_protein"),
        "decision_confidence": decision_today.get("decision_confidence"),
        "reality_check": reality_check,
        "reality_check_share_card": (
            reality_check.get("share_card") if isinstance(reality_check.get("share_card"), dict) else None
        ),
        "share_card": build_best_order_share_card(
            place_name=p.get("name"),
            health_score=score,
            best_order=best_order,
            estimated_calories=estimated_calories,
            estimated_protein_g=estimated_protein_g,
            subtitle=short_reason,
            recommended_badges=recommended_badges,
            order_strategy_tags=order_strategy_tags,
            cut_friendly=bool(order_suggestion.get("cut_friendly", False)),
            fat_loss_friendly=bool(scoring.get("fat_loss_friendly", False)),
            calories_saved=(
                reality_check.get("calories_saved") if isinstance(reality_check, dict) else None
            ),
        ),
        **ranking_fields,
        "candidate_source_label": top_menu_source.replace("_", " ").title(),
        **(mem_dict or {}),
    }


def build_rank_context_from_request(
    *,
    lat: float,
    lng: float,
    cut_mode: bool,
    goal: str,
    nutrition_mode: NutritionMode,
    personalization_goal: Optional[PersonalizationGoal],
    personalization_goal_value_str: str,
    diet_preference: str,
    remaining_calories: Optional[float],
    remaining_protein_g: Optional[float],
    post_workout: bool,
    late_night: bool,
    poor_sleep_flag: bool,
    high_craving_risk_flag: bool,
    context_mode: str,
    local_hour: Optional[int],
    user_id: str,
    feedback_events_prefetch: Optional[List[Dict[str, Any]]] = None,
    decision_events_prefetch: Optional[List[Dict[str, Any]]] = None,
) -> HealthyNearbyRankContext:
    diet_preference_val = normalize_diet_preference(diet_preference) if str(diet_preference or "").strip() else "omnivore"
    return HealthyNearbyRankContext(
        lat=float(lat),
        lng=float(lng),
        cut_mode=bool(cut_mode),
        goal=str(goal or "").strip(),
        nutrition_mode=nutrition_mode,
        personalization_goal=personalization_goal,
        personalization_goal_value_str=personalization_goal_value_str,
        diet_preference_val=diet_preference_val,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        post_workout=bool(post_workout),
        late_night=bool(late_night),
        poor_sleep_flag=bool(poor_sleep_flag),
        high_craving_risk_flag=bool(high_craving_risk_flag),
        context_mode=str(context_mode or "").strip(),
        local_hour=local_hour,
        user_id=str(user_id or "").strip(),
        feedback_events_prefetch=feedback_events_prefetch,
        decision_events_prefetch=decision_events_prefetch,
    )

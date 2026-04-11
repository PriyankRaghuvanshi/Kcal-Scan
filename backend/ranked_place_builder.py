"""
Canonical ranking builder for Healthy Nearby.

Single source of truth for all ranking-related fields. Call build_ranked_place_profile
and merge the result into the place; do not recompute ranking in lunch_decision, main, or healthy_food_map.
"""
from __future__ import annotations

from typing import Any, Dict

from meal_ranking import (
    LABEL_BEST_PICK,
    LABEL_NEEDS_MENU_CHECK,
    LABEL_STRONG_OPTION,
    LABEL_SUGGESTED_HEALTHIER,
    _is_generic_fallback,
    compute_eligibility_band,
    compute_meal_fitness_score,
    recommendation_label_and_section,
    why_this_ranked_here_short,
)
from personal_response_summary import compute_personal_memory_modifier
from context_scoring import compute_context_modifier
from place_trace_debug import infer_specificity_tier, get_specificity_bonus_100


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _confidence_label(menu_item_source: str, menu_item_confidence: float, diet_preference: str = "") -> str:
    """Deterministic: Verified | Estimated | Needs menu check. Vegan + weak inference -> prefer weaker label."""
    source = str(menu_item_source or "heuristic").strip().lower()
    conf = _safe_float(menu_item_confidence, 0.5)
    diet = str(diet_preference or "").strip().lower()
    if diet == "vegan" and source == "heuristic" and conf < 0.60:
        return "Needs menu check"
    if source in ("real_menu", "user_scan", "menu_intelligence_store", "structured_menu", "exact_menu_cache", "chain_registry", "ingested_chain_item") and conf >= 0.72:
        return "Verified"
    if source in ("chain_registry", "ingested_chain_item") and conf >= 0.60:
        return "Chain-backed"
    if conf >= 0.55 or source == "llm_inferred":
        return "Estimated"
    return "Needs menu check"


def _rank_reason_short(
    display_rank_score_100: float,
    protein_g: float,
    calories: int,
    recommendation_label: str,
    is_generic_fallback: bool,
    fit_today_score_100: float,
) -> str:
    """One short deterministic reason line per place (no LLM)."""
    if is_generic_fallback:
        return "Good fallback, but check menu for best pick."
    if recommendation_label == LABEL_NEEDS_MENU_CHECK:
        return "Needs menu confirmation."
    if _safe_float(fit_today_score_100, 50) >= 75 and protein_g >= 30:
        return f"{int(protein_g)}g protein, fits today."
    if display_rank_score_100 >= 70 and protein_g >= 25:
        return "Higher protein, better whole-food option."
    if calories < 450 and protein_g < 22:
        return "Lower calorie but weaker protein."
    if display_rank_score_100 >= 55:
        return "Reasonable option; check menu for exact items."
    return "Needs menu check for best pick."


def build_ranked_place_profile(
    place: Dict[str, Any],
    user_context: Dict[str, Any],
    *,
    for_map: bool = False,
    for_list: bool = False,
) -> Dict[str, Any]:
    """
    Single source of truth for ranking fields. Place must already have:
    name, recommended_order or best_order, estimated_calories, estimated_protein_g,
    menu_item_source, menu_item_confidence, order_confidence, distance_meters, cuisine_hint,
    decision_today, fit_for_today. Optional: fit_today_score_100, calorie_fit_score_100,
    protein_fit_score_100, overshoot_penalty_100, health_score (for venue_prior_score_100).

    Returns only ranking-related keys to merge into the place.
    """
    # Covered-chain neutral state: if the scoring layer found no exact chain items,
    # suppress the recommendation entirely rather than showing a fallback.
    covered_chain_neutral = bool(place.get("covered_chain_neutral"))
    item_provenance = str(place.get("item_provenance") or "").strip() or None
    covered_chain_key = str(place.get("covered_chain_key") or "").strip() or None
    can_show_verified = bool(place.get("can_show_verified_badge"))

    if covered_chain_neutral:
        best_order = ""
    else:
        best_order = str(place.get("recommended_order") or place.get("best_order") or "").strip() or "Lighter menu option"
    place_profile = {
        "name": str(place.get("name") or "").strip(),
        "cuisine_hint": str(place.get("cuisine_hint") or ""),
        "recommended_order": best_order,
        "best_order": best_order,
        "decision_today": place.get("decision_today"),
        "fit_for_today": place.get("fit_for_today"),
        "estimated_calories": _safe_float(place.get("estimated_calories"), 520.0),
        "estimated_protein_g": _safe_float(place.get("estimated_protein_g"), 32.0),
        "menu_item_confidence": _safe_float(place.get("menu_item_confidence") or place.get("order_confidence"), 0.5),
        "order_confidence": _safe_float(place.get("order_confidence") or place.get("menu_item_confidence"), 0.5),
        "distance_meters": _safe_float(place.get("distance_meters"), 2000.0),
        "menu_item_source": str(place.get("menu_item_source") or "heuristic").strip().lower(),
    }
    ctx = {
        "fit_today_score_100": place.get("fit_today_score_100") or user_context.get("fit_today_score_100"),
        "calorie_fit_score_100": place.get("calorie_fit_score_100") or user_context.get("calorie_fit_score_100"),
        "protein_fit_score_100": place.get("protein_fit_score_100") or user_context.get("protein_fit_score_100"),
        "overshoot_penalty_100": place.get("overshoot_penalty_100") or user_context.get("overshoot_penalty_100"),
        "remaining_protein_g": user_context.get("remaining_protein_g"),
        "cut_mode": user_context.get("cut_mode"),
        "goal": user_context.get("goal"),
    }

    meal_result = compute_meal_fitness_score(place_profile, ctx)
    eligibility_band = compute_eligibility_band(place_profile, ctx)
    is_generic = _is_generic_fallback(best_order)
    chain_match_key = str(place.get("chain_key") or place.get("chain_id") or place.get("chain_name") or "").strip()
    tier = infer_specificity_tier(
        place_profile["menu_item_source"],
        best_order,
        chain_match_key or None,
    )
    specificity_bonus_100 = get_specificity_bonus_100(tier)
    rec_label, section = recommendation_label_and_section(
        eligibility_band,
        place_profile["menu_item_source"],
        place_profile["menu_item_confidence"],
        is_generic,
    )
    # Generic fallbacks must never be Best pick or Strong option
    if is_generic and rec_label == LABEL_BEST_PICK:
        rec_label = LABEL_SUGGESTED_HEALTHIER
    if is_generic and rec_label == LABEL_STRONG_OPTION:
        rec_label = LABEL_NEEDS_MENU_CHECK
    # Covered-chain neutral: no item to recommend
    if covered_chain_neutral:
        rec_label = LABEL_NEEDS_MENU_CHECK

    display_rank_score_100 = round(meal_result["meal_fitness_score_100"], 1)
    venue_prior_score_100 = int(round(_safe_float(place.get("health_score"), 5.0) * 10.0))
    if venue_prior_score_100 <= 0:
        venue_prior_score_100 = int(round(display_rank_score_100))

    diet_pref = str(user_context.get("diet_preference") or "").strip() or ""
    confidence_lbl = _confidence_label(place_profile["menu_item_source"], place_profile["menu_item_confidence"], diet_preference=diet_pref)
    # Override confidence label for covered-chain neutral (no exact item)
    if covered_chain_neutral:
        confidence_lbl = "Needs menu check"
    fit_today_100 = _safe_float(place.get("fit_today_score_100") or ctx.get("fit_today_score_100"), 50.0)
    rank_reason = _rank_reason_short(
        display_rank_score_100,
        place_profile["estimated_protein_g"],
        int(place_profile["estimated_calories"]),
        rec_label,
        is_generic,
        fit_today_100,
    )
    why_ranked = why_this_ranked_here_short(
        display_rank_score_100, eligibility_band, rec_label,
        place_profile["estimated_protein_g"], int(place_profile["estimated_calories"]),
    )

    breakdown = meal_result.get("score_breakdown") or {}
    food_quality_100 = breakdown.get("food_quality", 50.0)
    protein_density_100 = breakdown.get("protein_density", 50.0)
    # Optional personal-memory modifier (bounded, small).
    personal_memory = user_context.get("personal_memory") if isinstance(user_context, dict) else None
    memory_mod = compute_personal_memory_modifier(
        personal_memory,
        base_score_100=float(display_rank_score_100),
        food_quality_score_100=float(food_quality_100),
        protein_density_score_100=float(protein_density_100),
    )
    score_after_memory = display_rank_score_100 + float(memory_mod.get("personal_history_net_100") or 0.0)
    # Context modifier (bounded [-8, +8])
    context_info = user_context.get("context_info") if isinstance(user_context, dict) else {}
    context_mod = {
        "context_bonus_100": 0,
        "context_penalty_100": 0,
        "context_net_100": 0,
        "context_mode": "default",
        "context_reason": "neutral",
        "context_applied": False,
        "context_components": {},
    }
    if context_info:
        place_profile_for_context = {
            **place_profile,
            "meal_fitness_score_100": display_rank_score_100,
            "food_quality_score_100": food_quality_100,
            "protein_density_score_100": protein_density_100,
            "score_breakdown": breakdown,
        }
        context_mod = compute_context_modifier(
            place_profile_for_context,
            context_info,
            user_context,
        )
    context_net = int(context_mod.get("context_net_100") or 0)
    final_display_score_100 = score_after_memory + context_net
    if final_display_score_100 < 0:
        final_display_score_100 = 0.0
    if final_display_score_100 > 100:
        final_display_score_100 = 100.0

    # Specificity-aware sort score: tie-break favoring chain/menu over generic
    display_sort_score_100 = min(100.0, max(0.0, final_display_score_100 + float(specificity_bonus_100)))

    return {
        "display_rank_score_100": int(round(final_display_score_100)),
        "display_sort_score_100": round(display_sort_score_100, 1),
        "chosen_candidate_specificity_tier": tier,
        "specificity_bonus_100": specificity_bonus_100,
        "meal_fitness_score_100": round(meal_result["meal_fitness_score_100"], 1),
        "meal_fitness_score": meal_result.get("meal_fitness_score", display_rank_score_100 / 10.0),
        "venue_prior_score_100": venue_prior_score_100,
        "eligibility_band": eligibility_band,
        "section": section,
        "recommendation_label": rec_label,
        "confidence_label": confidence_lbl,
        "why_this_ranked_here": why_ranked,
        "rank_reason_short": rank_reason,
        "score_breakdown": breakdown,
        "personal_history_bonus_100": memory_mod.get("personal_history_bonus_100"),
        "personal_history_penalty_100": memory_mod.get("personal_history_penalty_100"),
        "personal_history_net_100": memory_mod.get("personal_history_net_100"),
        "personal_memory_reason": memory_mod.get("personal_memory_reason"),
        "memory_sample_count": memory_mod.get("memory_sample_count"),
        "memory_applied": memory_mod.get("memory_applied"),
        "fit_today_score_100": round(_safe_float(place.get("fit_today_score_100") or ctx.get("fit_today_score_100"), 50.0), 1),
        "calorie_fit_score_100": round(_safe_float(place.get("calorie_fit_score_100") or ctx.get("calorie_fit_score_100"), 50.0), 1),
        "protein_fit_score_100": round(_safe_float(place.get("protein_fit_score_100") or ctx.get("protein_fit_score_100"), 50.0), 1),
        "overshoot_penalty_100": round(_safe_float(place.get("overshoot_penalty_100") or ctx.get("overshoot_penalty_100"), 0.0), 1),
        "best_item_name": best_order if not covered_chain_neutral else "",
        "best_item_calories": int(max(0, place_profile["estimated_calories"])) if not covered_chain_neutral else 0,
        "best_item_protein": int(max(0, place_profile["estimated_protein_g"])) if not covered_chain_neutral else 0,
        "best_item_source": place_profile["menu_item_source"],
        "best_item_is_generic_fallback": is_generic or covered_chain_neutral,
        "best_item_needs_menu_check": confidence_lbl == "Needs menu check" or rec_label == LABEL_NEEDS_MENU_CHECK,
        "item_provenance": item_provenance or ("exact_chain_menu" if not covered_chain_neutral and covered_chain_key else None),
        "can_show_verified_badge": can_show_verified and not covered_chain_neutral,
        "covered_chain_key": covered_chain_key,
        "covered_chain_neutral": covered_chain_neutral,
        "food_quality_score_100": round(food_quality_100, 1),
        "protein_density_score_100": round(protein_density_100, 1),
        "context_bonus_100": context_mod.get("context_bonus_100"),
        "context_penalty_100": context_mod.get("context_penalty_100"),
        "context_net_100": context_mod.get("context_net_100"),
        "context_mode": context_mod.get("context_mode"),
        "context_reason": context_mod.get("context_reason"),
        "context_applied": context_mod.get("context_applied"),
        "context_components": context_mod.get("context_components"),
    }

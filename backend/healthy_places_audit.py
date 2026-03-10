"""
Developer audit helpers for Healthy Nearby ranking.
Inspection only; no ranking logic. No LLM.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _safe_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except Exception:
        return default


def build_audit_one_liner(place: Dict[str, Any], rank: int) -> str:
    """Deterministic one-line audit string for tuning. Example:
    #1 Darbar | Score 84 (+3 personal, +2 context) | Band 3 | Best pick | Verified | Tandoori chicken + dal | 610 kcal | 42g protein | Higher protein, better whole-food option
    """
    name = _safe_str(place.get("name") or place.get("place_name"), "?")
    score = _safe_int(place.get("display_rank_score_100"), 0)
    net = _safe_int(place.get("personal_history_net_100"), 0)
    ctx_net = place.get("context_net_100")
    band = _safe_int(place.get("eligibility_band"), 0)
    rec = _safe_str(place.get("recommendation_label"), "")
    conf = _safe_str(place.get("confidence_label"), "")
    item = _safe_str(place.get("best_item_name") or place.get("best_order"), "")
    cal = _safe_int(place.get("best_item_calories") or place.get("estimated_calories"), 0)
    pro = _safe_int(place.get("best_item_protein") or place.get("estimated_protein_g"), 0)
    reason = _safe_str(place.get("rank_reason_short") or place.get("why_this_ranked_here"), "")
    swaps = place.get("best_item_swaps") or (place.get("top_menu_item") or {}).get("best_item_swaps") or []
    swap_hint = ""
    if isinstance(swaps, list) and swaps:
        first = swaps[0] if isinstance(swaps[0], dict) else None
        if first:
            swap_label = _safe_str(first.get("swap_label"), "")
            if swap_label:
                swap_hint = f"Swap: {swap_label}"
    score_suffix = ""
    if net != 0 or (ctx_net is not None and ctx_net != 0):
        parts_list = []
        if net != 0:
            parts_list.append(f"{'+' if net > 0 else ''}{net} personal")
        if ctx_net is not None and ctx_net != 0:
            parts_list.append(f"{'+' if ctx_net > 0 else ''}{ctx_net} context")
        score_suffix = " (" + ", ".join(parts_list) + ")"
    parts = [
        f"#{rank}",
        name,
        f"Score {score}{score_suffix}",
        f"Band {band}",
        rec or "-",
        conf or "-",
        item or "-",
        f"{cal} kcal",
        f"{pro}g protein",
    ]
    if reason:
        parts.append(reason)
    if swap_hint:
        parts.append(swap_hint)
    return " | ".join(parts)


def build_audit_result_row(place: Dict[str, Any], rank: int, *, include_candidate_debug: bool = False) -> Dict[str, Any]:
    """Build one audit result entry with all required fields. Optionally add candidate_debug."""
    breakdown = place.get("score_breakdown") or {}
    penalties = breakdown.get("penalties") if isinstance(breakdown.get("penalties"), dict) else {}
    top = place.get("top_menu_item") if isinstance(place.get("top_menu_item"), dict) else {}
    swaps = place.get("best_item_swaps")
    if swaps is None and isinstance(top, dict):
        swaps = top.get("best_item_swaps")
    row = {
        "rank": rank,
        "place_name": _safe_str(place.get("name") or place.get("place_name")),
        "place_id": _safe_str(place.get("place_id")),
        "distance_m": _safe_int(place.get("distance_meters")),
        "display_rank_score_100": place.get("display_rank_score_100"),
        "meal_fitness_score_100": place.get("meal_fitness_score_100"),
        "venue_prior_score_100": place.get("venue_prior_score_100"),
        "eligibility_band": place.get("eligibility_band"),
        "section": _safe_str(place.get("section")),
        "recommendation_label": _safe_str(place.get("recommendation_label")),
        "confidence_label": _safe_str(place.get("confidence_label")),
        "rank_reason_short": _safe_str(place.get("rank_reason_short")),
        "why_this_ranked_here": _safe_str(place.get("why_this_ranked_here")),
        "best_item_name": _safe_str(place.get("best_item_name") or place.get("best_order")),
        "best_item_calories": place.get("best_item_calories") or place.get("estimated_calories"),
        "best_item_protein": place.get("best_item_protein") or place.get("estimated_protein_g"),
        "best_item_source": _safe_str(place.get("best_item_source")),
        "best_item_is_generic_fallback": bool(place.get("best_item_is_generic_fallback")),
        "best_item_needs_menu_check": bool(place.get("best_item_needs_menu_check")),
        "fit_today_score_100": place.get("fit_today_score_100"),
        "calorie_fit_score_100": place.get("calorie_fit_score_100"),
        "protein_fit_score_100": place.get("protein_fit_score_100"),
        "overshoot_penalty_100": place.get("overshoot_penalty_100"),
        "selected_candidate_source": _safe_str(place.get("menu_item_source") or top.get("menu_item_source") or place.get("best_item_source")),
        "candidate_source_priority": place.get("menu_source_priority"),
        "best_item_swaps": swaps if isinstance(swaps, list) else [],
        "personal_history_bonus_100": place.get("personal_history_bonus_100"),
        "personal_history_penalty_100": place.get("personal_history_penalty_100"),
        "personal_history_net_100": place.get("personal_history_net_100"),
        "personal_memory_reason": _safe_str(place.get("personal_memory_reason")),
        "memory_sample_count": place.get("memory_sample_count"),
        "memory_applied": bool(place.get("memory_applied")),
        "context_bonus_100": place.get("context_bonus_100"),
        "context_penalty_100": place.get("context_penalty_100"),
        "context_net_100": place.get("context_net_100"),
        "context_mode": _safe_str(place.get("context_mode")),
        "context_reason": _safe_str(place.get("context_reason")),
        "context_applied": bool(place.get("context_applied")),
        "context_components": place.get("context_components") if isinstance(place.get("context_components"), dict) else {},
        "score_breakdown": {
            "macro_fit": breakdown.get("macro_fit"),
            "protein_density": breakdown.get("protein_density"),
            "food_quality": breakdown.get("food_quality"),
            "satiety": breakdown.get("satiety"),
            "confidence": breakdown.get("confidence"),
            "distance": breakdown.get("distance"),
            "price_value": breakdown.get("price_value"),
            "personal_history": breakdown.get("personal_history"),
            "penalties": {
                "ultra_processed_penalty": penalties.get("ultra_processed_penalty"),
                "combo_meal_penalty": penalties.get("combo_meal_penalty"),
                "deep_fried_penalty": penalties.get("deep_fried_penalty"),
                "sugary_drink_penalty": penalties.get("sugary_drink_penalty"),
                "hyper_palatable_penalty": penalties.get("hyper_palatable_penalty"),
                "low_protein_density_penalty": penalties.get("low_protein_density_penalty"),
                "generic_fallback_penalty": penalties.get("generic_fallback_penalty"),
                "overshoot_penalty": penalties.get("overshoot_penalty"),
            },
        },
        "audit_one_liner": build_audit_one_liner(place, rank),
    }
    if include_candidate_debug:
        row["candidate_debug"] = build_candidate_debug(place)
    return row


def build_candidate_debug(place: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build candidate_debug from top_menu_items for audit. Lightweight; only in audit context."""
    top = place.get("top_menu_items") or place.get("best_menu_items")
    if not isinstance(top, list):
        return []
    out = []
    for i, item in enumerate(top[:5]):
        if not isinstance(item, dict):
            continue
        name = _safe_str(item.get("item_name") or item.get("name"), "")
        if not name:
            continue
        out.append({
            "candidate_name": name,
            "estimated_calories": item.get("estimated_calories"),
            "estimated_protein_g": item.get("estimated_protein_g"),
            "candidate_source": _safe_str(item.get("menu_item_source") or item.get("menu_item_source_raw"), "heuristic"),
            "confidence": item.get("menu_item_confidence") or item.get("confidence"),
            "why_kept": "selected_as_primary" if i == 0 else "alternative",
        })
    return out


def build_filtered_out_entry(place: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """One filtered_out row for include_filtered_out=true."""
    name = _safe_str(place.get("name") or place.get("place_name"), "?")
    out = {
        "place_name": name,
        "reason_filtered_out": reason,
    }
    if place.get("menu_item_source") is not None:
        out["menu_item_source"] = _safe_str(place.get("menu_item_source"))
    if place.get("menu_item_confidence") is not None:
        out["menu_item_confidence"] = place.get("menu_item_confidence")
    if place.get("decision_today") is not None:
        out["decision_today"] = _safe_str(place.get("decision_today"))
    if place.get("display_rank_score_100") is not None:
        out["display_rank_score_100"] = place.get("display_rank_score_100")
    return out

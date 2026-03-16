"""
Place trace debug for Healthy Nearby.
Explains why a place like Subway did or did not appear in recommendations.
No LLM. Deterministic.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Specificity tiers: higher = more trustworthy (exact menu > chain > local profile > heuristic > generic)
TIER_EXACT_MENU_MATCH = "exact_menu_match"
TIER_CHAIN_REGISTRY = "chain_registry"
TIER_EXACT_LOCAL_PROFILE = "exact_local_profile"
TIER_ENRICHED_LOCAL_PROFILE = "enriched_local_profile"
TIER_MENU_INFERRED = "menu_inferred"
TIER_HEURISTIC_STRONG = "heuristic_cuisine_match_strong"
TIER_HEURISTIC_WEAK = "heuristic_cuisine_match_weak"
TIER_GENERIC_FALLBACK = "generic_fallback"

SPECIFICITY_TIERS = (
    TIER_EXACT_MENU_MATCH,
    TIER_CHAIN_REGISTRY,
    TIER_EXACT_LOCAL_PROFILE,
    TIER_ENRICHED_LOCAL_PROFILE,
    TIER_MENU_INFERRED,
    TIER_HEURISTIC_STRONG,
    TIER_HEURISTIC_WEAK,
    TIER_GENERIC_FALLBACK,
)

# Bounded specificity bonus/penalty for display ranking (tie-break only)
SPECIFICITY_BONUS_100: Dict[str, int] = {
    TIER_EXACT_MENU_MATCH: 5,
    TIER_CHAIN_REGISTRY: 4,
    TIER_EXACT_LOCAL_PROFILE: 5,
    TIER_ENRICHED_LOCAL_PROFILE: 4,
    TIER_MENU_INFERRED: 2,
    TIER_HEURISTIC_STRONG: 1,
    TIER_HEURISTIC_WEAK: 0,
    TIER_GENERIC_FALLBACK: -4,
}

# Safeguard: chain/menu-backed beats generic when core score gap <= this
SPECIFICITY_TIE_BREAK_THRESHOLD = 8

# Generic fallback item name tokens (including cuisine guesses like tandoori + dal + roti)
_GENERIC_FALLBACK_TOKENS = (
    "lighter menu option", "lighter option", "healthy option", "balanced meal",
    "egg + chicken plate", "egg and chicken plate", "tandoori + dal", "dal + roti",
    "tandoori + dal + roti",
    "grilled protein bowl", "protein bowl", "protein plate", "lean wrap", "protein wrap",
    "needs menu check", "recommended item", "best menu item", "smart choice",
)


def _safe_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _is_generic_fallback(item_name: str) -> bool:
    lower = str(item_name or "").strip().lower()
    return any(t in lower for t in _GENERIC_FALLBACK_TOKENS)


def infer_specificity_tier(
    menu_item_source: str,
    chosen_candidate_name: str,
    chain_match_key: Optional[str] = None,
) -> str:
    """
    Map menu_item_source + candidate name to specificity tier.
    """
    source = str(menu_item_source or "").strip().lower()
    name = str(chosen_candidate_name or "").strip()

    if _is_generic_fallback(name):
        return TIER_GENERIC_FALLBACK

    if source in ("real_menu", "user_scan", "menu_intelligence_store", "structured_menu", "scraped_menu", "website_menu", "website_text", "review_text", "ocr_menu", "ingested_chain_item", "exact_menu_cache", "enriched_local_profile", "local_venue_profile"):
        return TIER_EXACT_MENU_MATCH
    if source == "chain_registry" and chain_match_key:
        return TIER_CHAIN_REGISTRY
    if source == "chain_registry":
        return TIER_CHAIN_REGISTRY
    if source == "enriched_local_profile":
        return TIER_ENRICHED_LOCAL_PROFILE
    if source == "llm_inferred":
        return TIER_MENU_INFERRED
    if source in ("heuristic_cuisine_match_strong", "heuristic_cuisine_match"):
        return TIER_HEURISTIC_STRONG
    if source == "heuristic_cuisine_match_weak":
        return TIER_HEURISTIC_WEAK
    if source == "heuristic":
        # Infer from candidate name: strong cuisine-specific vs weak
        if any(t in name.lower() for t in ("6-inch", "grilled chicken sub", "chicken tikka", "idli", "dosa", "sashimi", "burrito bowl")):
            return TIER_HEURISTIC_STRONG
        return TIER_HEURISTIC_WEAK
    return TIER_HEURISTIC_WEAK


def get_specificity_bonus_100(tier: str) -> int:
    """Bounded bonus/penalty for display ranking."""
    return SPECIFICITY_BONUS_100.get(tier, 0)


def infer_hidden_reason(
    place: Dict[str, Any],
    visible_places: list,
    visible_rank: Optional[int],
    *,
    top_n_cutoff: int = 40,
) -> Optional[str]:
    """
    Best-effort deterministic reason why a fetched place is not visible.
    """
    if visible_rank is not None and visible_rank >= 1:
        return None  # Place IS visible

    source = str(place.get("menu_item_source") or place.get("best_item_source") or "").strip().lower()
    tier = str(place.get("chosen_candidate_specificity_tier") or "").strip()
    score = _safe_float(place.get("display_rank_score_100") or place.get("meal_fitness_score_100"), 0.0)
    is_generic = bool(place.get("best_item_is_generic_fallback"))

    # Check if it would be in top N by score
    if visible_places:
        cutoff_score = _safe_float(
            (visible_places[top_n_cutoff - 1] if len(visible_places) >= top_n_cutoff else visible_places[-1]).get("display_rank_score_100"),
            0.0,
        )
        if score < cutoff_score - 5:  # Clearly below cutoff
            return "low_score"
        if len(visible_places) >= top_n_cutoff and score <= cutoff_score:
            return "top_n_cutoff"

    if tier == TIER_GENERIC_FALLBACK and is_generic:
        return "generic_fallback_demoted"
    if source == "heuristic" and _safe_float(place.get("menu_item_confidence"), 0.5) < 0.50:
        return "confidence_too_low"
    # Chain match failed = we never got chain_registry; would have been in chain_menu_registry
    chain_key = place.get("chain_match_key") or place.get("chain_key") or place.get("chain_id")
    if not chain_key and "subway" in str(place.get("name") or "").lower():
        # Subway-like place without chain match
        return "chain_match_failed"
    return "low_score"


def build_place_trace(
    place: Dict[str, Any],
    *,
    user_context: Optional[Dict[str, Any]] = None,
    visible_rank: Optional[int] = None,
    visible_places: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Returns a debug trace for one place through the pipeline.
    Used by /places/healthy/trace to explain why Subway or any place is missing.
    """
    user_context = user_context or {}
    place_id = _safe_str(place.get("place_id") or place.get("id"))
    place_name = _safe_str(place.get("name") or place.get("place_name"))
    raw_types = place.get("types") if isinstance(place.get("types"), list) else []
    raw_place_types = ", ".join(str(t) for t in raw_types[:5]) if raw_types else ""

    recommended = str(place.get("recommended_order") or place.get("best_order") or place.get("best_item_name") or "").strip()
    chosen_candidate_name = recommended or "Lighter menu option"
    menu_source = str(place.get("menu_item_source") or place.get("best_item_source") or "heuristic").strip().lower()
    chain_match_key = _safe_str(place.get("chain_key") or place.get("chain_id") or place.get("chain_name"))
    cuisine_match_key = _safe_str(place.get("cuisine_hint") or place.get("matched_cuisine_id"))

    tier = infer_specificity_tier(menu_source, chosen_candidate_name, chain_match_key or None)
    specificity_bonus = get_specificity_bonus_100(tier)

    meal_fitness = _safe_float(place.get("meal_fitness_score_100"), 50.0)
    display_score = _safe_float(place.get("display_rank_score_100"), meal_fitness)
    eligibility_band = int(place.get("eligibility_band") or 1)
    section = _safe_str(place.get("section"), "Decent nearby options")

    fetched_but_hidden = visible_rank is None and visible_places is not None
    hidden_reason = None
    if fetched_but_hidden:
        hidden_reason = infer_hidden_reason(place, visible_places or [], None, top_n_cutoff=40)

    # Normalized place type (simplified)
    normalized_place_type = ""
    if raw_types:
        for t in raw_types:
            tstr = str(t or "").strip()
            if tstr and tstr not in ("point_of_interest", "establishment"):
                normalized_place_type = tstr.replace("_", " ")
                break

    candidate_count = len(place.get("top_menu_items") or place.get("best_menu_items") or [])
    if candidate_count == 0 and chosen_candidate_name:
        candidate_count = 1

    local_payload = place.get("_local_profile_payload") if isinstance(place.get("_local_profile_payload"), dict) else None
    matched_local = bool(local_payload)
    local_source = str(local_payload.get("local_profile_source") or "").strip() if local_payload else None
    local_conf = local_payload.get("local_profile_confidence") if local_payload and isinstance(local_payload.get("local_profile_confidence"), (int, float)) else None
    area_key = str(local_payload.get("local_profile_area_key") or "").strip() if local_payload else None
    not_used_reason = None
    if not matched_local and tier == TIER_GENERIC_FALLBACK:
        not_used_reason = "generic_fallback_only"
    elif not matched_local and chain_match_key:
        not_used_reason = "chain_candidate_preferred"
    elif not matched_local:
        not_used_reason = "no_local_profile" if not local_payload else "weak_name_match"

    trace = {
        "place_id": place_id,
        "place_name": place_name,
        "diet_preference": str(place.get("diet_preference") or "").strip() or None,
        "diet_excluded_candidate_count": place.get("_diet_excluded_candidate_count") or 0,
        "fallback_used": bool(place.get("best_item_is_generic_fallback") or (str(tier) == TIER_GENERIC_FALLBACK)),
        "fallback_reason": place.get("_fallback_reason") or ("generic_heuristic_only" if place.get("best_item_is_generic_fallback") else None),
        "fetched_from_places_api": True,  # If we have the place, it was fetched
        "raw_place_types": raw_place_types,
        "normalized_place_type": normalized_place_type,
        "chain_match_key": chain_match_key or None,
        "cuisine_match_key": cuisine_match_key or None,
        "area_key": area_key,
        "matched_local_profile": matched_local or bool(place.get("_matched_local_profile")),
        "local_profile_source": local_source or place.get("_local_profile_source"),
        "chosen_candidate_profile_source": place.get("_chosen_candidate_profile_source") or local_source or place.get("_local_profile_source"),
        "local_profile_confidence": local_conf or place.get("_local_profile_confidence"),
        "local_enrichment_used": matched_local or bool(place.get("_matched_local_profile")),
        "local_enrichment_not_used_reason": not_used_reason,
        "used_venue_intelligence_cache": bool(place.get("_used_venue_intelligence_cache")),
        "cache_source_type": place.get("_cache_source_type"),
        "cache_last_enriched_at": place.get("_cache_last_enriched_at"),
        "local_profile_id": place.get("_local_profile_id"),
        "profile_store": place.get("_profile_store") or "fallback_local_store",
        "seeded_by_launch_pack": bool(place.get("_seeded_by_launch_pack")),
        "enqueued_for_enrichment": bool(place.get("_enqueued_for_enrichment")),
        "enrichment_enqueue_reason": place.get("_enrichment_enqueue_reason"),
        "candidate_count": candidate_count,
        "chosen_candidate_name": chosen_candidate_name,
        "chosen_candidate_source": menu_source,
        "chosen_candidate_confidence": _safe_float(place.get("menu_item_confidence") or place.get("order_confidence"), 0.5),
        "chosen_candidate_specificity_tier": tier,
        "specificity_bonus_100": specificity_bonus,
        "meal_fitness_score_100": round(meal_fitness, 1),
        "display_rank_score_100": round(display_score, 1),
        "eligibility_band": eligibility_band,
        "section": section,
        "visible_in_results": visible_rank is not None,
        "visible_rank": visible_rank,
        "filter_reason": None,
        "suppressed_reason": None,
        "quality_tier": "high" if display_score >= 70 else ("medium" if display_score >= 55 else "low"),
        "fetched_but_hidden": fetched_but_hidden,
        "hidden_reason": hidden_reason,
        "debug_notes": [],
    }

    if trace["fetched_but_hidden"] and hidden_reason:
        trace["debug_notes"].append(f"Hidden: {hidden_reason}")
    if _is_generic_fallback(chosen_candidate_name):
        trace["debug_notes"].append("Generic fallback; demoted in ranking")
    if chain_match_key:
        trace["debug_notes"].append(f"Chain match: {chain_match_key}")

    # Forward chain/Supabase diagnostics from place when present (rollout trace)
    for key in ("matched_chain_key", "chain_match_status", "chain_menu_store", "menu_item_source", "profile_source", "specificity_tier", "last_ingested_at", "chain_menu_item_count_for_match"):
        if key in place and place[key] is not None:
            trace[key] = place[key]

    return trace

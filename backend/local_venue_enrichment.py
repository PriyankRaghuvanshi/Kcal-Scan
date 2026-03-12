"""
Local venue enrichment: match places to local profiles, build candidates, integrate with cache.
No LLM. No live scraping. Deterministic.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from launch_area_config import get_area_for_place, is_place_in_launch_area
from local_venue_profiles import (
    match_local_profile,
    profile_to_candidates,
    profile_to_swaps,
)

# Specificity bonuses for local profiles (tie-break only)
BONUS_EXACT_LOCAL = 5
BONUS_ENRICHED_LOCAL = 4
BONUS_HEURISTIC_LOCAL = 1
PENALTY_GENERIC_FALLBACK = -4


def get_local_profile_for_place(
    place: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], str]:
    """
    Get local venue profile for a place if in launch area.
    Tries Supabase-backed store first; falls back to local_venue_profiles JSON.
    Returns (profile, area_key, match_reason, profile_store).
    match_reason: "place_id" | "normalized_name" | "no_area" | "no_profile"
    profile_store: "supabase_canonical" | "fallback_local_store"
    """
    area = get_area_for_place(place)
    if not area:
        return (None, None, "no_area", "fallback_local_store")
    area_key = str(area.get("area_key") or "").strip()
    place_id = str(place.get("place_id") or place.get("id") or "").strip()
    place_name = str(place.get("name") or place.get("place_name") or "").strip()

    try:
        from supabase_intelligence_store import get_local_venue_profile as get_supabase_profile, _supabase_available
        profile = get_supabase_profile(
            place_id=place_id or None,
            normalized_name=place_name or None,
            area_key=area_key or None,
        )
        if profile:
            store = "supabase_canonical" if _supabase_available() else "fallback_local_store"
            matched_by_id = place_id and str(profile.get("place_id") or "").strip() == place_id
            return (profile, area_key, "place_id" if matched_by_id else "normalized_name", store)
    except Exception:
        pass

    profile = match_local_profile(place, area_key=area_key)
    if not profile:
        return (None, area_key, "no_profile", "fallback_local_store")

    matched_by_id = place_id and str(profile.get("place_id") or "").strip() == place_id
    return (profile, area_key, "place_id" if matched_by_id else "normalized_name", "fallback_local_store")


def enrich_place_with_local_profile(
    place: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    If place has a local profile, return menu payload (candidates, swaps, source).
    Otherwise return None. Caller uses this before heuristic fallback.
    """
    profile, area_key, match_reason, profile_store = get_local_profile_for_place(place)
    if not profile:
        return None

    candidates = profile_to_candidates(profile, max_items=6)
    if not candidates:
        return None

    top = candidates[0]
    template_key = top.get("template_key")
    swaps = profile_to_swaps(profile, template_key=template_key)

    specificity_tier = profile.get("specificity_tier") or "enriched_local_profile"
    profile_source = profile.get("profile_source") or "curated_manual"
    profile_id = str(profile.get("id") or profile.get("profile_id") or "").strip() or None
    seeded_by_launch_pack = bool(profile.get("seeded_by_launch_pack"))

    return {
        "local_profile_id": profile_id,
        "profile_id": profile_id,
        "profile_store": profile_store,
        "seeded_by_launch_pack": seeded_by_launch_pack,
        "menu_items_source": "enriched_local_profile",
        "menu_source": "enriched_local_profile",
        "menu_confidence": float(top.get("menu_item_confidence") or 0.78),
        "extraction_method": "local_venue_profile",
        "parse_method": "local_profile",
        "source_url": "",
        "top_menu_items": candidates[:3],
        "best_menu_items": candidates[:3],
        "top_menu_item": top,
        "top_item": str(top.get("item_name") or ""),
        "chain_key": None,
        "chain_match": False,
        "from_venue_cache": False,
        "from_local_profile": True,
        "local_profile_source": profile_source,
        "chosen_candidate_profile_source": str(top.get("profile_source") or "").strip() or profile_source,
        "local_profile_area_key": area_key,
        "local_profile_match_reason": match_reason,
        "local_profile_confidence": float(profile.get("confidence_tier", 0.8) if isinstance(profile.get("confidence_tier"), (int, float)) else 0.8),
        "chosen_candidate_specificity_tier": specificity_tier,
        "swap_templates": swaps,
        "candidates": candidates,
    }


def summarize_launch_area_coverage(area_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Coverage summary for launch area(s).
    Returns total_seeded_profiles, strong_profiles, partial_profiles, top cuisines, etc.
    """
    from local_venue_profiles import _profiles_list

    profiles = _profiles_list()
    if area_key:
        area_key_norm = str(area_key or "").strip().lower()
        profiles = [p for p in profiles if str(p.get("area_key") or "").strip().lower() == area_key_norm]

    strong = [p for p in profiles if str(p.get("coverage_status") or "").strip() == "strong"]
    partial = [p for p in profiles if str(p.get("coverage_status") or "").strip() == "partial"]
    seeded = [p for p in profiles if str(p.get("coverage_status") or "").strip() in ("strong", "partial", "seeded")]
    planned = [p for p in profiles if str(p.get("coverage_status") or "").strip() == "planned"]
    pack_seeded = [p for p in profiles if p.get("seeded_by_launch_pack")]
    auto_promoted = [
        p for p in profiles
        if any(
            str(t.get("profile_source") or "").strip() in ("auto_promoted", "community_confirmed")
            for t in (p.get("candidate_templates") or []) if isinstance(t, dict)
        )
    ]

    cuisine_counts: Dict[str, int] = {}
    for p in profiles:
        for c in p.get("cuisine_tags") or []:
            tag = str(c or "").strip().lower()
            if tag:
                cuisine_counts[tag] = cuisine_counts.get(tag, 0) + 1
    top_cuisines = sorted(cuisine_counts.items(), key=lambda x: -x[1])[:8]

    category_counts: Dict[str, int] = {}
    for p in profiles:
        for c in p.get("category_tags") or []:
            tag = str(c or "").strip().lower()
            if tag:
                category_counts[tag] = category_counts.get(tag, 0) + 1
    top_categories = sorted(category_counts.items(), key=lambda x: -x[1])[:8]

    return {
        "area_key": area_key,
        "total_seeded_profiles": len(seeded),
        "strong_profiles": len(strong),
        "partial_profiles": len(partial),
        "planned_profiles": len(planned),
        "pack_seeded_profiles": len(pack_seeded),
        "auto_promoted_profiles": len(auto_promoted),
        "top_cuisines_covered": [c[0] for c in top_cuisines],
        "top_categories_covered": [c[0] for c in top_categories],
        "cuisine_counts": dict(top_cuisines[:5]),
        "total_chain_covered_places": 0,
        "total_local_enriched_places": len(seeded) + len(partial),
    }


def list_high_priority_local_venues(
    area_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List local venues by enrichment priority.
    Uses profile coverage_status and area. Future: plug in meal_decision_event signals.
    """
    from local_venue_profiles import _profiles_list

    profiles = _profiles_list()
    if area_key:
        area_key_norm = str(area_key or "").strip().lower()
        profiles = [p for p in profiles if str(p.get("area_key") or "").strip().lower() == area_key_norm]

    priority_order = {"strong": 3, "partial": 2, "seeded": 1, "planned": 0}
    scored = []
    for p in profiles:
        cov = str(p.get("coverage_status") or "").strip().lower()
        prio = priority_order.get(cov, 0)
        scored.append((prio, p.get("place_name") or "", p))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [x[2] for x in scored]


def build_trace_enrichment_fields(
    place: Dict[str, Any],
    matched_profile: bool,
    profile_source: Optional[str] = None,
    profile_confidence: Optional[float] = None,
    specificity_tier: Optional[str] = None,
    not_used_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Build dict of local enrichment fields for trace/audit."""
    out = {
        "matched_local_profile": bool(matched_profile),
        "local_profile_source": profile_source,
        "local_profile_confidence": profile_confidence,
        "chosen_candidate_specificity_tier": specificity_tier,
        "local_enrichment_used": bool(matched_profile),
        "local_enrichment_not_used_reason": not_used_reason,
    }
    return out

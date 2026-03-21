"""
Local venue enrichment: match places to local profiles, build candidates, integrate with cache.
No LLM. No live scraping. Deterministic.
Diet-aware: when diet_preference is vegetarian/vegan, only diet-safe candidates are used for top item.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from chain_menu_registry import match_chain_key
from chain_rollout_registry import get_chain_runtime_config
from diet_filters import is_item_allowed_for_diet, normalize_diet_preference
from launch_area_config import get_area_for_place, is_place_in_launch_area
from local_venue_profiles import (
    match_local_profile,
    profile_to_candidates,
    profile_to_swaps,
)
from supabase_intelligence_store import get_chain_menu_items

# Specificity bonuses for local profiles (tie-break only)
BONUS_EXACT_LOCAL = 5
BONUS_ENRICHED_LOCAL = 4
BONUS_HEURISTIC_LOCAL = 1
PENALTY_GENERIC_FALLBACK = -4


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sort_chain_candidates_by_fitness(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort Supabase chain candidates for default Healthy Nearby ordering.
    Favors fitness-relevant items: fat_loss_fit_score, protein_density_score,
    estimated_protein_g, confidence (all descending). Deterministic.
    """
    if not candidates:
        return []
    def key(c: Dict[str, Any]) -> tuple:
        return (
            _safe_float(c.get("fat_loss_fit_score"), 0.0),
            _safe_float(c.get("protein_density_score"), 0.0),
            _safe_float(c.get("estimated_protein_g"), 0.0),
            _safe_float(c.get("confidence") or c.get("menu_confidence"), 0.0),
        )
    return sorted(candidates, key=key, reverse=True)


def _item_safe_for_diet(item: Dict[str, Any], diet: str) -> bool:
    """
    True if item is allowed for the given diet. Prefers explicit vegetarian_possible/vegan_possible
    when present (from chain seed/Supabase); otherwise falls back to diet_filters inference.
    Omnivore: all allowed.
    """
    if diet == "omnivore":
        return True
    # Explicit flags from seed/Supabase take precedence
    if diet == "vegetarian":
        veg = item.get("vegetarian_possible")
        if veg is True:
            return True
        if veg is False:
            return False
    if diet == "vegan":
        v = item.get("vegan_possible")
        if v is True:
            return True
        if v is False:
            return False
    return is_item_allowed_for_diet(item, diet)


def _filter_chain_candidates_for_diet(
    candidates: List[Dict[str, Any]],
    diet: str,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Filter chain candidates to diet-safe only. Returns (filtered_list, excluded_count).
    When diet is omnivore, returns all. Deterministic.
    """
    if not candidates or diet == "omnivore":
        return candidates, 0
    filtered = [c for c in candidates if _item_safe_for_diet(c, diet)]
    return filtered, len(candidates) - len(filtered)


def _infer_market_tag_from_place(place: Dict[str, Any]) -> str:
    """Infer market_tag (AU/US/IN) from place when not provided."""
    for key in ("country_code", "countryCode", "country", "region"):
        val = place.get(key)
        if not val:
            continue
        v = str(val).strip().upper()
        if v in ("US", "USA"):
            return "US"
        if v in ("IN", "IND", "INDIA"):
            return "IN"
        if v in ("AU", "AUS", "AUSTRALIA"):
            return "AU"
    text = " ".join(
        str(place.get(k) or "") for k in ("vicinity", "address", "formatted_address", "formattedAddress")
    ).lower()
    if "india" in text or " ind " in text:
        return "IN"
    if "united states" in text or " usa " in f" {text} " or " u.s." in text:
        return "US"
    if "australia" in text or " au " in text:
        return "AU"
    return "AU"


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
    *,
    market_tag: Optional[str] = None,
    diet_preference: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    If place matches a chain with Supabase menu items, return chain-backed payload.
    Else if place has a local profile, return menu payload (candidates, swaps, source).
    Otherwise return None. Caller uses this before heuristic fallback.

    When diet_preference is vegetarian or vegan, only diet-safe candidates are used for
    top_menu_item; if none exist, top_menu_item is None and no_diet_safe_candidates is True.
    """
    place_name = str(place.get("name") or place.get("place_name") or "").strip()
    brand_hint = place.get("brand_hint") or None
    chain_key = match_chain_key(place_name, brand_hint) if place_name else None
    diet = normalize_diet_preference(diet_preference or place.get("diet_preference"))

    if chain_key:
        market = market_tag or _infer_market_tag_from_place(place)
        chain_runtime = get_chain_runtime_config(chain_key, market)
        items = get_chain_menu_items(chain_key, market)
        if items:
            candidates = []
            for it in items:
                c = dict(it)
                c["menu_item_source"] = "ingested_chain_item"
                c["profile_source"] = "chain_menu_supabase"
                c["specificity_tier"] = "exact_menu_match"
                candidates.append(c)
            # Diet-aware: hard filter to diet-safe candidates before sort
            if diet != "omnivore":
                candidates, _excluded = _filter_chain_candidates_for_diet(candidates, diet)
            candidates = _sort_chain_candidates_by_fitness(candidates)
            top = candidates[0] if candidates else {}
            no_diet_safe = diet != "omnivore" and not candidates
            # When no diet-safe candidates, return payload with empty top but same shape
            return {
                "matched_chain_key": chain_key,
                "chain_match_status": "matched",
                "chain_menu_store": "supabase",
                "chain_menu_item_count_for_match": len(items),
                # Additive rollout-registry metadata (read-only plumbing).
                "chain_registry_configured": bool(chain_runtime.get("configured")),
                "chain_status": str(chain_runtime.get("status") or "unconfigured"),
                "chain_registry_version": int(chain_runtime.get("registry_version") or 0),
                "chain_active_config_version": str(chain_runtime.get("active_config_version") or ""),
                "chain_baseline_snapshot_id": str(chain_runtime.get("baseline_snapshot_id") or ""),
                "chain_fallback_mode": str(chain_runtime.get("fallback_mode") or "balanced"),
                "market": str(market or "").strip().upper(),
                "country_code": str(market or "").strip().upper(),
                "chain_rollout_enabled": bool(((chain_runtime.get("rollout") or {}).get("enabled"))),
                "chain_canary_percent": int(((chain_runtime.get("rollout") or {}).get("canary_percent")) or 0),
                "chain_features": dict(chain_runtime.get("features") or {}),
                "supabase_chain_candidates": candidates,
                "top_menu_items": candidates[:6],
                "best_menu_items": candidates[:6],
                "top_menu_item": top if not no_diet_safe else None,
                "top_item": str(top.get("item_name") or "") if not no_diet_safe else "",
                "chain_key": chain_key,
                "chain_match": True,
                "menu_items_source": "ingested_chain_item",
                "menu_source": "chain_menu_supabase",
                "menu_confidence": float(top.get("confidence") or top.get("menu_confidence") or 0.78) if top else 0.0,
                "from_venue_cache": False,
                "from_local_profile": False,
                "local_profile_id": None,
                "profile_id": None,
                "profile_store": None,
                "seeded_by_launch_pack": False,
                "extraction_method": "chain_menu_supabase",
                "parse_method": "chain_menu_supabase",
                "source_url": str(top.get("source_url") or "").strip() if top else "",
                "chosen_candidate_profile_source": "chain_menu_supabase",
                "chosen_candidate_specificity_tier": "exact_menu_match",
                "swap_templates": [],
                "candidates": candidates,
                "diet_filter_applied": diet != "omnivore",
                "no_diet_safe_candidates": no_diet_safe,
            }

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

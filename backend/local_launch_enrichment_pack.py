"""
Launch enrichment pack: structured local venue profiles for top launch suburbs.
Seeds local_venue_profiles with specific, plausible candidate templates and swaps.
Reduces generic fallback in Healthy Nearby and Smart Alerts.
No LLM. No live fetch. Deterministic structured data.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from launch_area_config import get_launch_area, list_launch_areas
from local_venue_profiles import (
    _profiles_list,
    get_profile_by_normalized_name,
    upsert_profile_from_pack,
)
from local_venue_enrichment import summarize_launch_area_coverage

# Priority order for launch areas (worst coverage / highest impact first)
PRIORITY_AREA_ORDER = (
    "wentworthville",
    "parramatta",
    "harris_park",
    "westmead",
    "merrylands",
    "granville",
    "homebush",
    "strathfield",
    "sydney_olympic_park",
)

# Structured venue definitions per area. Specific, plausible templates.
# Diet-aware: vegetarian_possible, vegan_possible on templates where appropriate.
LAUNCH_ENRICHMENT_PACK: Dict[str, List[Dict[str, Any]]] = {
    "wentworthville": [
        {
            "place_name": "Raj's Curry House",
            "name_variants": ["Raj's Curry House", "Raje Curry House", "Raj Curry"],
            "area_key": "wentworthville",
            "cuisine_tags": ["indian", "north_indian"],
            "category_tags": ["restaurant"],
            "notes": "North Indian. Tandoori, dal. Favor grilled.",
            "candidate_templates": [
                {"template_key": "tandoori_dal", "template_name": "Tandoori chicken half + dal tadka", "estimated_calories": 520, "estimated_protein_g": 40, "confidence": 0.82, "food_quality_tags": ["grilled", "high_protein"], "cut_friendly": True},
                {"template_key": "paneer_dal", "template_name": "Paneer tikka + dal", "estimated_calories": 500, "estimated_protein_g": 26, "confidence": 0.80, "food_quality_tags": ["vegetarian", "grilled"], "vegetarian_possible": True, "cut_friendly": True},
                {"template_key": "dal_roti", "template_name": "Dal + roti (2)", "estimated_calories": 380, "estimated_protein_g": 14, "confidence": 0.85, "food_quality_tags": ["vegetarian"], "vegetarian_possible": True, "vegan_possible": True, "cut_friendly": True},
            ],
            "swap_templates": [
                {"swap_key": "light_raita", "swap_label": "Light raita on the side", "swap_type": "sauce_modify", "calories_delta": -40, "protein_delta": 0, "reason": "Lower fat", "plausibility_score": 0.90},
                {"swap_key": "no_naan", "swap_label": "Skip naan, extra salad", "swap_type": "side_swap", "calories_delta": -180, "protein_delta": -2, "reason": "Lower carb", "plausibility_score": 0.85},
            ],
        },
        {
            "place_name": "Wenty Cafe",
            "name_variants": ["Wenty Cafe", "Wenty Cafè"],
            "area_key": "wentworthville",
            "cuisine_tags": ["cafe", "australian"],
            "category_tags": ["cafe"],
            "notes": "Local cafe. Eggs, wraps.",
            "candidate_templates": [
                {"template_key": "eggs_toast", "template_name": "Eggs on toast", "estimated_calories": 420, "estimated_protein_g": 24, "confidence": 0.82, "cut_friendly": True},
                {"template_key": "chicken_wrap", "template_name": "Grilled chicken wrap", "estimated_calories": 460, "estimated_protein_g": 30, "confidence": 0.80, "cut_friendly": True},
                {"template_key": "avocado_toast", "template_name": "Avocado toast + poached egg", "estimated_calories": 450, "estimated_protein_g": 12, "confidence": 0.78, "vegetarian_possible": True, "cut_friendly": False},
            ],
            "swap_templates": [
                {"swap_key": "no_hash", "swap_label": "Skip hash browns", "swap_type": "side_omit", "calories_delta": -140, "protein_delta": -1, "reason": "Lower calories", "plausibility_score": 0.88},
            ],
        },
    ],
    "parramatta": [
        {
            "place_name": "Spice Alley Parramatta",
            "name_variants": ["Spice Alley", "Spice Alley Parramatta"],
            "area_key": "parramatta",
            "cuisine_tags": ["indian", "asian"],
            "category_tags": ["restaurant"],
            "notes": "Indian street food. Favor grilled over creamy.",
            "candidate_templates": [
                {"template_key": "chicken_tikka", "template_name": "Chicken tikka + salad", "estimated_calories": 450, "estimated_protein_g": 38, "confidence": 0.82, "food_quality_tags": ["grilled"], "cut_friendly": True},
                {"template_key": "paneer_tikka", "template_name": "Paneer tikka + dal", "estimated_calories": 480, "estimated_protein_g": 24, "confidence": 0.80, "vegetarian_possible": True, "cut_friendly": True},
            ],
            "swap_templates": [],
        },
        {
            "place_name": "Juice Bar Parramatta",
            "name_variants": ["Juice Bar", "Fresh Juice Bar Parramatta"],
            "area_key": "parramatta",
            "cuisine_tags": ["juice", "smoothie", "healthy"],
            "category_tags": ["cafe", "juice_bar"],
            "notes": "Juice and smoothies. Lower-sugar options.",
            "candidate_templates": [
                {"template_key": "green_smoothie", "template_name": "Green smoothie (spinach, apple, ginger)", "estimated_calories": 160, "estimated_protein_g": 2, "confidence": 0.78, "vegetarian_possible": True, "vegan_possible": True, "cut_friendly": True},
                {"template_key": "protein_smoothie", "template_name": "Protein smoothie (banana, milk, protein)", "estimated_calories": 280, "estimated_protein_g": 25, "confidence": 0.75, "cut_friendly": True},
            ],
            "swap_templates": [],
        },
    ],
    "harris_park": [
        {
            "place_name": "Chaat House",
            "name_variants": ["Chaat House", "Chaat House Harris Park"],
            "area_key": "harris_park",
            "cuisine_tags": ["indian", "street_food"],
            "category_tags": ["restaurant"],
            "notes": "Indian chaat and snacks. Dahi puri, pav bhaji.",
            "candidate_templates": [
                {"template_key": "chicken_tikka", "template_name": "Chicken tikka + raita", "estimated_calories": 420, "estimated_protein_g": 36, "confidence": 0.82, "cut_friendly": True},
                {"template_key": "pav_bhaji", "template_name": "Pav bhaji (veg)", "estimated_calories": 450, "estimated_protein_g": 10, "confidence": 0.80, "vegetarian_possible": True, "cut_friendly": False},
            ],
            "swap_templates": [],
        },
    ],
    "westmead": [
        {
            "place_name": "Westmead Cafe",
            "name_variants": ["Westmead Cafe", "Westmead Café"],
            "area_key": "westmead",
            "cuisine_tags": ["cafe"],
            "category_tags": ["cafe"],
            "notes": "Hospital area cafe. Eggs, sandwiches.",
            "candidate_templates": [
                {"template_key": "eggs", "template_name": "Eggs on toast", "estimated_calories": 400, "estimated_protein_g": 22, "confidence": 0.80, "cut_friendly": True},
                {"template_key": "omelette", "template_name": "Omelette + toast", "estimated_calories": 440, "estimated_protein_g": 26, "confidence": 0.78, "cut_friendly": True},
                {"template_key": "chicken_salad", "template_name": "Grilled chicken salad", "estimated_calories": 380, "estimated_protein_g": 35, "confidence": 0.82, "cut_friendly": True},
            ],
            "swap_templates": [],
        },
    ],
    "merrylands": [
        {
            "place_name": "Merrylands Indian",
            "name_variants": ["Merrylands Indian", "Merrylands Indian Restaurant"],
            "area_key": "merrylands",
            "cuisine_tags": ["indian"],
            "category_tags": ["restaurant"],
            "notes": "North Indian. Tandoori, dal.",
            "candidate_templates": [
                {"template_key": "tandoori_dal", "template_name": "Tandoori chicken half + dal", "estimated_calories": 510, "estimated_protein_g": 42, "confidence": 0.80, "cut_friendly": True},
                {"template_key": "dal_roti", "template_name": "Dal + roti (vegan)", "estimated_calories": 360, "estimated_protein_g": 12, "confidence": 0.85, "vegetarian_possible": True, "vegan_possible": True, "cut_friendly": True},
            ],
            "swap_templates": [
                {"swap_key": "light_raita", "swap_label": "Light raita", "swap_type": "sauce_modify", "calories_delta": -35, "protein_delta": 0, "reason": "Lower fat", "plausibility_score": 0.88},
            ],
        },
    ],
}


def list_priority_launch_areas(limit: int = 5) -> List[str]:
    """Return area_keys for top-priority launch suburbs (by configured order)."""
    areas = list_launch_areas(enabled_only=True)
    area_keys = [str(a.get("area_key") or "").strip() for a in areas if a.get("area_key")]
    ordered = []
    for key in PRIORITY_AREA_ORDER:
        if key in area_keys and key not in ordered:
            ordered.append(key)
    for key in area_keys:
        if key not in ordered:
            ordered.append(key)
    return ordered[: max(1, min(20, limit))]


def list_priority_local_venues(area_key: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Return venue definitions from the pack for an area."""
    key = str(area_key or "").strip().lower().replace(" ", "_")
    pack_venues = LAUNCH_ENRICHMENT_PACK.get(key, [])
    return pack_venues[: max(1, min(50, limit))]


def seed_launch_area_enrichment(area_key: str, limit: int = 20) -> Dict[str, Any]:
    """
    Seed local venue profiles for an area from the enrichment pack.
    Returns {area_key, venues_seeded, profiles_created, profiles_extended, templates_added, swaps_added}.
    """
    venues = list_priority_local_venues(area_key, limit=limit)
    profiles_created = 0
    profiles_extended = 0
    templates_added = 0
    swaps_added = 0

    for v in venues:
        result = upsert_profile_from_pack(v, profile_source="launch_enrichment_pack")
        if result.get("created"):
            profiles_created += 1
        elif result.get("templates_added", 0) > 0 or result.get("swaps_added", 0) > 0:
            profiles_extended += 1
        templates_added += result.get("templates_added", 0)
        swaps_added += result.get("swaps_added", 0)

    result = {
        "area_key": area_key,
        "venues_seeded": len(venues),
        "profiles_created": profiles_created,
        "profiles_extended": profiles_extended,
        "templates_added": templates_added,
        "swaps_added": swaps_added,
        "coverage_after": summarize_launch_area_coverage(area_key),
    }
    try:
        from local_profile_supabase_sync import sync_launch_pack_profiles_to_supabase
        sync_res = sync_launch_pack_profiles_to_supabase(area_key=area_key, limit=50)
        result["supabase_sync"] = sync_res
    except Exception:
        result["supabase_sync"] = {"synced": 0, "skipped": 0, "failed": 0, "errors": ["sync skipped or failed"]}
    return result


def seed_all_priority_launch_areas(
    limit_areas: int = 5,
    limit_per_area: int = 20,
) -> Dict[str, Any]:
    """
    Seed enrichment pack across top-priority launch areas.
    Returns aggregated summary.
    """
    areas = list_priority_launch_areas(limit=limit_areas)
    area_results = []
    total_created = 0
    total_extended = 0
    total_templates = 0
    total_swaps = 0

    for area_key in areas:
        r = seed_launch_area_enrichment(area_key, limit=limit_per_area)
        area_results.append(r)
        total_created += r.get("profiles_created", 0)
        total_extended += r.get("profiles_extended", 0)
        total_templates += r.get("templates_added", 0)
        total_swaps += r.get("swaps_added", 0)

    all_coverage = summarize_launch_area_coverage(None)

    return {
        "areas_seeded": len(area_results),
        "total_profiles_created": total_created,
        "total_profiles_extended": total_extended,
        "total_templates_added": total_templates,
        "total_swaps_added": total_swaps,
        "area_results": area_results,
        "coverage_summary": all_coverage,
    }


def get_launch_enrichment_status(area_key: Optional[str] = None) -> Dict[str, Any]:
    """Status of launch enrichment: pack definitions vs profiles in store."""
    pack_areas = list(LAUNCH_ENRICHMENT_PACK.keys())
    areas = list_priority_launch_areas(limit=20)
    profiles = _profiles_list()
    seeded = sum(1 for p in profiles if p.get("seeded_by_launch_pack"))

    by_area: Dict[str, Dict[str, Any]] = {}
    for ak in areas:
        pack_count = len(LAUNCH_ENRICHMENT_PACK.get(ak, []))
        area_profiles = [p for p in profiles if str(p.get("area_key") or "").strip().lower() == ak]
        pack_seeded = sum(1 for p in area_profiles if p.get("seeded_by_launch_pack"))
        by_area[ak] = {
            "pack_venue_count": pack_count,
            "profiles_in_store": len(area_profiles),
            "pack_seeded_count": pack_seeded,
        }

    coverage = summarize_launch_area_coverage(area_key) if area_key else summarize_launch_area_coverage(None)

    return {
        "area_key": area_key,
        "pack_areas": pack_areas,
        "priority_areas": areas,
        "total_profiles_seeded_by_pack": seeded,
        "by_area": by_area,
        "coverage": coverage,
    }

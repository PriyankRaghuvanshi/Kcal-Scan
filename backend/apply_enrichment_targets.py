"""
Bulk apply next-enrichment targets into canonical trusted local venue profiles.
Maps target recommended_enrichment_action to profile/template/swap upserts.
Idempotent. No LLM. No live menu fetch. Deterministic structured updates only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from local_profile_supabase_sync import merge_trusted_profile_sources
from post_sync_remediation_report import (
    ACTION_ADD_PROFILE_NOW,
    ACTION_ADD_SWAPS,
    ACTION_ADD_VEG_VEGAN_VARIANTS,
    ACTION_EXPAND_EXISTING_PROFILE,
    ACTION_FIX_GENERIC_TEMPLATE,
    ACTION_REVIEW_CHAIN_GAP,
)
from supabase_intelligence_store import get_local_venue_profile, upsert_trusted_profile_to_supabase

PROFILE_SOURCE_BULK = "bulk_enrichment_target"
SKIP_REASON_CHAIN_GAP = "chain_gap"


def _safe_str(v: Any, default: str = "") -> str:
    s = str(v or "").strip() if v is not None else ""
    return s if s else default


def _normalize_name(s: str) -> str:
    import re
    return re.sub(r"[^\w\s]", "", re.sub(r"\s+", " ", str(s or "").strip().lower())).strip()


# Deterministic template definitions by cuisine (no LLM). Specific, plausible names only.
def _templates_for_cuisine(cuisine: str, *, veg_vegan_only: bool = False) -> List[Dict[str, Any]]:
    """Return 1–3 candidate templates for the cuisine. veg_vegan_only=True returns only veg/vegan-safe."""
    c = _safe_str(cuisine).lower()
    if c == "indian":
        if veg_vegan_only:
            return [
                {"template_key": "dal_roti", "template_name": "Dal + roti (2)", "estimated_calories": 380, "estimated_protein_g": 14, "confidence": 0.78, "food_quality_tags": ["vegetarian"], "vegetarian_possible": True, "vegan_possible": True, "cut_friendly": True},
                {"template_key": "paneer_dal", "template_name": "Paneer tikka + dal", "estimated_calories": 500, "estimated_protein_g": 26, "confidence": 0.76, "food_quality_tags": ["vegetarian", "grilled"], "vegetarian_possible": True, "cut_friendly": True},
            ]
        return [
            {"template_key": "tandoori_dal", "template_name": "Tandoori chicken half + dal tadka", "estimated_calories": 520, "estimated_protein_g": 40, "confidence": 0.80, "food_quality_tags": ["grilled", "high_protein"], "cut_friendly": True},
            {"template_key": "chicken_tikka", "template_name": "Chicken tikka + salad", "estimated_calories": 450, "estimated_protein_g": 38, "confidence": 0.78, "food_quality_tags": ["grilled"], "cut_friendly": True},
            {"template_key": "dal_roti", "template_name": "Dal + roti (2)", "estimated_calories": 380, "estimated_protein_g": 14, "confidence": 0.82, "food_quality_tags": ["vegetarian"], "vegetarian_possible": True, "vegan_possible": True, "cut_friendly": True},
        ]
    if c == "cafe":
        if veg_vegan_only:
            return [
                {"template_key": "avocado_toast", "template_name": "Avocado toast + poached egg", "estimated_calories": 450, "estimated_protein_g": 12, "confidence": 0.75, "vegetarian_possible": True, "cut_friendly": False},
            ]
        return [
            {"template_key": "eggs_toast", "template_name": "Eggs on toast", "estimated_calories": 420, "estimated_protein_g": 24, "confidence": 0.80, "cut_friendly": True},
            {"template_key": "chicken_wrap", "template_name": "Grilled chicken wrap", "estimated_calories": 460, "estimated_protein_g": 30, "confidence": 0.78, "cut_friendly": True},
            {"template_key": "omelette_toast", "template_name": "Omelette + toast", "estimated_calories": 440, "estimated_protein_g": 26, "confidence": 0.76, "cut_friendly": True},
        ]
    if c == "juice_smoothie":
        if veg_vegan_only:
            return [
                {"template_key": "green_smoothie", "template_name": "Green smoothie (spinach, apple, ginger)", "estimated_calories": 160, "estimated_protein_g": 2, "confidence": 0.78, "vegetarian_possible": True, "vegan_possible": True, "cut_friendly": True},
            ]
        return [
            {"template_key": "green_smoothie", "template_name": "Green smoothie (spinach, apple, ginger)", "estimated_calories": 160, "estimated_protein_g": 2, "confidence": 0.78, "vegetarian_possible": True, "vegan_possible": True, "cut_friendly": True},
            {"template_key": "protein_smoothie", "template_name": "Protein smoothie (banana, milk, protein)", "estimated_calories": 280, "estimated_protein_g": 25, "confidence": 0.75, "cut_friendly": True},
        ]
    if c in ("chinese", "thai", "pizza", "burger", "mexican"):
        # Generic but still specific names for other cuisines
        if c == "chinese":
            return [
                {"template_key": "stir_fry", "template_name": "Stir-fried chicken + vegetables", "estimated_calories": 420, "estimated_protein_g": 35, "confidence": 0.72, "cut_friendly": True},
                {"template_key": "steamed_rice", "template_name": "Steamed rice + steamed protein", "estimated_calories": 400, "estimated_protein_g": 28, "confidence": 0.70, "cut_friendly": True},
            ]
        if c == "thai":
            return [
                {"template_key": "grilled_chicken", "template_name": "Grilled chicken + salad", "estimated_calories": 380, "estimated_protein_g": 36, "confidence": 0.72, "cut_friendly": True},
            ]
    # Default: minimal cafe-style fallback (still specific)
    return [
        {"template_key": "eggs_toast", "template_name": "Eggs on toast", "estimated_calories": 420, "estimated_protein_g": 24, "confidence": 0.75, "cut_friendly": True},
    ]


def _swaps_for_cuisine(cuisine: str) -> List[Dict[str, Any]]:
    """Deterministic swap templates by cuisine."""
    c = _safe_str(cuisine).lower()
    if c == "indian":
        return [
            {"swap_key": "light_raita", "swap_label": "Light raita on the side", "swap_type": "sauce_modify", "calories_delta": -40, "protein_delta": 0, "reason": "Lower fat", "plausibility_score": 0.88},
            {"swap_key": "no_naan", "swap_label": "Skip naan, extra salad", "swap_type": "side_swap", "calories_delta": -180, "protein_delta": -2, "reason": "Lower carb", "plausibility_score": 0.82},
        ]
    if c == "cafe":
        return [
            {"swap_key": "no_hash", "swap_label": "Skip hash browns", "swap_type": "side_omit", "calories_delta": -140, "protein_delta": -1, "reason": "Lower calories", "plausibility_score": 0.85},
        ]
    return []


def _inject_profile_source(templates: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    out = []
    for t in templates:
        x = dict(t)
        x["profile_source"] = source
        out.append(x)
    return out


def build_profile_update_from_target(target: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build a profile update payload from an enrichment target.
    Returns dict with candidate_templates, swap_templates, profile_source, etc., or None for review_chain_gap.
    Does not call Supabase. Idempotent: only adds new template_key/swap_key; caller merges.
    """
    action = _safe_str(target.get("recommended_enrichment_action") or "").lower()
    if action == ACTION_REVIEW_CHAIN_GAP:
        return None

    area_key = _safe_str(target.get("area_key") or "")
    place_name = _safe_str(target.get("place_name") or target.get("name") or "")
    place_id = _safe_str(target.get("place_id") or "")
    cuisine = _safe_str(target.get("cuisine_guess") or "").lower() or "cafe"

    if not place_name and not place_id:
        return None

    candidate_templates: List[Dict[str, Any]] = []
    swap_templates: List[Dict[str, Any]] = []

    if action == ACTION_ADD_PROFILE_NOW:
        candidate_templates = _templates_for_cuisine(cuisine or "cafe")[:3]
        swap_templates = _swaps_for_cuisine(cuisine or "cafe")[:2]
    elif action == ACTION_EXPAND_EXISTING_PROFILE:
        candidate_templates = _templates_for_cuisine(cuisine or "cafe")[1:3]  # 1–2 additional
        swap_templates = _swaps_for_cuisine(cuisine or "cafe")[:2]
    elif action == ACTION_ADD_VEG_VEGAN_VARIANTS:
        candidate_templates = _templates_for_cuisine(cuisine or "cafe", veg_vegan_only=True)
        swap_templates = []
    elif action == ACTION_ADD_SWAPS:
        swap_templates = _swaps_for_cuisine(cuisine or "cafe")
    elif action == ACTION_FIX_GENERIC_TEMPLATE:
        candidate_templates = _templates_for_cuisine(cuisine or "cafe")[:3]
        swap_templates = _swaps_for_cuisine(cuisine or "cafe")[:2]

    candidate_templates = _inject_profile_source(candidate_templates, PROFILE_SOURCE_BULK)

    return {
        "place_id": place_id or None,
        "place_name": place_name,
        "normalized_name": _normalize_name(place_name),
        "name_variants": [place_name] if place_name else [],
        "area_key": area_key,
        "profile_source": PROFILE_SOURCE_BULK,
        "seeded_by_launch_pack": False,
        "candidate_templates": candidate_templates,
        "swap_templates": swap_templates,
        "coverage_status": "partial",
        "specificity_tier": "enriched_local_profile",
        "cuisine_tags": [cuisine] if cuisine and cuisine != "cafe" else ["cafe"],
        "category_tags": ["restaurant"] if cuisine not in ("cafe", "juice_smoothie") else ["cafe"],
        "last_enriched_at": datetime.now(timezone.utc).isoformat(),
    }


def apply_enrichment_target(target: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply one enrichment target to the canonical Supabase store.
    Gets existing profile, merges update (no duplicate template_key/swap_key), upserts.
    Returns result dict: applied, profile_created, templates_added, swaps_added, place_name, area_key, skipped_reason, etc.
    """
    action = _safe_str(target.get("recommended_enrichment_action") or "")
    if action == ACTION_REVIEW_CHAIN_GAP:
        return {
            "place_name": target.get("place_name") or target.get("name"),
            "area_key": target.get("area_key"),
            "recommended_enrichment_action": action,
            "applied": False,
            "profile_created": False,
            "templates_added": 0,
            "swaps_added": 0,
            "skipped_reason": SKIP_REASON_CHAIN_GAP,
        }

    update = build_profile_update_from_target(target)
    if not update:
        return {
            "place_name": target.get("place_name") or target.get("name"),
            "area_key": target.get("area_key"),
            "recommended_enrichment_action": action,
            "applied": False,
            "profile_created": False,
            "templates_added": 0,
            "swaps_added": 0,
            "skipped_reason": "no_update",
        }

    place_id = update.get("place_id") or target.get("place_id")
    place_name = _safe_str(update.get("place_name") or target.get("place_name") or target.get("name"))
    area_key = _safe_str(update.get("area_key") or target.get("area_key"))

    existing = get_local_venue_profile(
        place_id=place_id or None,
        normalized_name=_normalize_name(place_name) if place_name else None,
        area_key=area_key or None,
    )
    profile_created = existing is None

    merged = merge_trusted_profile_sources(existing, update)
    if not existing:
        merged["profile_source"] = PROFILE_SOURCE_BULK
    merged["place_name"] = place_name or merged.get("place_name", "")
    merged["place_id"] = place_id or merged.get("place_id", "")
    merged["area_key"] = area_key or merged.get("area_key", "")

    templates_before = len(existing.get("candidate_templates") or []) if existing else 0
    swaps_before = len(existing.get("swap_templates") or []) if existing else 0
    templates_after = len(merged.get("candidate_templates") or [])
    swaps_after = len(merged.get("swap_templates") or [])

    result = upsert_trusted_profile_to_supabase(
        merged,
        templates=merged.get("candidate_templates"),
        swaps=merged.get("swap_templates"),
    )

    templates_added = max(0, templates_after - templates_before)
    swaps_added = max(0, swaps_after - swaps_before)
    applied = result is not None

    return {
        "place_name": place_name,
        "area_key": area_key,
        "recommended_enrichment_action": action,
        "applied": applied,
        "profile_created": profile_created and applied,
        "templates_added": templates_added,
        "swaps_added": swaps_added,
        "skipped_reason": None if applied else "upsert_failed",
    }


def apply_enrichment_targets(
    targets: List[Dict[str, Any]],
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Bulk apply enrichment targets. Idempotent; duplicate template_key/swap_key are not re-added.
    Returns summary: targets_considered, targets_applied, targets_skipped, applied_by_action, skipped_by_reason, sample_results.
    """
    if limit is not None:
        targets = targets[: max(1, limit)]
    considered = len(targets)
    applied_count = 0
    skipped_count = 0
    applied_by_action: Dict[str, int] = {}
    skipped_by_reason: Dict[str, int] = {}
    sample_results: List[Dict[str, Any]] = []

    for t in targets:
        action = _safe_str(t.get("recommended_enrichment_action") or "")
        if action == ACTION_REVIEW_CHAIN_GAP:
            skipped_count += 1
            skipped_by_reason[SKIP_REASON_CHAIN_GAP] = skipped_by_reason.get(SKIP_REASON_CHAIN_GAP, 0) + 1
            sample_results.append({
                "place_name": t.get("place_name") or t.get("name"),
                "area_key": t.get("area_key"),
                "recommended_enrichment_action": action,
                "applied": False,
                "profile_created": False,
                "templates_added": 0,
                "swaps_added": 0,
                "skipped_reason": SKIP_REASON_CHAIN_GAP,
            })
            continue

        res = apply_enrichment_target(t)
        if res.get("applied"):
            applied_count += 1
            applied_by_action[action] = applied_by_action.get(action, 0) + 1
        else:
            skipped_count += 1
            reason = res.get("skipped_reason") or "unknown"
            skipped_by_reason[reason] = skipped_by_reason.get(reason, 0) + 1

        if len(sample_results) < 30:
            sample_results.append(res)

    return {
        "targets_considered": considered,
        "targets_applied": applied_count,
        "targets_skipped": skipped_count,
        "applied_by_action": applied_by_action,
        "skipped_by_reason": skipped_by_reason,
        "sample_results": sample_results[:20],
    }


async def apply_next_enrichment_targets(
    limit: int = 20,
    area_keys: Optional[List[str]] = None,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
    targets: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Get next-enrichment targets (from fetch or explicit list) and bulk apply them.
    If targets is provided, use it. Otherwise call build_next_enrichment_targets_from_fetch (requires fetch_fn).
    """
    if targets is None:
        if fetch_fn is None:
            return {
                "targets_considered": 0,
                "targets_applied": 0,
                "targets_skipped": 0,
                "applied_by_action": {},
                "skipped_by_reason": {},
                "sample_results": [],
                "error": "targets or fetch_fn required",
            }
        from post_sync_remediation_report import build_next_enrichment_targets_from_fetch

        out = await build_next_enrichment_targets_from_fetch(
            fetch_fn=fetch_fn,
            limit_total=limit,
            limit_areas=5,
            area_keys=area_keys,
        )
        targets = out.get("targets") or []

    return apply_enrichment_targets(targets, limit=limit)

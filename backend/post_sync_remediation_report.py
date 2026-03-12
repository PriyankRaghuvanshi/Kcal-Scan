"""
Post-sync remediation report: measures launch-area quality after canonical Supabase sync.
Produces prioritized next-enrichment targets for action planning.
No LLM. No ranking changes. Measurement + prioritization only.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from launch_area_config import sample_points_for_area
from launch_readiness_report import build_launch_readiness_report
from local_launch_enrichment_pack import PRIORITY_AREA_ORDER, list_priority_launch_areas
from local_profile_supabase_sync import get_sync_status

# Action buckets for recommended enrichment
ACTION_ADD_PROFILE_NOW = "add_profile_now"
ACTION_EXPAND_EXISTING_PROFILE = "expand_existing_profile"
ACTION_ADD_VEG_VEGAN_VARIANTS = "add_veg_vegan_variants"
ACTION_ADD_SWAPS = "add_swaps"
ACTION_FIX_GENERIC_TEMPLATE = "fix_generic_template"
ACTION_REVIEW_CHAIN_GAP = "review_chain_gap"

# Priority suburbs (top 5 for default runs)
DEFAULT_PRIORITY_AREAS = list(PRIORITY_AREA_ORDER)[:5]


def _safe_str(v: Any, default: str = "") -> str:
    s = str(v or "").strip() if v is not None else ""
    return s if s else default


def _normalize_name(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[^\w\s]", "", re.sub(r"\s+", " ", str(s).strip().lower())).strip()


def _dedupe_key(place_name: str, area_key: str, place_id: str = "") -> str:
    pid = _safe_str(place_id)
    name = _normalize_name(place_name or "")
    area = _safe_str(area_key or "").lower()
    if pid:
        return f"id:{pid}"
    return f"name:{name}|area:{area}" if name and area else ""


async def run_post_sync_launch_report(
    area_key: str,
    *,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
    include_examples: bool = True,
) -> Dict[str, Any]:
    """
    Run launch readiness report with remediation extended and augment with canonical sync metrics.
    Returns report dict with canonical_profile_count, pack_seeded_profiles, auto_promoted_profiles.
    """
    points = sample_points_for_area(area_key, count=5)
    report = await build_launch_readiness_report(
        area_key,
        fetch_fn=fetch_fn,
        sample_points=points,
        include_examples=include_examples,
        remediation_extended=True,
    )
    sync = get_sync_status(area_key=area_key)
    report["canonical_sync"] = {
        "canonical_profile_count": sync.get("canonical_profile_count", 0),
        "pack_seeded_profiles": sync.get("local_pack_seeded_count", 0),
        "auto_promoted_profiles": sync.get("local_auto_promoted_count", 0),
        "pack_venue_definitions": sync.get("pack_venue_definitions", 0),
        "supabase_available": sync.get("supabase_available", False),
    }
    # Ensure local_enrichment has canonical context
    le = report.get("local_enrichment") or {}
    le["canonical_trusted_local_profiles_count"] = sync.get("canonical_profile_count", 0)
    report["local_enrichment"] = le
    # Derived rate for post-sync metrics
    known_fetched = report.get("known_chain_fetched_count") or 0
    known_hidden = report.get("known_chain_hidden_count") or 0
    report["known_chain_hidden_rate"] = (
        known_hidden / known_fetched if known_fetched else 0.0
    )
    # Single remediation_examples block for consumers
    report["remediation_examples"] = {
        "top_remaining_generic_fallback_venues": report.get("generic_problem_examples") or [],
        "top_weak_local_venues": report.get("concrete_examples") or [],  # weak = could expand
        "top_missing_chain_opportunities": report.get("top_missing_chain_examples") or report.get("missing_chain_examples") or [],
        "top_duplicate_score_cluster_examples": report.get("duplicate_score_examples") or [],
    }
    return report


async def run_post_sync_reports_for_priority_areas(
    *,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
    limit_areas: int = 5,
    include_examples: bool = True,
) -> Dict[str, Any]:
    """
    Run post-sync reports for top priority launch areas.
    Returns summaries keyed by area_key plus aggregate metrics.
    """
    areas = list_priority_launch_areas(limit=limit_areas)
    reports: List[Dict[str, Any]] = []
    for area_key in areas:
        r = await run_post_sync_launch_report(
            area_key,
            fetch_fn=fetch_fn,
            include_examples=include_examples,
        )
        reports.append(r)

    return {
        "areas": reports,
        "total_areas": len(reports),
        "priority_order": areas,
    }


def _infer_cuisine_from_venue_or_item(place: Dict[str, Any]) -> Optional[str]:
    """Infer cuisine from place name or best_item_name. Accepts place dict or example dict."""
    name = _safe_str(place.get("name") or place.get("place_name") or "").lower()
    item = _safe_str(place.get("best_item_name") or place.get("best_order") or "").lower()
    combined = f"{name} {item}"
    keywords = {
        "indian": ("indian", "tandoori", "dal", "roti", "curry", "naan"),
        "cafe": ("cafe", "coffee", "espresso", "brunch", "eggs on toast"),
        "chinese": ("chinese", "noodle", "fried rice", "dim sum"),
        "thai": ("thai", "pad thai", "green curry"),
        "juice_smoothie": ("juice", "smoothie", "protein shake"),
        "pizza": ("pizza", "italian"),
        "burger": ("burger", "grill"),
        "mexican": ("mexican", "burrito", "tacos"),
    }
    for cuisine, kws in keywords.items():
        if any(kw in combined for kw in kws):
            return cuisine
    return None


def _area_priority_rank(area_key: str) -> int:
    """Lower index = higher priority. 0 = first in list."""
    key = _safe_str(area_key).lower()
    for i, a in enumerate(PRIORITY_AREA_ORDER):
        if key == a:
            return i
    return 999


def _assign_recommended_action(
    target: Dict[str, Any],
    source_type: str,
) -> str:
    """
    Assign recommended enrichment action based on target context.
    source_type: "generic_fallback" | "missing_chain" | "weak_local"
    """
    tier = _safe_str(target.get("chosen_candidate_specificity_tier") or "").lower()
    cuisine = _safe_str(target.get("cuisine_guess") or "")
    seeded = target.get("seeded_by_launch_pack") is True

    if source_type == "missing_chain":
        return ACTION_REVIEW_CHAIN_GAP

    if source_type == "weak_local":
        if "veg" in cuisine or "vegan" in cuisine:
            return ACTION_ADD_VEG_VEGAN_VARIANTS
        if target.get("has_swaps") is False:
            return ACTION_ADD_SWAPS
        return ACTION_EXPAND_EXISTING_PROFILE

    # generic_fallback
    if seeded:
        return ACTION_FIX_GENERIC_TEMPLATE
    if "indian" in cuisine or "cafe" in cuisine or "juice" in cuisine:
        return ACTION_ADD_PROFILE_NOW
    return ACTION_ADD_PROFILE_NOW


def score_enrichment_target(target: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute priority_score for a target. Higher = more urgent.
    Favor: high visibility, generic fallback, high-priority suburb, weak cuisine cluster.
    Penalize: strong coverage (enriched_local_profile, strong profiles).
    """
    area_key = _safe_str(target.get("area_key") or "")
    place_name = _safe_str(target.get("place_name") or target.get("name") or "")
    source_type = _safe_str(target.get("source_type") or "generic_fallback")
    tier = _safe_str(target.get("chosen_candidate_specificity_tier") or "").lower()
    visibility_count = int(target.get("visibility_count") or 1)
    area_rank = _area_priority_rank(area_key)
    pct_generic_in_area = float(target.get("percent_top_5_generic_in_area") or 0)
    cuisine_weakness = 1.0 if target.get("cuisine_in_weak_cluster") else 0.0

    score = 0.0

    # Visibility: more appearances in top-5 = higher impact
    score += min(visibility_count * 5, 25)

    # Area priority: top suburbs first
    if area_rank < 5:
        score += (5 - area_rank) * 3
    elif area_rank < 10:
        score += 2

    # Generic fallback = highest urgency
    if source_type == "generic_fallback" and tier == "generic_fallback":
        score += 30
    elif source_type == "missing_chain":
        score += 20
    elif source_type == "weak_local":
        score += 15

    # Suburb has high generic % = more urgent
    if pct_generic_in_area > 50:
        score += 10
    elif pct_generic_in_area > 30:
        score += 5

    # Cuisine in weak cluster
    score += cuisine_weakness * 8

    # Penalize already-strong coverage
    if tier in ("exact_local_profile", "chain_registry", "exact_menu_match"):
        score -= 40
    elif tier == "enriched_local_profile":
        score -= 15

    out = dict(target)
    out["priority_score"] = max(0.0, round(score, 1))
    return out


def build_next_enrichment_targets(
    *,
    reports: Optional[List[Dict[str, Any]]] = None,
    limit_total: int = 20,
    area_keys: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Build prioritized list of next enrichment targets from post-sync reports.
    If reports is None, returns empty list (caller must run reports first).
    """
    if not reports:
        return []

    # Collect targets from each report
    raw_targets: Dict[str, Dict[str, Any]] = {}
    area_metrics: Dict[str, Dict[str, Any]] = {}

    for r in reports:
        area_key = _safe_str(r.get("area_key") or "")
        if area_keys and area_key not in [str(a).lower() for a in area_keys]:
            continue

        pct_gen = float(r.get("percent_top_5_generic_fallback") or 0)
        le = r.get("local_enrichment") or {}
        area_metrics[area_key] = {
            "percent_top_5_generic_fallback": pct_gen,
            "visible_results_using_local_profiles_percent": le.get("visible_results_using_local_profiles_percent", 0),
        }

        # Generic fallback venues
        for ex in r.get("generic_problem_examples") or []:
            name = ex.get("name") or ex.get("place_name") or ""
            place_id = _safe_str(ex.get("place_id") or "")
            key = _dedupe_key(name, area_key, place_id)
            if not key:
                continue
            if key in raw_targets:
                raw_targets[key]["visibility_count"] = raw_targets[key].get("visibility_count", 1) + 1
                continue
            raw_targets[key] = {
                "area_key": area_key,
                "place_id": place_id if place_id else None,
                "place_name": name,
                "source_type": "generic_fallback",
                "chosen_candidate_specificity_tier": ex.get("tier") or "generic_fallback",
                "visibility_count": 1,
                "percent_top_5_generic_in_area": pct_gen,
                "cuisine_guess": _infer_cuisine_from_venue_or_item(ex),
                "cuisine_in_weak_cluster": _is_cuisine_weak(r, ex),
                "current_source": "generic_fallback",
                "profile_store": ex.get("profile_store"),
                "local_profile_source": ex.get("local_profile_source"),
                "chosen_candidate_profile_source": ex.get("chosen_candidate_profile_source"),
                "seeded_by_launch_pack": ex.get("seeded_by_launch_pack"),
            }

        # Missing chain opportunities
        for ex in r.get("top_missing_chain_examples") or r.get("missing_chain_examples") or []:
            name = ex.get("place_name") or ex.get("name") or ""
            key = _dedupe_key(name, area_key, ex.get("place_id") or "")
            if not key:
                continue
            if key in raw_targets:
                continue
            raw_targets[key] = {
                "area_key": area_key,
                "place_id": ex.get("place_id") or None,
                "place_name": name,
                "source_type": "missing_chain",
                "chosen_candidate_specificity_tier": ex.get("chosen_candidate_specificity_tier"),
                "visibility_count": 1,
                "percent_top_5_generic_in_area": pct_gen,
                "hidden_reason": ex.get("hidden_reason"),
                "cuisine_guess": "chain",
                "current_source": "chain_fetched_not_visible",
                "recommended_enrichment_action": ACTION_REVIEW_CHAIN_GAP,
                "profile_store": None,
                "local_profile_source": None,
                "chosen_candidate_profile_source": None,
                "seeded_by_launch_pack": False,
            }

    # Add area metrics to each target
    for t in raw_targets.values():
        am = area_metrics.get(t.get("area_key") or "", {})
        t["percent_top_5_generic_in_area"] = am.get("percent_top_5_generic_fallback", 0)

    # Score and assign actions
    scored = []
    for t in raw_targets.values():
        t["recommended_enrichment_action"] = _assign_recommended_action(
            t, _safe_str(t.get("source_type") or "generic_fallback")
        )
        st = score_enrichment_target(t)
        st["reason_summary"] = _build_reason_summary(st)
        scored.append(st)

    scored.sort(key=lambda x: -float(x.get("priority_score") or 0))
    return scored[: max(1, limit_total)]


def _is_cuisine_weak(report: Dict[str, Any], example: Dict[str, Any]) -> bool:
    """True if this example's cuisine appears in top_cuisines_needing_enrichment."""
    cuisines = report.get("top_cuisines_needing_enrichment") or []
    cuisine_set = {str(c.get("cuisine") or "").lower() for c in cuisines if c.get("cuisine")}
    ex_cuisine = _infer_cuisine_from_venue_or_item(example)
    return ex_cuisine and ex_cuisine.lower() in cuisine_set


def _build_reason_summary(target: Dict[str, Any]) -> str:
    """Build human-readable reason for enrichment priority."""
    parts = []
    area = target.get("area_key") or ""
    if area:
        parts.append(area)
    st = target.get("source_type") or ""
    if st == "generic_fallback":
        parts.append("generic fallback")
    elif st == "missing_chain":
        parts.append("chain not visible")
    elif st == "weak_local":
        parts.append("weak local profile")
    vis = target.get("visibility_count")
    if vis and vis > 1:
        parts.append(f"seen {vis}x")
    cuisine = target.get("cuisine_guess")
    if cuisine:
        parts.append(cuisine)
    return " | ".join(parts) if parts else "enrichment target"


async def build_next_enrichment_targets_from_fetch(
    *,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
    limit_total: int = 20,
    limit_areas: int = 5,
    area_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Run post-sync reports for priority areas and build next-enrichment targets.
    One-shot for endpoint use.
    """
    if area_keys:
        areas = [str(a).strip().lower() for a in area_keys]
    else:
        areas = list_priority_launch_areas(limit=limit_areas)

    reports: List[Dict[str, Any]] = []
    for area_key in areas:
        r = await run_post_sync_launch_report(
            area_key,
            fetch_fn=fetch_fn,
            include_examples=True,
        )
        reports.append(r)

    targets = build_next_enrichment_targets(
        reports=reports,
        limit_total=limit_total,
        area_keys=area_keys,
    )

    # Bucket by action type
    by_action: Dict[str, List[Dict[str, Any]]] = {}
    for t in targets:
        action = t.get("recommended_enrichment_action") or ACTION_ADD_PROFILE_NOW
        by_action.setdefault(action, []).append(t)

    return {
        "targets": targets,
        "by_action": by_action,
        "areas_analyzed": len(reports),
        "total_targets": len(targets),
    }

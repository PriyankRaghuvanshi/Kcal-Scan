"""
Launch readiness report: measures whether Healthy Nearby produces concrete value
beyond Google Places. Per-suburb metrics for speed, specificity, concrete-value,
genericity, missing chains, and local enrichment coverage.
No LLM. Deterministic.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Union

from launch_area_config import get_launch_area, list_launch_areas, sample_points_for_area
from local_venue_enrichment import summarize_launch_area_coverage

# Specificity score (0-5) for metrics
SPECIFICITY_SCORE: Dict[str, int] = {
    "exact_menu_match": 5,
    "exact_local_profile": 5,
    "chain_registry": 4,
    "enriched_local_profile": 4,
    "menu_inferred": 3,
    "heuristic_cuisine_match_strong": 2,
    "heuristic_cuisine_match_weak": 1,
    "generic_fallback": 0,
}

# Generic fallback item name tokens
_GENERIC_ITEM_TOKENS = (
    "lighter menu option", "lighter option", "healthy option", "balanced meal",
    "egg + chicken plate", "egg and chicken plate", "tandoori + dal", "dal + roti",
    "tandoori + dal + roti", "grilled protein bowl", "protein bowl", "protein plate",
    "lean wrap", "protein wrap", "needs menu check", "recommended item", "best menu item",
    "smart choice",
)

# Known trust-builder chains for missing-winner diagnostics
KNOWN_CHAIN_TOKENS = (
    "subway", "mcdonald", "maccas", "kfc", "hungry jack", "domino", "pizza hut",
    "grill'd", "grilld", "boost juice", "guzman", "gyg", "oporto", "red rooster",
    "zambrero", "nando",
)

# Thresholds for grading
THRESHOLD_P90_MS = 5000
THRESHOLD_TOP5_GENERIC_PERCENT = 60
THRESHOLD_TOP3_CONCRETE_PERCENT = 50
THRESHOLD_LOCAL_PROFILE_USAGE_PERCENT = 10
THRESHOLD_CHAIN_HIDDEN_RATE = 0.5


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_str(v: Any, default: str = "") -> str:
    s = str(v or "").strip()
    return s if s else default


def _specificity_score(tier: str) -> int:
    return SPECIFICITY_SCORE.get(str(tier or "").strip().lower(), 0)


def _is_generic_item(item_name: str) -> bool:
    lower = str(item_name or "").strip().lower()
    return any(t in lower for t in _GENERIC_ITEM_TOKENS)


def _is_concrete_order(place: Dict[str, Any]) -> bool:
    name = _safe_str(place.get("best_item_name") or place.get("best_order") or "")
    if not name:
        return False
    return not _is_generic_item(name)


def _has_specific_swap(place: Dict[str, Any]) -> bool:
    swaps = place.get("best_item_swaps") or []
    if not isinstance(swaps, list) or not swaps:
        return False
    for s in swaps[:3]:
        if isinstance(s, dict):
            label = _safe_str(s.get("swap_label") or "")
            if label and len(label) > 4:
                return True
    return False


def _has_high_confidence(place: Dict[str, Any]) -> bool:
    conf = _safe_str(place.get("confidence_label") or "").lower()
    return conf in ("verified", "estimated")


def _has_clear_difference_reason(place: Dict[str, Any]) -> bool:
    reason = _safe_str(place.get("rank_reason_short") or place.get("why_this_ranked_here") or "")
    if not reason or len(reason) < 10:
        return False
    generic = ("needs menu check", "check menu", "good fallback", "lighter option")
    return not any(g in reason.lower() for g in generic)


def _is_known_chain(place: Dict[str, Any]) -> bool:
    name = _safe_str(place.get("name") or place.get("place_name") or "").lower()
    return any(t in name for t in KNOWN_CHAIN_TOKENS)


def _extract_places(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract full ranked places list from healthy_places response."""
    items = response.get("items") or response.get("places") or []
    return items if isinstance(items, list) else []


def _extract_timings(response: Dict[str, Any]) -> Dict[str, float]:
    debug = response.get("_debug") or {}
    timings = debug.get("timings_ms") or {}
    return {
        "total_ms": _safe_float(timings.get("total_ms"), 0),
        "nearby_fetch_ms": _safe_float(timings.get("nearby_fetch_ms"), 0),
        "shortlist_ms": _safe_float(timings.get("shortlist_ms"), 0),
        "ranking_ms": _safe_float(timings.get("ranking_ms"), 0),
    }


def _extract_counts(response: Dict[str, Any]) -> Dict[str, int]:
    debug = response.get("_debug") or {}
    return {
        "fetched": int(debug.get("fetched_count") or response.get("places_count") or 0),
        "shortlisted": int(debug.get("shortlisted_count") or 0),
        "deep_ranked": int(debug.get("deeply_ranked_count") or response.get("places_count") or 0),
    }


async def build_launch_readiness_report(
    area_key: str,
    *,
    sample_points: Optional[List[Dict[str, Any]]] = None,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
    include_examples: bool = True,
    remediation_extended: bool = False,
) -> Dict[str, Any]:
    """
    Build launch readiness report for a suburb.
    fetch_fn(lat, lng) must return healthy_places-style response (places/items, _debug).
    If fetch_fn is None, returns report with zeros (for testing structure).
    """
    area = get_launch_area(area_key)
    display_name = _safe_str(area.get("display_name") or area_key) if area else area_key
    points = sample_points or sample_points_for_area(area_key)

    if not fetch_fn or not points:
        coverage = summarize_launch_area_coverage(area_key)
        return _empty_report(area_key, display_name, coverage, include_examples, remediation_extended)

    all_places: List[Dict[str, Any]] = []
    all_timings: List[Dict[str, float]] = []
    all_counts: List[Dict[str, int]] = []

    for pt in points:
        lat = _safe_float(pt.get("lat"), 0)
        lng = _safe_float(pt.get("lng"), 0)
        if not math.isfinite(lat) or not math.isfinite(lng):
            continue
        try:
            resp = await fetch_fn(lat, lng)
            if isinstance(resp, dict):
                places = _extract_places(resp)
                all_places.append(places)
                all_timings.append(_extract_timings(resp))
                all_counts.append(_extract_counts(resp))
        except Exception:
            continue

    return _aggregate_report(
        area_key=area_key,
        display_name=display_name,
        sample_count=len(all_counts),
        all_places=all_places,
        all_timings=all_timings,
        all_counts=all_counts,
        include_examples=include_examples,
        remediation_extended=remediation_extended,
    )


def _empty_report(
    area_key: str,
    display_name: str,
    coverage: Dict[str, Any],
    include_examples: bool,
    remediation_extended: bool = False,
) -> Dict[str, Any]:
    return {
        "area_key": area_key,
        "display_name": display_name,
        "sample_count": 0,
        "readiness_status": "no_data",
        "avg_total_response_ms": 0,
        "p50_total_response_ms": 0,
        "p90_total_response_ms": 0,
        "avg_fetched_places": 0,
        "avg_shortlisted_places": 0,
        "avg_deep_ranked_places": 0,
        "percent_top_1_exact_or_chain_backed": 0,
        "percent_top_3_exact_chain_or_enriched_local": 0,
        "percent_top_5_generic_fallback": 100,
        "avg_specificity_score_top_3": 0,
        "avg_specificity_score_top_5": 0,
        "percent_top_3_with_concrete_order": 0,
        "percent_top_3_with_specific_swap": 0,
        "percent_top_3_with_high_confidence": 0,
        "percent_top_3_with_non_generic_item_name": 0,
        "percent_top_3_with_clear_difference_reason": 0,
        "duplicate_score_cluster_rate_top_5": 0,
        "duplicate_candidate_name_rate_top_5": 0,
        "percent_top_5_same_cuisine_generic_guess": 0,
        "generic_indian_cluster_count": 0,
        "generic_cafe_cluster_count": 0,
        "generic_juice_cluster_count": 0,
        "known_chain_fetched_count": 0,
        "known_chain_visible_top_5_count": 0,
        "known_chain_hidden_count": 0,
        "top_missing_chain_examples": [],
        "top_cuisines_needing_enrichment": [] if remediation_extended else None,
        "duplicate_score_clusters": [] if remediation_extended else None,
        "local_enrichment": coverage,
        "concrete_examples": [] if include_examples else None,
        "generic_problem_examples": [] if include_examples else None,
        "missing_chain_examples": [] if include_examples else None,
        "duplicate_score_examples": [] if include_examples else None,
    }


_CUISINE_KEYWORDS: Dict[str, tuple] = {
    "indian": ("indian", "tandoori", "dal", "roti", "curry", "naan"),
    "cafe": ("cafe", "coffee", "espresso", "brunch"),
    "chinese": ("chinese", "noodle", "fried rice", "dim sum"),
    "thai": ("thai", "pad thai", "green curry"),
    "juice_smoothie": ("juice", "smoothie", "protein shake"),
    "pizza": ("pizza", "italian"),
    "burger": ("burger", "grill"),
    "mexican": ("mexican", "burrito", "tacos"),
}


def _infer_cuisine_from_venue(place: Dict[str, Any]) -> Optional[str]:
    name = str(place.get("name") or place.get("place_name") or "").lower()
    item = str(place.get("best_item_name") or place.get("best_order") or "").lower()
    combined = f"{name} {item}"
    for cuisine, keywords in _CUISINE_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return cuisine
    return None


def _aggregate_report(
    area_key: str,
    display_name: str,
    sample_count: int,
    all_places: List[List[Dict[str, Any]]],
    all_timings: List[Dict[str, float]],
    all_counts: List[Dict[str, int]],
    include_examples: bool,
    remediation_extended: bool = False,
) -> Dict[str, Any]:
    top1_list: List[Dict[str, Any]] = []
    top3_list: List[Dict[str, Any]] = []
    top5_list: List[Dict[str, Any]] = []
    all_places_flat: List[Dict[str, Any]] = []
    for chunk in all_places:
        if chunk:
            top1_list.append(chunk[0])
        top3_list.extend(chunk[:3])
        top5_list.extend(chunk[:5])
        all_places_flat.extend(chunk)

    total_ms_list = [t.get("total_ms") or 0 for t in all_timings if t.get("total_ms")]
    total_ms_list.sort()
    p50 = total_ms_list[len(total_ms_list) // 2] if total_ms_list else 0
    p90 = total_ms_list[int(len(total_ms_list) * 0.9)] if total_ms_list else 0
    avg_ms = sum(total_ms_list) / len(total_ms_list) if total_ms_list else 0

    avg_fetched = sum(c.get("fetched") or 0 for c in all_counts) / len(all_counts) if all_counts else 0
    avg_shortlisted = sum(c.get("shortlisted") or 0 for c in all_counts) / len(all_counts) if all_counts else 0
    avg_deep = sum(c.get("deep_ranked") or 0 for c in all_counts) / len(all_counts) if all_counts else 0

    def _top1_exact_or_chain(p: Dict[str, Any]) -> bool:
        tier = _safe_str(p.get("chosen_candidate_specificity_tier") or "").lower()
        return tier in ("exact_menu_match", "exact_local_profile", "chain_registry")

    def _top3_good(p: Dict[str, Any]) -> bool:
        tier = _safe_str(p.get("chosen_candidate_specificity_tier") or "").lower()
        return tier in ("exact_menu_match", "exact_local_profile", "chain_registry", "enriched_local_profile")

    def _top5_generic(p: Dict[str, Any]) -> bool:
        tier = _safe_str(p.get("chosen_candidate_specificity_tier") or "").lower()
        return tier == "generic_fallback"

    pct_top1 = 100 * sum(1 for p in top1_list if _top1_exact_or_chain(p)) / len(top1_list) if top1_list else 0
    pct_top3 = 100 * sum(1 for p in top3_list if _top3_good(p)) / len(top3_list) if top3_list else 0
    pct_top5_gen = 100 * sum(1 for p in top5_list if _top5_generic(p)) / len(top5_list) if top5_list else 100
    avg_spec_3 = sum(_specificity_score(p.get("chosen_candidate_specificity_tier")) for p in top3_list) / len(top3_list) if top3_list else 0
    avg_spec_5 = sum(_specificity_score(p.get("chosen_candidate_specificity_tier")) for p in top5_list) / len(top5_list) if top5_list else 0

    pct_concrete = 100 * sum(1 for p in top3_list if _is_concrete_order(p)) / len(top3_list) if top3_list else 0
    pct_swap = 100 * sum(1 for p in top3_list if _has_specific_swap(p)) / len(top3_list) if top3_list else 0
    pct_conf = 100 * sum(1 for p in top3_list if _has_high_confidence(p)) / len(top3_list) if top3_list else 0
    pct_non_gen = 100 * sum(1 for p in top3_list if not _is_generic_item(str(p.get("best_item_name") or p.get("best_order") or ""))) / len(top3_list) if top3_list else 0
    pct_reason = 100 * sum(1 for p in top3_list if _has_clear_difference_reason(p)) / len(top3_list) if top3_list else 0

    scores = [float(p.get("display_rank_score_100") or 0) for p in top5_list]
    names = [_safe_str(p.get("best_item_name") or p.get("best_order") or "") for p in top5_list]
    score_cluster = sum(1 for i, s in enumerate(scores) if i > 0 and abs(s - (scores[i - 1] if i else 0)) < 2) / max(1, len(scores) - 1) * 100 if len(scores) > 1 else 0
    name_dupe = 100 * (1 - len(set(n.lower() for n in names if n)) / max(1, len([n for n in names if n]))) if names else 0

    def _generic_cuisine_cluster(tokens: tuple, top5: list) -> int:
        count = 0
        for p in top5:
            name = _safe_str(p.get("best_item_name") or "").lower()
            place_name = _safe_str(p.get("name") or "").lower()
            if any(t in name or t in place_name for t in tokens):
                if _is_generic_item(name):
                    count += 1
        return count

    generic_indian = _generic_cuisine_cluster(("indian", "tandoori", "dal", "roti", "curry"), top5_list)
    generic_cafe = _generic_cuisine_cluster(("cafe", "coffee", "eggs on toast"), top5_list)
    generic_juice = _generic_cuisine_cluster(("juice", "smoothie", "protein shake"), top5_list)
    same_cuisine_gen = 100 * generic_indian / max(1, len(top5_list)) if top5_list else 0

    known_chains_all = [p for p in all_places_flat if _is_known_chain(p)]
    known_in_top5 = [p for p in top5_list if _is_known_chain(p)]
    known_fetched = len(set(str(p.get("place_id") or "") for p in known_chains_all))
    known_visible = len(known_in_top5)
    known_hidden = max(0, known_fetched - known_visible)
    missing_examples = []
    if known_hidden > 0:
        fetched_ids = {str(p.get("place_id") or ""): p for p in known_chains_all}
        visible_ids = {str(p.get("place_id") or "") for p in known_in_top5}
        limit = 10 if remediation_extended else 5
        for pid, p in list(fetched_ids.items()):
            if pid and pid not in visible_ids and len(missing_examples) < limit:
                missing_examples.append({
                    "place_id": pid,
                    "place_name": p.get("name") or p.get("place_name"),
                    "hidden_reason": p.get("hidden_reason") or "not_in_top_5",
                    "chosen_candidate_specificity_tier": p.get("chosen_candidate_specificity_tier"),
                    "display_rank_score_100": p.get("display_rank_score_100"),
                })

    coverage = summarize_launch_area_coverage(area_key)
    total_local = coverage.get("total_local_enriched_places") or 0
    total_strong = coverage.get("strong_profiles") or 0
    using_local = sum(1 for p in top5_list if str(p.get("menu_item_source") or "").lower() == "enriched_local_profile")
    using_chain = sum(1 for p in top5_list if str(p.get("menu_item_source") or "").lower() == "chain_registry")
    using_generic = sum(1 for p in top5_list if _top5_generic(p))
    pct_local = 100 * using_local / len(top5_list) if top5_list else 0
    pct_chain = 100 * using_chain / len(top5_list) if top5_list else 0
    pct_gen = 100 * using_generic / len(top5_list) if top5_list else 0

    status = _compute_readiness_status(
        p90_ms=p90,
        pct_top5_generic=pct_top5_gen,
        pct_top3_concrete=pct_concrete,
        pct_local=pct_local,
        known_hidden_rate=known_hidden / max(1, known_fetched) if known_fetched else 0,
    )

    n_gen = 10 if remediation_extended else 3
    n_dup = 10 if remediation_extended else 3
    examples = {}
    if include_examples:
        examples["concrete_examples"] = [
            {"name": p.get("name"), "best_item_name": p.get("best_item_name"), "display_rank_score_100": p.get("display_rank_score_100")}
            for p in top5_list if _is_concrete_order(p)
        ][:n_gen]
        examples["generic_problem_examples"] = [
            {
                "name": p.get("name"),
                "place_name": p.get("place_name") or p.get("name"),
                "place_id": p.get("place_id") or p.get("id") or "",
                "best_item_name": p.get("best_item_name"),
                "tier": p.get("chosen_candidate_specificity_tier"),
                "profile_store": p.get("profile_store"),
                "local_profile_source": p.get("local_profile_source"),
                "chosen_candidate_profile_source": p.get("chosen_candidate_profile_source"),
                "seeded_by_launch_pack": p.get("seeded_by_launch_pack"),
            }
            for p in top5_list if _top5_generic(p)
        ][:n_gen]
        examples["missing_chain_examples"] = missing_examples[:n_gen]
        dupes = []
        seen_scores: Dict[Union[int, float], Dict[str, Any]] = {}
        for p in top5_list:
            s = p.get("display_rank_score_100")
            if s is not None:
                if s in seen_scores:
                    dupes.append({"score": s, "places": [seen_scores[s].get("name"), p.get("name")]})
                else:
                    seen_scores[s] = p
        examples["duplicate_score_examples"] = dupes[:n_dup]
    dup_clusters: List[Dict[str, Any]] = []
    top_cuisines: List[Dict[str, Any]] = []
    if remediation_extended:
        score_to_places: Dict[Union[int, float], List[str]] = {}
        for p in top5_list:
            s = p.get("display_rank_score_100")
            if s is not None:
                n = p.get("name") or p.get("place_name") or "Unknown"
                score_to_places.setdefault(s, []).append(str(n))
        dup_clusters = [
            {"score": s, "count": len(pls), "places": pls}
            for s, pls in sorted(score_to_places.items(), key=lambda x: -len(x[1]))
            if len(pls) >= 2
        ][:10]
        cuisine_counts: Dict[str, int] = {}
        for p in top5_list:
            if _top5_generic(p):
                cu = _infer_cuisine_from_venue(p)
                if cu:
                    cuisine_counts[cu] = cuisine_counts.get(cu, 0) + 1
        top_cuisines = [
            {"cuisine": c, "generic_count": n}
            for c, n in sorted(cuisine_counts.items(), key=lambda x: -x[1])
        ][:10]

    return {
        "area_key": area_key,
        "display_name": display_name,
        "sample_count": sample_count,
        "readiness_status": status,
        "avg_total_response_ms": round(avg_ms, 1),
        "p50_total_response_ms": round(p50, 1),
        "p90_total_response_ms": round(p90, 1),
        "avg_fetched_places": round(avg_fetched, 1),
        "avg_shortlisted_places": round(avg_shortlisted, 1),
        "avg_deep_ranked_places": round(avg_deep, 1),
        "percent_top_1_exact_or_chain_backed": round(pct_top1, 1),
        "percent_top_3_exact_chain_or_enriched_local": round(pct_top3, 1),
        "percent_top_5_generic_fallback": round(pct_top5_gen, 1),
        "avg_specificity_score_top_3": round(avg_spec_3, 2),
        "avg_specificity_score_top_5": round(avg_spec_5, 2),
        "percent_top_3_with_concrete_order": round(pct_concrete, 1),
        "percent_top_3_with_specific_swap": round(pct_swap, 1),
        "percent_top_3_with_high_confidence": round(pct_conf, 1),
        "percent_top_3_with_non_generic_item_name": round(pct_non_gen, 1),
        "percent_top_3_with_clear_difference_reason": round(pct_reason, 1),
        "duplicate_score_cluster_rate_top_5": round(score_cluster, 1),
        "duplicate_candidate_name_rate_top_5": round(name_dupe, 1),
        "percent_top_5_same_cuisine_generic_guess": round(same_cuisine_gen, 1),
        "generic_indian_cluster_count": generic_indian,
        "generic_cafe_cluster_count": generic_cafe,
        "generic_juice_cluster_count": generic_juice,
        "known_chain_fetched_count": known_fetched,
        "known_chain_visible_top_5_count": known_visible,
        "known_chain_hidden_count": known_hidden,
        "top_missing_chain_examples": missing_examples[:10] if remediation_extended else missing_examples[:5],
        "top_cuisines_needing_enrichment": top_cuisines if remediation_extended else None,
        "duplicate_score_clusters": dup_clusters if remediation_extended else None,
        "local_enrichment": {
            **coverage,
            "visible_results_using_local_profiles_percent": round(pct_local, 1),
            "visible_results_using_chain_registry_percent": round(pct_chain, 1),
            "visible_results_using_generic_fallback_percent": round(pct_gen, 1),
        },
        **examples,
    }


def _compute_readiness_status(
    p90_ms: float,
    pct_top5_generic: float,
    pct_top3_concrete: float,
    pct_local: float,
    known_hidden_rate: float,
) -> str:
    issues = []
    if p90_ms > THRESHOLD_P90_MS:
        issues.append("too_slow")
    if pct_top5_generic > THRESHOLD_TOP5_GENERIC_PERCENT:
        issues.append("too_generic")
    if pct_top3_concrete < THRESHOLD_TOP3_CONCRETE_PERCENT:
        issues.append("too_generic")
    if pct_local < THRESHOLD_LOCAL_PROFILE_USAGE_PERCENT and pct_top5_generic > 30:
        issues.append("needs_local_enrichment")
    if known_hidden_rate > THRESHOLD_CHAIN_HIDDEN_RATE:
        issues.append("chain_coverage_gap")
    if len(issues) == 0:
        return "launch_ready"
    if len(issues) >= 3:
        return "mixed"
    return issues[0]


async def build_all_areas_report(
    *,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
    include_examples: bool = False,
    samples_per_area: int = 1,
) -> Dict[str, Any]:
    """Summaries for all configured launch areas. Use samples_per_area=1 for faster run."""
    areas = list_launch_areas()
    summaries = []
    for a in areas:
        key = str(a.get("area_key") or "").strip()
        if not key:
            continue
        pts = sample_points_for_area(key, count=max(1, min(5, samples_per_area)))
        r = await build_launch_readiness_report(
            key, fetch_fn=fetch_fn, sample_points=pts, include_examples=include_examples,
        )
        summaries.append({
            "area_key": r.get("area_key"),
            "display_name": r.get("display_name"),
            "readiness_status": r.get("readiness_status"),
            "sample_count": r.get("sample_count"),
            "p90_total_response_ms": r.get("p90_total_response_ms"),
            "percent_top_5_generic_fallback": r.get("percent_top_5_generic_fallback"),
            "percent_top_3_exact_chain_or_enriched_local": r.get("percent_top_3_exact_chain_or_enriched_local"),
        })
    return {"areas": summaries, "total_areas": len(summaries)}

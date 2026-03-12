"""
Suburb remediation: turns launch-readiness report output into prioritized product fixes.
Surfaces top problematic suburbs, missing chains, generic examples, duplicate clusters.
No LLM. Deterministic.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from launch_area_config import list_launch_areas, sample_points_for_area
from launch_readiness_report import build_launch_readiness_report


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _worst_suburb_score(report: Dict[str, Any]) -> float:
    """
    Composite score for "worst" suburb: higher = more problems.
    Weights: generic fallback %, hidden chain rate, duplicate cluster rate.
    """
    pct_gen = _safe_float(report.get("percent_top_5_generic_fallback"), 0)
    known_fetched = report.get("known_chain_fetched_count") or 0
    known_hidden = report.get("known_chain_hidden_count") or 0
    hidden_rate = known_hidden / max(1, known_fetched) if known_fetched else 0
    dup_rate = _safe_float(report.get("duplicate_score_cluster_rate_top_5"), 0)
    return pct_gen * 1.0 + hidden_rate * 100 * 1.5 + dup_rate * 0.5


def rank_suburbs_by_worst(reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank reports by worst composite score. Returns sorted list (worst first)."""
    scored = [(r, _worst_suburb_score(r)) for r in reports]
    scored.sort(key=lambda x: -x[1])
    return [r for r, _ in scored]


def build_remediation_list(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build remediation list for one suburb from its report.
    Expects report with remediation_extended=True for full data.
    """
    area_key = report.get("area_key") or ""
    display_name = report.get("display_name") or area_key

    missing = report.get("top_missing_chain_examples") or []
    generic = report.get("generic_problem_examples") or []

    cuisines = report.get("top_cuisines_needing_enrichment") or []
    dup_clusters = report.get("duplicate_score_clusters") or []

    return {
        "area_key": area_key,
        "display_name": display_name,
        "readiness_status": report.get("readiness_status"),
        "percent_top_5_generic_fallback": report.get("percent_top_5_generic_fallback"),
        "known_chain_hidden_count": report.get("known_chain_hidden_count"),
        "top_10_missing_chain_opportunities": missing[:10],
        "top_10_generic_fallback_venues": generic[:10],
        "top_cuisines_needing_enrichment": cuisines[:10],
        "top_duplicate_score_clusters": dup_clusters[:10],
    }


def surface_top_problems(reports: List[Dict[str, Any]], top_n: int = 2) -> Dict[str, Any]:
    """
    Surface top problematic suburbs and their remediation lists.
    """
    ranked = rank_suburbs_by_worst(reports)
    worst = ranked[:top_n]

    all_missing: List[Dict[str, Any]] = []
    all_generic: List[Dict[str, Any]] = []
    for r in worst:
        all_missing.extend((r.get("top_missing_chain_examples") or [])[:5])
        all_generic.extend((r.get("generic_problem_examples") or [])[:5])

    def _dedupe_by_name(items: List[Dict], key: str = "place_name") -> List[Dict]:
        seen = set()
        out = []
        for x in items:
            n = x.get(key) or x.get("name")
            if n and n not in seen:
                seen.add(n)
                out.append(x)
        return out[:10]

    return {
        "worst_suburbs": [
            {
                "area_key": r.get("area_key"),
                "display_name": r.get("display_name"),
                "readiness_status": r.get("readiness_status"),
                "percent_top_5_generic_fallback": r.get("percent_top_5_generic_fallback"),
                "known_chain_hidden_count": r.get("known_chain_hidden_count"),
                "known_chain_hidden_rate": (
                    (r.get("known_chain_hidden_count") or 0) / max(1, r.get("known_chain_fetched_count") or 1)
                ),
                "remediation_list": build_remediation_list(r),
            }
            for r in worst
        ],
        "top_missing_chain_examples": _dedupe_by_name(all_missing, "place_name"),
        "top_generic_problem_examples": _dedupe_by_name(all_generic, "name"),
    }


async def generate_prioritized_remediation(
    *,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
    top_n_suburbs: int = 2,
    samples_per_area: int = 2,
) -> Dict[str, Any]:
    """
    Generate full prioritized remediation for top N worst suburbs.
    Fetches reports for all areas with remediation_extended=True, then ranks and surfaces.
    """
    areas = list_launch_areas()
    reports: List[Dict[str, Any]] = []
    for a in areas:
        key = str(a.get("area_key") or "").strip()
        if not key:
            continue
        pts = sample_points_for_area(key, count=max(1, min(5, samples_per_area)))
        r = await build_launch_readiness_report(
            key,
            fetch_fn=fetch_fn,
            sample_points=pts,
            include_examples=True,
            remediation_extended=True,
        )
        reports.append(r)

    return surface_top_problems(reports, top_n=top_n_suburbs)

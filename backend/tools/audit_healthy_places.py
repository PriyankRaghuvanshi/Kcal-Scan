#!/usr/bin/env python3
"""
CLI for Healthy Nearby audit. Calls the same ranking path as GET /places/healthy/audit.
Usage:
  python backend/tools/audit_healthy_places.py --lat -33.80 --lng 150.97 --goal cut \\
    --remaining-calories 700 --remaining-protein 45 --radius-m 2500 --limit 10
  python backend/tools/audit_healthy_places.py --lat -33.80 --lng 150.97 --json
  python backend/tools/audit_healthy_places.py --lat -33.80 --lng 150.97 --markdown
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

try:
    import requests
except ImportError:
    requests = None


def _safe_str(v: Any, default: str = "-") -> str:
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except Exception:
        return default


def run_audit(
    base_url: str,
    lat: float,
    lng: float,
    radius_m: int = 3000,
    goal: str = "",
    remaining_calories: float | None = None,
    remaining_protein_g: float | None = None,
    sort_mode: str = "flat_score",
    limit: int = 10,
    include_filtered_out: bool = False,
    include_candidate_debug: bool = False,
    include_alert_candidates: bool = False,
    context_mode: str = "",
    post_workout: bool = False,
    late_night: bool = False,
    local_hour: int | None = None,
    poor_sleep_flag: bool = False,
    high_craving_risk_flag: bool = False,
) -> Dict[str, Any]:
    """Call GET /places/healthy/audit and return the JSON payload."""
    if not requests:
        raise RuntimeError("requests is required; pip install requests")
    params: Dict[str, Any] = {
        "lat": lat,
        "lng": lng,
        "radius_m": radius_m,
        "sort_mode": sort_mode,
        "limit": limit,
        "include_filtered_out": "true" if include_filtered_out else "false",
        "include_candidate_debug": "true" if include_candidate_debug else "false",
        "include_alert_candidates": "true" if include_alert_candidates else "false",
    }
    if goal:
        params["goal"] = goal
    if remaining_calories is not None:
        params["remaining_calories"] = remaining_calories
    if remaining_protein_g is not None:
        params["remaining_protein_g"] = remaining_protein_g
    if context_mode:
        params["context_mode"] = context_mode
    if post_workout:
        params["post_workout"] = "true"
    if late_night:
        params["late_night"] = "true"
    if local_hour is not None:
        params["local_hour"] = local_hour
    if poor_sleep_flag:
        params["poor_sleep_flag"] = "true"
    if high_craving_risk_flag:
        params["high_craving_risk_flag"] = "true"
    url = f"{base_url.rstrip('/')}/places/healthy/audit"
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def print_table(results: List[Dict[str, Any]], filtered_out: List[Dict[str, Any]] | None = None) -> None:
    """Print a readable table to stdout."""
    cols = ["rank", "place", "score", "band", "label", "confidence", "best item", "kcal", "protein", "section", "reason"]
    widths = [4, 22, 5, 4, 14, 10, 24, 5, 7, 10, 28]
    header = "".join(c.ljust(w) for c, w in zip(cols, widths))
    print(header)
    print("-" * len(header))
    for row in results:
        rank = _safe_int(row.get("rank"), 0)
        place = _safe_str(row.get("place_name"), "?")[: widths[1] - 1]
        score = _safe_int(row.get("display_rank_score_100"), 0)
        band = _safe_int(row.get("eligibility_band"), 0)
        label = _safe_str(row.get("recommendation_label"), "")[: widths[4] - 1]
        conf = _safe_str(row.get("confidence_label"), "")[: widths[5] - 1]
        item = _safe_str(row.get("best_item_name"), "")[: widths[6] - 1]
        kcal = _safe_int(row.get("best_item_calories"), 0)
        protein = _safe_int(row.get("best_item_protein"), 0)
        section = _safe_str(row.get("section"), "")[: widths[9] - 1]
        reason = _safe_str(row.get("rank_reason_short"), "")[: widths[10] - 1]
        line = f"{rank:<{widths[0]}}{place:<{widths[1]}}{score:<{widths[2]}}{band:<{widths[3]}}{label:<{widths[4]}}{conf:<{widths[5]}}{item:<{widths[6]}}{kcal:<{widths[7]}}{protein:<{widths[8]}}{section:<{widths[9]}}{reason:<{widths[10]}}"
        print(line)
    if filtered_out:
        print()
        print("Filtered out (limit):")
        for fo in filtered_out[:20]:
            name = _safe_str(fo.get("place_name"), "?")
            reason = _safe_str(fo.get("reason_filtered_out"), "")
            print(f"  - {name} | {reason}")


def print_markdown(results: List[Dict[str, Any]], filtered_out: List[Dict[str, Any]] | None = None) -> None:
    """Print a markdown table for pasting into docs/chats."""
    cols = ["rank", "place", "score", "band", "label", "confidence", "best item", "kcal", "protein", "section", "reason"]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    print(header)
    print(sep)
    for row in results:
        rank = row.get("rank", "")
        place = _safe_str(row.get("place_name"), "?").replace("|", "\\|")
        score = row.get("display_rank_score_100", "")
        band = row.get("eligibility_band", "")
        label = _safe_str(row.get("recommendation_label"), "").replace("|", "\\|")
        conf = _safe_str(row.get("confidence_label"), "").replace("|", "\\|")
        item = _safe_str(row.get("best_item_name"), "").replace("|", "\\|")
        kcal = row.get("best_item_calories", "")
        protein = row.get("best_item_protein", "")
        section = _safe_str(row.get("section"), "").replace("|", "\\|")
        reason = _safe_str(row.get("rank_reason_short"), "").replace("|", "\\|")
        print(f"| {rank} | {place} | {score} | {band} | {label} | {conf} | {item} | {kcal} | {protein} | {section} | {reason} |")
    if filtered_out:
        print()
        print("### Filtered out")
        print("| place_name | reason_filtered_out |")
        print("| --- | --- |")
        for fo in filtered_out:
            name = _safe_str(fo.get("place_name"), "?").replace("|", "\\|")
            reason = _safe_str(fo.get("reason_filtered_out"), "").replace("|", "\\|")
            print(f"| {name} | {reason} |")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Healthy Nearby ranking for a location (calls /places/healthy/audit)."
    )
    parser.add_argument("--lat", type=float, required=True, help="Latitude")
    parser.add_argument("--lng", type=float, required=True, help="Longitude")
    parser.add_argument("--radius-m", type=int, default=3000, help="Radius in metres (default 3000)")
    parser.add_argument("--goal", type=str, default="", help="e.g. cut, fat_loss")
    parser.add_argument("--remaining-calories", type=float, default=None, help="Remaining calories for the day")
    parser.add_argument("--remaining-protein", type=float, default=None, dest="remaining_protein_g", help="Remaining protein (g)")
    parser.add_argument("--sort-mode", type=str, default="flat_score", choices=("flat_score", "sectioned"), help="Sort mode")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default 10)")
    parser.add_argument("--include-filtered-out", action="store_true", help="Include places beyond limit in output")
    parser.add_argument("--include-candidate-debug", action="store_true", help="Include candidate_debug per result (generated candidates)")
    parser.add_argument("--include-alert-candidates", action="store_true", help="Include smart food alert candidates (alert_type, alert_score, eligible_to_send)")
    parser.add_argument("--context-mode", type=str, default="", help="Context mode override (e.g. post_workout_recovery, late_night_damage_control)")
    parser.add_argument("--post-workout", action="store_true", help="Post-workout recovery mode")
    parser.add_argument("--late-night", action="store_true", help="Late-night damage-control mode")
    parser.add_argument("--local-hour", type=int, default=None, help="Local hour 0-23 for breakfast/lunch/dinner inference")
    parser.add_argument("--poor-sleep-flag", action="store_true", help="Poor sleep; prefer satiating meals")
    parser.add_argument("--high-craving-risk-flag", action="store_true", help="High craving risk; penalise hyper-palatable combos")
    parser.add_argument("--base-url", type=str, default=None, help="API base URL (default from KCAL_AUDIT_BASE_URL or http://localhost:8000)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--markdown", action="store_true", help="Output markdown table")
    args = parser.parse_args()

    base_url = args.base_url or os.environ.get("KCAL_AUDIT_BASE_URL", "http://localhost:8000")

    try:
        data = run_audit(
            base_url=base_url,
            lat=args.lat,
            lng=args.lng,
            radius_m=args.radius_m,
            goal=args.goal,
            remaining_calories=args.remaining_calories,
            remaining_protein_g=args.remaining_protein_g,
            sort_mode=args.sort_mode,
            limit=args.limit,
            include_filtered_out=args.include_filtered_out,
            include_candidate_debug=args.include_candidate_debug,
            include_alert_candidates=args.include_alert_candidates,
            context_mode=args.context_mode,
            post_workout=args.post_workout,
            late_night=args.late_night,
            local_hour=args.local_hour,
            poor_sleep_flag=args.poor_sleep_flag,
            high_craving_risk_flag=args.high_craving_risk_flag,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    results = data.get("results") or []
    filtered_out = data.get("filtered_out") if args.include_filtered_out else None
    if filtered_out is None:
        filtered_out = []

    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    if args.markdown:
        print_markdown(results, filtered_out if filtered_out else None)
        return 0
    print_table(results, filtered_out if filtered_out else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())

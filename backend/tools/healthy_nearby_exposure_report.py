"""Rank chains by user-facing exposure × bug count to prioritise remediation.

Without server logs available locally, "exposure" is a composite proxy:
  - rollout_priority  (p0_core_trust=4, p1_high_value=3, p2_regional=2, p3=1)
  - confidence_tier   (tier_1_strong=3, tier_2_good=2, tier_3_basic=1)
  - market_spread     (count of markets the chain is live in)
  - ingested_items    (items present in chain_menu_ingested.json — required to surface at all)

Remediation leverage = exposure_score × real_bug_count (from menu_audit_report.json).

Outputs data/healthy_nearby_exposure_report.json and prints top targets.
"""

from __future__ import annotations

import collections
import json
import os
from typing import Dict, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROADMAP_PATH = os.path.join(REPO_ROOT, "data", "chain_coverage_roadmap.json")
INGESTED_PATH = os.path.join(REPO_ROOT, "data", "chain_menu_ingested.json")
AUDIT_PATH = os.path.join(REPO_ROOT, "data", "menu_audit_report.json")
OUT_PATH = os.path.join(REPO_ROOT, "data", "healthy_nearby_exposure_report.json")

PRIORITY_WEIGHT = {
    "p0_core_trust": 4,
    "p1_high_value": 3,
    "p2_regional_growth": 2,
    "p3_long_tail": 1,
}
TIER_WEIGHT = {"tier_1_strong": 3, "tier_2_good": 2, "tier_3_basic": 1}


def main() -> int:
    with open(ROADMAP_PATH) as fh:
        roadmap = json.load(fh)
    with open(INGESTED_PATH) as fh:
        ingested = json.load(fh)
    with open(AUDIT_PATH) as fh:
        audit = json.load(fh)

    items_by_chain_market: Dict[str, int] = {}
    for ck_market, items in ingested.get("chains", {}).items():
        if isinstance(items, list):
            items_by_chain_market[ck_market] = len(items)

    real_bugs_by_chain_market: Dict[str, int] = collections.Counter()
    for fl in audit.get("flags", []):
        if fl["severity"] in ("critical", "high", "medium"):
            real_bugs_by_chain_market[fl["chain_market"]] += 1

    rows: List[Dict] = []
    for chain in roadmap.get("chains", []):
        if chain.get("coverage_status") != "live":
            continue
        chain_key = chain.get("chain_key")
        if not chain_key:
            continue
        markets = chain.get("market_tags") or []
        prio_w = PRIORITY_WEIGHT.get(chain.get("rollout_priority", ""), 1)
        tier_w = TIER_WEIGHT.get(chain.get("confidence_tier", ""), 1)
        market_spread = len(markets)

        per_market: List[Dict] = []
        chain_total_items = 0
        chain_total_bugs = 0
        for market in markets:
            ck_market = f"{chain_key}::{market}"
            n_items = items_by_chain_market.get(ck_market, 0)
            n_bugs = real_bugs_by_chain_market.get(ck_market, 0)
            chain_total_items += n_items
            chain_total_bugs += n_bugs
            per_market.append({
                "market": market,
                "ingested_items": n_items,
                "real_bugs": n_bugs,
            })

        # Exposure score: weighted by priority/tier × market spread × log(items+1)
        # Items multiplier capped — having 8 vs 80 items doesn't multiply exposure 10x
        items_factor = min(chain_total_items, 50) / 10.0  # 0..5
        exposure_score = prio_w * tier_w * market_spread * (1 + items_factor)
        leverage_score = exposure_score * chain_total_bugs

        rows.append({
            "chain_key": chain_key,
            "display_name": chain.get("display_name") or chain_key,
            "rollout_priority": chain.get("rollout_priority"),
            "confidence_tier": chain.get("confidence_tier"),
            "market_spread": market_spread,
            "ingested_items_total": chain_total_items,
            "real_bugs_total": chain_total_bugs,
            "exposure_score": round(exposure_score, 2),
            "leverage_score": round(leverage_score, 2),
            "per_market": per_market,
            "notes": chain.get("notes", ""),
        })

    # Sort by leverage desc (where bugs > 0), then by pure exposure for the rest
    rows_with_bugs = sorted([r for r in rows if r["real_bugs_total"] > 0],
                            key=lambda r: -r["leverage_score"])
    rows_no_bugs = sorted([r for r in rows if r["real_bugs_total"] == 0],
                          key=lambda r: -r["exposure_score"])
    final_rows = rows_with_bugs + rows_no_bugs

    out = {
        "summary": {
            "total_chains_live": len(rows),
            "chains_with_real_bugs": len(rows_with_bugs),
            "chains_clean": len(rows_no_bugs),
            "exposure_proxy_signals": [
                "rollout_priority", "confidence_tier", "market_spread", "ingested_items"
            ],
            "note": "No server-side /places/healthy logs available locally; "
                    "exposure is a composite proxy. Replace with real impression "
                    "counts when telemetry pipeline lands.",
        },
        "chains": final_rows,
    }

    with open(OUT_PATH, "w") as fh:
        json.dump(out, fh, indent=2)

    print(f"\n=== HEALTHY NEARBY EXPOSURE × BUG REPORT ===")
    print(f"Live chains:               {len(rows)}")
    print(f"Chains with real bugs:     {len(rows_with_bugs)}")
    print(f"Chains clean:              {len(rows_no_bugs)}")
    print()
    print(f"=== TOP 30 REMEDIATION TARGETS (by leverage = exposure × bugs) ===")
    print(f"{'#':<4}{'chain':<25}{'prio':<6}{'mkts':<6}{'items':<7}{'bugs':<6}{'expos':<8}{'LEV':<8}")
    for i, r in enumerate(final_rows[:30], 1):
        prio = (r['rollout_priority'] or '?').replace('p0_core_trust', 'p0').replace('p1_high_value', 'p1').replace('p2_regional_growth', 'p2').replace('p3_long_tail', 'p3')
        print(f"{i:<4}{r['chain_key']:<25}{prio:<6}"
              f"{r['market_spread']:<6}{r['ingested_items_total']:<7}"
              f"{r['real_bugs_total']:<6}{r['exposure_score']:<8.1f}{r['leverage_score']:<8.1f}")

    print(f"\n=== TOP 10 CLEAN CHAINS BY EXPOSURE (already in good shape) ===")
    for i, r in enumerate(rows_no_bugs[:10], 1):
        print(f"  {i:<3}{r['chain_key']:<25} expos={r['exposure_score']:<6.1f} items={r['ingested_items_total']}")

    print(f"\nReport written: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

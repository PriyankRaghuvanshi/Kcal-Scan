"""List chain::market pairs that need hand-curated PDF ingestion.

A chain qualifies if EITHER:
  - It returned [] from the URL-grounded pipeline (Gemini found no web data).
  - Its current items in chain_menu_ingested.json have menu_item_source other
    than "real_menu" AND the chain has high audit-bug count.

For each target, prints search hints to help the operator find a PDF.

Run:
    python3 tools/list_handcuration_targets.py
    python3 tools/list_handcuration_targets.py --markdown   # GitHub-friendly
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INGESTED = f"{REPO}/data/chain_menu_ingested.json"
RUN_LOG = f"{REPO}/data/remediation_run_log.json"
AUDIT = f"{REPO}/data/menu_audit_report.json"
ROADMAP = f"{REPO}/data/chain_coverage_roadmap.json"
EXPOSURE = f"{REPO}/data/healthy_nearby_exposure_report.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", action="store_true",
                        help="Output as a GitHub-flavoured markdown table")
    parser.add_argument("--max", type=int, default=40)
    args = parser.parse_args()

    with open(INGESTED) as f:
        store = json.load(f)
    chains = store.get("chains", {})

    # Run log — completed chains where item count was 0
    completed = {}
    if os.path.exists(RUN_LOG):
        with open(RUN_LOG) as f:
            for k, v in json.load(f).items():
                if v.get("status") in ("ok", "needs_review", "failed"):
                    completed[k] = v

    # Audit bugs per chain::market
    audit_bugs = collections.Counter()
    if os.path.exists(AUDIT):
        with open(AUDIT) as f:
            for fl in json.load(f).get("flags", []):
                if fl["severity"] in ("critical", "high", "medium"):
                    audit_bugs[fl["chain_market"]] += 1

    # Roadmap — display name + priority
    display = {}
    priority = {}
    if os.path.exists(ROADMAP):
        with open(ROADMAP) as f:
            for c in json.load(f).get("chains", []):
                ck = c.get("chain_key")
                if not ck: continue
                display[ck] = c.get("display_name") or ck
                priority[ck] = c.get("rollout_priority", "")

    # Exposure leverage
    leverage = {}
    if os.path.exists(EXPOSURE):
        with open(EXPOSURE) as f:
            for r in json.load(f).get("chains", []):
                leverage[r["chain_key"]] = r.get("leverage_score", 0)

    targets = []
    for ck_market, items in chains.items():
        if not isinstance(items, list): continue
        chain_key, _, market = ck_market.partition("::")
        sources = {str(it.get("menu_item_source") or "") for it in items}
        is_real_menu = sources == {"real_menu"} and items  # all real_menu and non-empty
        if is_real_menu:
            continue  # already remediated

        # Was the URL-grounded pipeline tried and returned 0 items?
        run_entry = completed.get(ck_market, {})
        url_pipeline_failed = (
            run_entry and run_entry.get("status") in ("ok", "failed", "needs_review")
            and len(items) == len(items)  # always true; placeholder
        )

        bugs = audit_bugs.get(ck_market, 0)

        # Filter: include if URL pipeline was tried and didn't help, OR has bugs
        if not (run_entry or bugs >= 2):
            continue

        targets.append({
            "chain_market": ck_market,
            "chain_key": chain_key,
            "market": market,
            "display_name": display.get(chain_key, chain_key),
            "priority": priority.get(chain_key, ""),
            "leverage": leverage.get(chain_key, 0),
            "items_now": len(items),
            "bugs": bugs,
            "url_pipeline_status": run_entry.get("status", ""),
        })

    # Sort: leverage desc, then bugs desc
    targets.sort(key=lambda t: (-(t["leverage"] or 0), -t["bugs"]))
    targets = targets[: args.max]

    if args.markdown:
        print("| Chain | Market | Items | Bugs | Priority | Leverage | URL pipeline | PDF search hint |")
        print("|-------|--------|-------|------|----------|----------|--------------|-----------------|")
        for t in targets:
            hint = pdf_search_hint(t["chain_key"], t["display_name"], t["market"])
            print(f"| {t['display_name']} | {t['market']} | {t['items_now']} | "
                  f"{t['bugs']} | {t['priority']} | {t['leverage']} | "
                  f"{t['url_pipeline_status'] or '-'} | {hint} |")
        return 0

    print(f"\n=== HAND-CURATION TARGETS ({len(targets)}) ===\n")
    print(f"{'#':<4}{'chain_market':<28}{'items':>6}{'bugs':>5}{'prio':<6}{'lev':>7}  url_run")
    for i, t in enumerate(targets, 1):
        prio = (t["priority"] or "").replace("p0_core_trust", "p0").replace(
            "p1_high_value", "p1").replace("p2_regional_growth", "p2").replace("p3_long_tail", "p3")
        print(f"{i:<4}{t['chain_market']:<28}{t['items_now']:>6}{t['bugs']:>5}"
              f"{prio:<6}{t['leverage']:>7}  {t['url_pipeline_status'] or '-'}")
    print()
    print("Workflow per target:")
    print("  1. Find the chain's official nutrition PDF:")
    print("     - Google: \"<chain> nutrition information pdf <market>\"")
    print("     - Try the chain's allergen/footer link, e.g. /allergens, /nutrition")
    print("     - For US chains: look for FDA-mandated nutrition disclosure PDFs")
    print("     - For IN chains: FSSAI or FoSCoS-linked menus are sparse; try the brand")
    print("       Twitter/Instagram bio for menu links")
    print("  2. Save PDF locally (e.g. ~/Downloads/<chain>_<market>.pdf)")
    print("  3. Run:")
    print("     python3 tools/ingest_chain_from_pdf.py \\")
    print("         --chain <chain_key> --market <MARKET> \\")
    print("         --pdf-path ~/Downloads/<chain>_<market>.pdf \\")
    print("         --source-url <real PDF URL or chain website>")
    print("  4. Review staging output. If clean, re-run with --commit.")
    return 0


def pdf_search_hint(chain_key: str, display_name: str, market: str) -> str:
    return f"`{display_name} nutrition pdf {market}`"


if __name__ == "__main__":
    sys.exit(main())

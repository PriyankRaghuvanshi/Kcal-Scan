"""Batch-remediate top-N chains by exposure × bug leverage.

Reads data/healthy_nearby_exposure_report.json, takes the top N chain::market
pairs, pulls the existing source_url for each from chain_menu_ingested.json,
and runs tools/ingest_chain_from_url.py in --stage-only mode by default
(staging output → human review → manual promote).

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 tools/remediate_top_chains.py --top 10
    python3 tools/remediate_top_chains.py --top 30 --commit   # writes directly to ingested store
    python3 tools/remediate_top_chains.py --dry-run            # skips API calls, shows plan

Writes a run log to data/remediation_run_log.json so reruns skip completed entries.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from typing import Dict, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXPOSURE_PATH = os.path.join(REPO_ROOT, "data", "healthy_nearby_exposure_report.json")
INGESTED_PATH = os.path.join(REPO_ROOT, "data", "chain_menu_ingested.json")
RUN_LOG_PATH = os.path.join(REPO_ROOT, "data", "remediation_run_log.json")
NEEDS_URL_PATH = os.path.join(REPO_ROOT, "data", "remediation_needs_url.json")
INGEST_SCRIPT = os.path.join(REPO_ROOT, "tools", "ingest_chain_from_url.py")


def load_source_urls() -> Dict[str, str]:
    """Map chain::market -> source_url from existing ingested items."""
    with open(INGESTED_PATH) as fh:
        store = json.load(fh)
    out: Dict[str, str] = {}
    for ck_market, items in store.get("chains", {}).items():
        if isinstance(items, list) and items:
            url = str(items[0].get("source_url") or "").strip()
            if url:
                out[ck_market] = url
    return out


def load_run_log() -> Dict[str, Dict]:
    if not os.path.exists(RUN_LOG_PATH):
        return {}
    with open(RUN_LOG_PATH) as fh:
        return json.load(fh)


def save_run_log(log: Dict[str, Dict]) -> None:
    with open(RUN_LOG_PATH, "w") as fh:
        json.dump(log, fh, indent=2)


def plan_targets(top_n: int) -> List[Dict]:
    """Return list of {chain_key, market, url, leverage_score} for top N."""
    with open(EXPOSURE_PATH) as fh:
        exp = json.load(fh)
    urls = load_source_urls()
    targets: List[Dict] = []
    needs_url: List[Dict] = []
    seen_chain_markets = set()

    for row in exp.get("chains", [])[:top_n]:
        ck = row["chain_key"]
        for pm in row.get("per_market", []):
            m = pm["market"]
            ck_m = f"{ck}::{m}"
            if ck_m in seen_chain_markets:
                continue
            seen_chain_markets.add(ck_m)
            entry = {
                "chain_key": ck,
                "market": m,
                "chain_market": ck_m,
                "leverage_score": row["leverage_score"],
                "real_bugs": pm["real_bugs"],
                "ingested_items": pm["ingested_items"],
            }
            url = urls.get(ck_m)
            if url:
                entry["url"] = url
                targets.append(entry)
            else:
                needs_url.append(entry)

    if needs_url:
        with open(NEEDS_URL_PATH, "w") as fh:
            json.dump({
                "note": "These chain::market pairs have no URL in the ingested store. "
                        "Add a URL manually and rerun with --chain/--market/--url.",
                "entries": needs_url,
            }, fh, indent=2)

    return targets


def run_one(entry: Dict, stage_only: bool, commit: bool, dry_run: bool) -> Dict:
    cmd = [
        sys.executable, INGEST_SCRIPT,
        "--chain", entry["chain_key"],
        "--market", entry["market"],
        "--url", entry["url"],
    ]
    if dry_run:
        cmd.append("--dry-run")
    elif stage_only and not commit:
        cmd.append("--stage-only")

    print(f"\n{'='*70}")
    print(f"TARGET: {entry['chain_market']:25s}  bugs={entry['real_bugs']}  "
          f"items={entry['ingested_items']}  leverage={entry['leverage_score']}")
    print(f"URL:    {entry['url']}")
    print(f"CMD:    {' '.join(cmd)}")

    if dry_run:
        print("(dry-run — skipping actual execution)")
        return {"status": "dry_run", "rc": 0}

    t0 = dt.datetime.utcnow()
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=False, timeout=600)
        rc = result.returncode
    except subprocess.TimeoutExpired:
        rc = -1
    elapsed = (dt.datetime.utcnow() - t0).total_seconds()
    status = "ok" if rc == 0 else ("needs_review" if rc == 2 else "failed")
    return {"status": status, "rc": rc, "elapsed_s": round(elapsed, 1),
            "completed_at": dt.datetime.utcnow().isoformat() + "Z"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=10,
                        help="How many chains (from exposure report) to process")
    parser.add_argument("--commit", action="store_true",
                        help="Write directly to ingested store (default: --stage-only)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Plan + print, skip API calls")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if run log shows 'ok' for that target")
    args = parser.parse_args()

    targets = plan_targets(args.top)
    print(f"\n=== REMEDIATION PLAN ===")
    print(f"Top N chains:     {args.top}")
    print(f"Eligible targets: {len(targets)} (URLs found)")
    print(f"Commit mode:      {'direct-write' if args.commit else 'stage-only'}")
    if os.path.exists(NEEDS_URL_PATH):
        print(f"Needs URL:        written to {NEEDS_URL_PATH}")

    run_log = load_run_log()
    results: Dict[str, Dict] = {}
    for entry in targets:
        ck_m = entry["chain_market"]
        prior = run_log.get(ck_m)
        if prior and prior.get("status") == "ok" and not args.force:
            print(f"\nSKIP {ck_m} — already ok in run log (use --force to rerun)")
            results[ck_m] = prior
            continue
        res = run_one(entry, stage_only=True, commit=args.commit, dry_run=args.dry_run)
        results[ck_m] = res
        run_log[ck_m] = res
        save_run_log(run_log)

    print(f"\n=== SUMMARY ===")
    by_status = {}
    for ck_m, r in results.items():
        by_status.setdefault(r["status"], []).append(ck_m)
    for status, names in by_status.items():
        print(f"  {status:15s} {len(names)}")
        for n in names[:5]:
            print(f"    - {n}")
        if len(names) > 5:
            print(f"    ... and {len(names)-5} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())

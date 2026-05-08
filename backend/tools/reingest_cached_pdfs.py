"""Re-ingest already-cached PDFs through the deterministic pipeline.

The data/chain_pdfs/ directory has dozens of PDFs downloaded during the
Gemini-era runs. They're all real chain nutrition PDFs whose origin URL we
can recover from chain_menu_ingested.json (each item carries source_url; the
PDF filename is sha256(url)[:16].pdf).

For every cached PDF we can map back to a chain::market, this script:
  1. extracts items via tools.ingest_chain_from_url.extract_items_from_pdf_path
  2. normalizes + validates against the chain::market
  3. compares the deterministic pass count against current ingested-store
     item count for the same chain::market
  4. stages the result; --commit promotes anything that grows or matches
     existing coverage without losing items

No network calls. No Gemini. Only the cached files.

Usage:
    python3 tools/reingest_cached_pdfs.py --dry-run     # list mapping + outcome
    python3 tools/reingest_cached_pdfs.py --stage-only  # write staging files
    python3 tools/reingest_cached_pdfs.py --commit      # promote (with backup)
    python3 tools/reingest_cached_pdfs.py --chain-market subway::IN  # filter
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from typing import Dict, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from ingest_chain_from_url import (  # noqa: E402
    INGESTED_PATH,
    PDF_CACHE_DIR,
    extract_items_from_pdf_path,
    normalize_item,
    validate_items,
    write_staging,
    write_with_backup,
)

EXTRACTOR_VERSION = "deterministic_pdf_v1"


def _build_pdf_url_index() -> Dict[str, Tuple[str, str]]:
    """Return {url_hash16: (chain_market, source_url)} from the ingested store."""
    with open(INGESTED_PATH) as fh:
        store = json.load(fh)
    chains = store.get("chains", {})
    # Vote: a URL might appear in many items; we trust it for the chain::market
    # that contains it most often.
    votes: Dict[Tuple[str, str], int] = defaultdict(int)
    for chain_market, items in chains.items():
        if not isinstance(items, list):
            continue
        for it in items:
            url = (it.get("source_url") or "").strip()
            if not url or "pdf" not in url.lower():
                continue
            votes[(url, chain_market)] += 1
    # Pick the most-voted chain::market per URL
    by_url: Dict[str, Tuple[str, int]] = {}
    for (url, cm), n in votes.items():
        if url not in by_url or by_url[url][1] < n:
            by_url[url] = (cm, n)
    out: Dict[str, Tuple[str, str]] = {}
    for url, (cm, _n) in by_url.items():
        h = hashlib.sha256(url.encode()).hexdigest()[:16]
        out[h] = (cm, url)
    return out


def _existing_item_count(chain_market: str) -> int:
    with open(INGESTED_PATH) as fh:
        store = json.load(fh)
    items = store.get("chains", {}).get(chain_market, [])
    return len(items) if isinstance(items, list) else 0


def _existing_real_menu_count(chain_market: str) -> int:
    with open(INGESTED_PATH) as fh:
        store = json.load(fh)
    items = store.get("chains", {}).get(chain_market, [])
    if not isinstance(items, list):
        return 0
    return sum(1 for it in items if it.get("menu_item_source") == "real_menu")


def _is_valid_pdf(path: str) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) < 1024:
        return False
    with open(path, "rb") as fh:
        return fh.read(5) == b"%PDF-"


def _process_one(
    pdf_path: str,
    chain_market: str,
    source_url: str,
    *,
    commit: bool,
    stage_only: bool,
) -> Dict:
    chain_key, market = chain_market.split("::")
    run_id = uuid.uuid4().hex[:12]
    pdf_hash = hashlib.sha256(open(pdf_path, "rb").read()).hexdigest()[:16]

    rows = extract_items_from_pdf_path(pdf_path, source_url)
    if not rows:
        return {
            "chain_market": chain_market,
            "status": "no_rows",
            "extracted": 0,
            "passing": 0,
            "blocking": 0,
            "existing_total": _existing_item_count(chain_market),
            "existing_real_menu": _existing_real_menu_count(chain_market),
            "action": "skipped",
        }

    items = [
        normalize_item(
            r.__dict__, chain_key, market, source_url, run_id, pdf_hash,
            confidence=0.97,
            extraction_method="pdf_table_extract",
            parse_method=r.parse_method or "pdf_table",
            extractor_version=EXTRACTOR_VERSION,
        )
        for r in rows
    ]
    passing, failures = validate_items(items, chain_market)

    existing_total = _existing_item_count(chain_market)
    existing_real = _existing_real_menu_count(chain_market)

    out = {
        "chain_market": chain_market,
        "status": "ok",
        "extracted": len(rows),
        "passing": len(passing),
        "blocking": len(failures),
        "existing_total": existing_total,
        "existing_real_menu": existing_real,
    }

    if not passing:
        out["action"] = "skipped_zero_passing"
        return out

    if stage_only:
        path = write_staging(chain_key, market, passing, [])
        out["action"] = "staged"
        out["staging_path"] = path
        return out

    if commit:
        # Refusal rule: don't shrink existing coverage. We compare against the
        # full existing item count (not just real_menu) because the new payload
        # *replaces* the chain::market entry.
        if existing_total > len(passing) and existing_real > len(passing):
            path = write_staging(chain_key, market, passing,
                                 [{"reason": "would_shrink_real_menu",
                                   "detail": f"existing_real_menu={existing_real} "
                                             f"> new_passing={len(passing)}; "
                                             f"refusing to overwrite"}])
            out["action"] = "refused_shrink"
            out["staging_path"] = path
            return out
        backup_path = write_with_backup(chain_key, market, passing)
        out["action"] = "committed"
        out["backup_path"] = backup_path
        return out

    # Default = stage-only when neither flag set
    path = write_staging(chain_key, market, passing, [])
    out["action"] = "staged"
    out["staging_path"] = path
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="list mappings and predicted outcomes; no extraction")
    parser.add_argument("--stage-only", action="store_true",
                        help="extract + validate + write staging files (default)")
    parser.add_argument("--commit", action="store_true",
                        help="extract, validate, and overwrite the ingested store "
                             "(skips chain::markets that would shrink real_menu coverage)")
    parser.add_argument("--chain-market", action="append", dest="filters",
                        help="only process this chain::market (repeatable)")
    parser.add_argument("--cache-dir", default=PDF_CACHE_DIR)
    args = parser.parse_args()

    if args.commit and args.dry_run:
        print("ERROR: --commit and --dry-run are mutually exclusive", file=sys.stderr)
        return 1

    pdf_to_cm = _build_pdf_url_index()
    print(f"\n=== REINGEST CACHED PDFs ({EXTRACTOR_VERSION}) ===")
    print(f"  ingested store : {INGESTED_PATH}")
    print(f"  pdf cache      : {args.cache_dir}")
    print(f"  url->cm mappings : {len(pdf_to_cm)}")

    # Find all valid cached PDFs that we have a mapping for
    eligible: List[Tuple[str, str, str]] = []  # (path, chain_market, url)
    skipped_orphan = 0
    skipped_invalid = 0
    for fname in sorted(os.listdir(args.cache_dir)):
        path = os.path.join(args.cache_dir, fname)
        if not _is_valid_pdf(path):
            skipped_invalid += 1
            continue
        stem = fname.replace(".pdf", "")
        if stem not in pdf_to_cm:
            skipped_orphan += 1
            continue
        cm, url = pdf_to_cm[stem]
        if args.filters and cm not in args.filters:
            continue
        eligible.append((path, cm, url))

    print(f"  eligible PDFs  : {len(eligible)}")
    print(f"  orphan PDFs    : {skipped_orphan} (no chain::market mapping)")
    print(f"  invalid PDFs   : {skipped_invalid}")
    if not eligible:
        print("\nNothing to process.")
        return 0

    print(f"\n  {'chain_market':<28s} {'existing':>10s} {'rmenu':>6s}  url")
    print(f"  {'-'*28} {'-'*10} {'-'*6}  ---")
    for _, cm, url in eligible:
        print(f"  {cm:<28s} {_existing_item_count(cm):>10d} {_existing_real_menu_count(cm):>6d}  {url[:60]}")

    if args.dry_run:
        print("\nDRY RUN — exiting without extraction.")
        return 0

    print(f"\n--- PROCESSING ---")
    results: List[Dict] = []
    t_start = time.time()
    for i, (path, cm, url) in enumerate(eligible, 1):
        print(f"\n[{i}/{len(eligible)}] {cm}  ({os.path.basename(path)})")
        t0 = time.time()
        try:
            r = _process_one(
                path, cm, url,
                commit=args.commit,
                stage_only=args.stage_only or (not args.commit),
            )
        except Exception as exc:
            print(f"      ERROR: {type(exc).__name__}: {exc}")
            results.append({
                "chain_market": cm, "status": "error", "extracted": 0,
                "passing": 0, "blocking": 0,
                "existing_total": _existing_item_count(cm),
                "existing_real_menu": _existing_real_menu_count(cm),
                "action": "errored", "error": str(exc),
            })
            continue
        results.append(r)
        delta = (r.get("passing", 0)) - r.get("existing_real_menu", 0)
        delta_s = f"{delta:+d}" if delta else "0"
        print(f"      extracted={r['extracted']:>3d} passing={r['passing']:>3d} "
              f"blocking={r['blocking']:>2d}  existing_real={r['existing_real_menu']:>3d} "
              f"delta={delta_s:>4s}  action={r['action']}  ({time.time()-t0:.1f}s)")

    print(f"\n=== SUMMARY ({time.time()-t_start:.1f}s total) ===")
    by_action: Dict[str, int] = defaultdict(int)
    total_passing = 0
    total_delta = 0
    for r in results:
        by_action[r["action"]] += 1
        total_passing += r.get("passing", 0)
        total_delta += r.get("passing", 0) - r.get("existing_real_menu", 0)
    print(f"  total passing items extracted: {total_passing}")
    print(f"  net real_menu delta vs current store: {total_delta:+d}")
    print(f"  outcomes: {dict(by_action)}")
    print()
    print(f"  {'chain_market':<28s} {'extr':>5s} {'pass':>5s} {'block':>6s} "
          f"{'real':>5s} {'delta':>6s}  action")
    print(f"  {'-'*28} {'-'*5} {'-'*5} {'-'*6} {'-'*5} {'-'*6}  ---")
    for r in results:
        delta = r.get("passing", 0) - r.get("existing_real_menu", 0)
        print(f"  {r['chain_market']:<28s} {r['extracted']:>5d} {r['passing']:>5d} "
              f"{r['blocking']:>6d} {r['existing_real_menu']:>5d} "
              f"{delta:>+6d}  {r['action']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

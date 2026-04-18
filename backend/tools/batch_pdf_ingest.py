"""Batch PDF ingestion — process multiple chain nutrition PDFs in sequence.

Reads chain_pdf_sources.json and processes each entry that has a real PDF URL
(skipping web pages), calling the same Gemini-based extraction pipeline as
ingest_chain_from_pdf.py.

Usage:
    export GEMINI_API_KEY=AIza...

    # Dry run — list what would be processed
    python3 tools/batch_pdf_ingest.py --dry-run

    # Process all eligible PDFs
    python3 tools/batch_pdf_ingest.py --commit

    # Process specific chains only
    python3 tools/batch_pdf_ingest.py --chain mcdonalds --chain subway --commit

    # Set max cost budget (default $5)
    python3 tools/batch_pdf_ingest.py --max-cost 2.00 --commit
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from ingest_chain_from_pdf import (  # noqa: E402
    EXTRACTOR_VERSION,
    MODEL,
    _download_pdf,
    call_gemini_with_pdf,
)
from ingest_chain_from_url import (  # noqa: E402
    EXTRACTION_PROMPT,
    INGESTED_PATH,
    MAX_RETRIES,
    REPAIR_PROMPT_PREFIX,
    normalize_item,
    parse_json_array,
    validate_items,
    write_staging,
    write_with_backup,
)

SOURCES_PATH = os.path.join(os.path.dirname(__file__), "chain_pdf_sources.json")
RATE_LIMIT_DELAY = 5  # seconds between chains
SKIP_THRESHOLD = 30  # chains with >= this many items are skipped
# Gemini 2.5 Flash pricing (per 1M tokens, as of 2025)
COST_PER_1M_INPUT = 0.15   # $0.15 / 1M input tokens
COST_PER_1M_OUTPUT = 0.60  # $0.60 / 1M output tokens

# Heuristic: URLs ending in these extensions or containing these patterns
# are likely web pages, not downloadable PDFs.
WEB_PAGE_INDICATORS = [
    "/nutrition",
    "/menu",
    "calculator",
    "cal-o-meter",
    ".jsp",
    ".html",
    ".htm",
    "/info",
]


def _is_likely_pdf_url(url: str) -> bool:
    """Return True if the URL looks like a downloadable PDF, not a web page."""
    lower = url.lower()
    if lower.endswith(".pdf"):
        return True
    for indicator in WEB_PAGE_INDICATORS:
        if indicator in lower:
            return False
    # Ambiguous — treat as PDF (let download fail gracefully)
    return True


def _load_sources(path: str) -> List[Dict[str, Any]]:
    """Load chain_pdf_sources.json and return the sources list."""
    with open(path) as fh:
        data = json.load(fh)
    return data.get("sources", [])


def _load_existing_counts() -> Dict[str, int]:
    """Return {chain_market: item_count} from the ingested store."""
    if not os.path.exists(INGESTED_PATH):
        return {}
    with open(INGESTED_PATH) as fh:
        store = json.load(fh)
    chains = store.get("chains", {})
    return {k: len(v) if isinstance(v, list) else 0 for k, v in chains.items()}


def _estimate_cost(prompt_tokens: int, candidate_tokens: int) -> float:
    """Estimate USD cost from token counts."""
    return (prompt_tokens * COST_PER_1M_INPUT / 1_000_000
            + candidate_tokens * COST_PER_1M_OUTPUT / 1_000_000)


def _process_one(
    chain_key: str,
    market: str,
    pdf_url: str,
    commit: bool,
) -> Tuple[str, int, float, List[str]]:
    """Process a single chain PDF. Returns (status, item_count, cost_usd, errors)."""
    import hashlib

    chain_market = f"{chain_key}::{market}"
    ingest_run_id = uuid.uuid4().hex[:12]
    errors: List[str] = []
    total_cost = 0.0

    # Download PDF
    try:
        pdf_path = _download_pdf(pdf_url)
    except Exception as e:
        return ("download_failed", 0, 0.0, [f"Download failed: {e}"])

    pdf_hash = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]
    source_url = pdf_url

    # Build extraction prompt
    prompt = EXTRACTION_PROMPT.format(
        chain_key=chain_key, market=market, url=source_url
    ) + ("\n\nNOTE: You have been given DIRECT ACCESS to the chain's official "
         "nutrition PDF as your source. Extract menu items with macros directly "
         "from the PDF — do NOT use Google Search; the PDF IS the source of truth.")

    # Call Gemini
    try:
        t0 = time.time()
        raw_text = call_gemini_with_pdf(prompt, pdf_path)
        elapsed = time.time() - t0
        print(f"      response_chars={len(raw_text)}  elapsed={elapsed:.1f}s")
    except Exception as e:
        return ("gemini_failed", 0, 0.0, [f"Gemini call failed: {e}"])

    # Parse response
    raw_items = parse_json_array(raw_text)
    if not raw_items:
        return ("no_items", 0, 0.0, ["No items extracted from PDF"])

    items = [
        normalize_item(r, chain_key, market, source_url, ingest_run_id, pdf_hash)
        for r in raw_items
    ]
    for it in items:
        it["extractor_version"] = EXTRACTOR_VERSION
        it["extraction_method"] = "pdf_upload"
        it["parse_method"] = "llm_pdf"

    # Validate
    passing, failures = validate_items(items, chain_market)
    print(f"      extracted={len(raw_items)}  passing={len(passing)}  "
          f"failures={len(failures)}")

    # Repair loop
    retries = 0
    while failures and retries < MAX_RETRIES:
        retries += 1
        print(f"      repair pass {retries}/{MAX_RETRIES}...")
        repair_prompt = REPAIR_PROMPT_PREFIX.format(
            failures=json.dumps(failures, indent=2)
        ) + "\n\nOriginal extraction:\n" + raw_text
        try:
            repair_text = call_gemini_with_pdf(repair_prompt, pdf_path)
            raw_items = parse_json_array(repair_text)
            items = [
                normalize_item(r, chain_key, market, source_url, ingest_run_id, pdf_hash)
                for r in raw_items
            ]
            for it in items:
                it["extractor_version"] = EXTRACTOR_VERSION
                it["extraction_method"] = "pdf_upload"
                it["parse_method"] = "llm_pdf"
            passing, failures = validate_items(items, chain_market)
            print(f"        after repair: passing={len(passing)}  "
                  f"failures={len(failures)}")
            raw_text = repair_text
        except Exception as e:
            errors.append(f"Repair pass {retries} failed: {e}")
            break

    if failures:
        staging_path = write_staging(chain_key, market, items, failures)
        errors.append(f"Validation failures remain after {retries} retries; "
                      f"staged to {staging_path}")
        return ("validation_failed", len(passing), total_cost, errors)

    if not passing:
        return ("no_passing_items", 0, total_cost, ["All items failed validation"])

    # Write results
    if commit:
        backup_path = write_with_backup(chain_key, market, passing)
        print(f"      COMMITTED {len(passing)} items (backup: {backup_path})")
    else:
        staging_path = write_staging(chain_key, market, passing, [])
        print(f"      STAGED {len(passing)} items to {staging_path}")

    return ("ok", len(passing), total_cost, errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch PDF ingestion for chain nutrition data"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List what would be processed without actually doing it"
    )
    parser.add_argument(
        "--chain", action="append", dest="chains", default=None,
        help="Filter to specific chain(s). Can be repeated: --chain mcdonalds --chain subway"
    )
    parser.add_argument(
        "--max-cost", type=float, default=5.0,
        help="Max estimated cost in USD before stopping (default: $5.00)"
    )
    parser.add_argument(
        "--commit", action="store_true",
        help="Write results to chain_menu_ingested.json (default: stage-only)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Process even if chain already has 30+ items"
    )
    parser.add_argument(
        "--sources", default=SOURCES_PATH,
        help="Path to chain_pdf_sources.json (default: auto-detected)"
    )
    args = parser.parse_args()

    # Validate environment
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        return 1

    # Load sources
    try:
        sources = _load_sources(args.sources)
    except Exception as e:
        print(f"ERROR: Failed to load sources from {args.sources}: {e}",
              file=sys.stderr)
        return 1

    existing_counts = _load_existing_counts()

    # Filter to real PDF URLs
    eligible: List[Dict[str, Any]] = []
    skipped_web: List[str] = []
    skipped_deep: List[str] = []
    skipped_filter: List[str] = []

    for src in sources:
        chain_key = src["chain"].lower()
        market = src["market"].upper()
        pdf_url = src.get("pdf_url", "")
        chain_market = f"{chain_key}::{market}"

        # Chain filter
        if args.chains and chain_key not in [c.lower() for c in args.chains]:
            skipped_filter.append(chain_market)
            continue

        # Skip web pages
        if not _is_likely_pdf_url(pdf_url):
            skipped_web.append(f"{chain_market} ({pdf_url})")
            continue

        # Skip chains with enough items already
        item_count = existing_counts.get(chain_market, 0)
        if item_count >= SKIP_THRESHOLD and not args.force:
            skipped_deep.append(f"{chain_market} ({item_count} items)")
            continue

        eligible.append({
            "chain_key": chain_key,
            "market": market,
            "pdf_url": pdf_url,
            "existing_items": item_count,
            "notes": src.get("notes", ""),
        })

    # Print summary
    print(f"\n{'='*60}")
    print(f"  BATCH PDF INGEST — {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")
    print(f"  Sources file:     {args.sources}")
    print(f"  Total entries:    {len(sources)}")
    print(f"  Eligible (PDF):   {len(eligible)}")
    print(f"  Skipped (web):    {len(skipped_web)}")
    print(f"  Skipped (deep):   {len(skipped_deep)}")
    if args.chains:
        print(f"  Skipped (filter): {len(skipped_filter)}")
    print(f"  Max cost budget:  ${args.max_cost:.2f}")
    print(f"  Mode:             {'DRY RUN' if args.dry_run else ('COMMIT' if args.commit else 'STAGE-ONLY')}")
    print(f"  Model:            {MODEL}")
    print(f"{'='*60}\n")

    if skipped_web:
        print("Skipped (web pages, use ingest_chain_from_url.py instead):")
        for s in skipped_web:
            print(f"  - {s}")
        print()

    if skipped_deep:
        print(f"Skipped (already >= {SKIP_THRESHOLD} items):")
        for s in skipped_deep:
            print(f"  - {s}")
        print()

    if not eligible:
        print("Nothing to process.")
        return 0

    # List eligible
    print("Eligible for processing:")
    for i, e in enumerate(eligible, 1):
        cm = f"{e['chain_key']}::{e['market']}"
        existing = e["existing_items"]
        print(f"  {i}. {cm:30s}  existing={existing:3d}  {e['pdf_url']}")
    print()

    if args.dry_run:
        print("DRY RUN complete. Use --commit or remove --dry-run to process.")
        return 0

    # Process sequentially
    total_cost = 0.0
    results: List[Dict[str, Any]] = []

    for i, entry in enumerate(eligible, 1):
        chain_key = entry["chain_key"]
        market = entry["market"]
        pdf_url = entry["pdf_url"]
        chain_market = f"{chain_key}::{market}"

        print(f"\n[{i}/{len(eligible)}] Processing {chain_market}")
        print(f"  URL: {pdf_url}")

        # Cost guard
        if total_cost >= args.max_cost:
            print(f"\n  BUDGET EXCEEDED: ${total_cost:.2f} >= ${args.max_cost:.2f}")
            print(f"  Stopping. {len(eligible) - i + 1} chains remaining.")
            results.append({
                "chain_market": chain_market,
                "status": "budget_exceeded",
                "items": 0,
                "cost": 0.0,
                "errors": [f"Budget ${args.max_cost:.2f} exceeded"],
            })
            # Mark remaining as skipped
            for remaining in eligible[i:]:
                rm = f"{remaining['chain_key']}::{remaining['market']}"
                results.append({
                    "chain_market": rm,
                    "status": "budget_skipped",
                    "items": 0,
                    "cost": 0.0,
                    "errors": [],
                })
            break

        try:
            status, item_count, cost, errors = _process_one(
                chain_key, market, pdf_url, args.commit
            )
            # Estimate cost from a rough heuristic since usage_metadata is
            # printed but not returned. Approximate: ~2000 input tokens per
            # PDF page (avg 5 pages) + ~500 output tokens per item.
            estimated_cost = _estimate_cost(10_000, max(item_count * 500, 1000))
            total_cost += estimated_cost

            results.append({
                "chain_market": chain_market,
                "status": status,
                "items": item_count,
                "cost": estimated_cost,
                "errors": errors,
            })

            if errors:
                for err in errors:
                    print(f"  WARNING: {err}")

            print(f"  Result: {status} ({item_count} items, "
                  f"~${estimated_cost:.3f}, cumulative ~${total_cost:.3f})")

        except Exception as e:
            print(f"  FATAL ERROR: {e}")
            results.append({
                "chain_market": chain_market,
                "status": "error",
                "items": 0,
                "cost": 0.0,
                "errors": [str(e)],
            })

        # Rate limit delay (skip after last item)
        if i < len(eligible):
            print(f"  Waiting {RATE_LIMIT_DELAY}s (rate limit)...")
            time.sleep(RATE_LIMIT_DELAY)

    # Final summary
    print(f"\n{'='*60}")
    print(f"  BATCH COMPLETE")
    print(f"{'='*60}")
    ok_count = sum(1 for r in results if r["status"] == "ok")
    fail_count = sum(1 for r in results if r["status"] not in ("ok", "budget_skipped"))
    skip_count = sum(1 for r in results if r["status"] == "budget_skipped")
    total_items = sum(r["items"] for r in results)

    print(f"  Succeeded:   {ok_count}")
    print(f"  Failed:      {fail_count}")
    print(f"  Skipped:     {skip_count}")
    print(f"  Total items: {total_items}")
    print(f"  Est. cost:   ${total_cost:.3f}")
    print()

    # Detail table
    print(f"  {'Chain::Market':<30s} {'Status':<20s} {'Items':>6s} {'Cost':>8s}")
    print(f"  {'-'*30} {'-'*20} {'-'*6} {'-'*8}")
    for r in results:
        print(f"  {r['chain_market']:<30s} {r['status']:<20s} "
              f"{r['items']:>6d} ${r['cost']:>7.3f}")
        if r["errors"]:
            for err in r["errors"]:
                print(f"    ^ {err}")

    print()
    return 1 if fail_count > 0 and ok_count == 0 else 0


if __name__ == "__main__":
    sys.exit(main())

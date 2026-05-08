"""Deterministic PDF ingestion — thin CLI around pdfplumber-based table extract.

Sister to ingest_chain_from_url.py for chains where you already have the
official nutrition PDF (or PDF URL) in hand. Extraction is fully deterministic
via pdfplumber.extract_tables() with multi-page header stitching. No LLM in
the path.

Usage:
    python3 tools/ingest_chain_from_pdf.py \\
        --chain pizza_hut --market TH \\
        --pdf-path ~/Downloads/pizzahut_th_nutrition.pdf \\
        --source-url https://www.pizzahut.co.th/nutrition.pdf

    # Remote PDF (downloaded to data/chain_pdfs/ then parsed)
    python3 tools/ingest_chain_from_pdf.py \\
        --chain mcdonalds --market US \\
        --pdf-url https://www.mcdonalds.com/.../Nutrition.pdf

Image-only PDFs (no extractable text/tables) are staged with zero items and
exit code 4 — no OCR in v1. The shared helpers come from ingest_chain_from_url.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from ingest_chain_from_url import (  # noqa: E402
    INGESTED_PATH,
    download_pdf_to_cache,
    extract_items_from_pdf_path,
    normalize_item,
    validate_items,
    write_staging,
    write_with_backup,
)

EXTRACTOR_VERSION = "deterministic_pdf_v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", required=True, help="chain_key e.g. pizza_hut")
    parser.add_argument("--market", required=True, help="market_tag e.g. TH")
    parser.add_argument("--pdf-path", help="Local PDF path")
    parser.add_argument("--pdf-url", help="Remote PDF URL (downloaded then parsed)")
    parser.add_argument("--source-url",
                        help="Persisted as each item's source_url. Defaults to "
                             "--pdf-url, else 'pdf://{filename}' if local-only.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stage-only", action="store_true",
                        help="Default. Use --commit to promote.")
    parser.add_argument("--commit", action="store_true",
                        help="Skip staging and write directly to chain_menu_ingested.json")
    args = parser.parse_args()

    if not args.pdf_path and not args.pdf_url:
        print("ERROR: provide --pdf-path or --pdf-url", file=sys.stderr)
        return 1

    chain_key = args.chain.lower()
    market = args.market.upper()
    chain_market = f"{chain_key}::{market}"
    ingest_run_id = uuid.uuid4().hex[:12]

    print(f"\n=== INGEST {chain_market} (PDF, deterministic) ===")
    print(f"run_id: {ingest_run_id}")

    # Resolve PDF path
    if args.pdf_url:
        print(f"\n[1/4] Downloading PDF from {args.pdf_url}")
        try:
            pdf_path = download_pdf_to_cache(args.pdf_url)
        except Exception as e:
            print(f"ERROR: PDF download failed: {e}", file=sys.stderr)
            return 1
        print(f"      saved to {pdf_path}")
    else:
        pdf_path = os.path.expanduser(args.pdf_path)
        if not os.path.exists(pdf_path):
            print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
            return 1
        print(f"\n[1/4] Using local PDF: {pdf_path}")
    pdf_size = os.path.getsize(pdf_path)
    pdf_hash = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]
    print(f"      size={pdf_size:,} bytes  sha256={pdf_hash}")

    source_url = (args.source_url or args.pdf_url
                  or f"pdf://{os.path.basename(pdf_path)}").strip()

    print(f"\n[2/4] Parsing PDF tables (pdfplumber)...")
    t0 = time.time()
    rows = extract_items_from_pdf_path(pdf_path, source_url)
    print(f"      rows={len(rows)}  elapsed={time.time()-t0:.1f}s")

    if not rows:
        # Likely image-only PDF or layout we can't parse
        staging_path = write_staging(chain_key, market, [], [{
            "reason": "no_rows_extracted",
            "detail": ("Probable image-only PDF or unparseable layout — "
                       "no tables matched the header schema. "
                       "Check pdfplumber.extract_tables() output manually."),
        }])
        print(f"\n[4/4] No rows extracted; staged at: {staging_path}")
        return 4

    items = [
        normalize_item(
            row.__dict__, chain_key, market, source_url, ingest_run_id, pdf_hash,
            confidence=0.97,
            extraction_method="pdf_table_extract",
            parse_method=row.parse_method or "pdf_table",
            extractor_version=EXTRACTOR_VERSION,
        )
        for row in rows
    ]

    print(f"\n[3/4] Validating with audit rules...")
    passing, failures = validate_items(items, chain_market)
    print(f"      passing={len(passing)}  blocking_failures={len(failures)}")

    if failures:
        staging_path = write_staging(chain_key, market, items, failures)
        print(f"\n[4/4] Validation failures — staged at: {staging_path}")
        print(f"      {len(passing)} passed, {len(failures)} blocked.")
        return 2

    if args.dry_run:
        print(f"\n[4/4] DRY RUN — would write {len(passing)} items to {chain_market}")
        for it in passing[:5]:
            print(f"       - {it['item_name']}  ({it['estimated_calories']} kcal, "
                  f"{it['estimated_protein_g']}g P, {it['diet_type']})")
        return 0

    if args.commit:
        if not passing:
            with open(INGESTED_PATH) as _fh:
                import json
                _store = json.load(_fh)
            _existing = _store.get("chains", {}).get(chain_market, [])
            if isinstance(_existing, list) and _existing:
                staging_path = write_staging(chain_key, market, [], failures)
                print(f"\n[4/4] EMPTY — refusing to overwrite {len(_existing)} existing items")
                print(f"      Empty payload staged at: {staging_path}")
                return 3
        backup_path = write_with_backup(chain_key, market, passing)
        print(f"\n[4/4] COMMITTED {len(passing)} items to {chain_market}")
        print(f"      backup: {backup_path}")
        return 0

    # Default: stage-only
    path = write_staging(chain_key, market, passing, [])
    print(f"\n[4/4] Wrote {len(passing)} validated items to staging: {path}")
    print(f"      Review then commit with: --commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())

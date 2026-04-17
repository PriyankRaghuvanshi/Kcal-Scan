"""Hand-curation pipeline — extract chain menu items from a nutrition PDF.

Sister tool to ingest_chain_from_url.py for chains that don't publish
nutrition data on the web (regional Indian chains, vegan boutique chains,
small UK/AU brands). Workflow:

  1. Download the chain's official nutrition PDF (search "{chain} nutrition pdf"
     or check the brand's allergen / footer links).
  2. Save to /tmp or ~/Downloads with a clear name.
  3. Run this tool — Gemini 2.5 Pro reads the PDF natively (text + tables).
  4. Validator gates the output exactly like the URL pipeline.
  5. Stage by default; --commit promotes to live.

Usage:
    export GEMINI_API_KEY=AIza...
    python3 tools/ingest_chain_from_pdf.py \\
        --chain sangeetha --market IN \\
        --pdf-path ~/Downloads/sangeetha_nutrition_2025.pdf \\
        --source-url https://www.sangeethaveg.com/nutrition.pdf

    # Remote PDF (downloaded then uploaded to Gemini)
    python3 tools/ingest_chain_from_pdf.py \\
        --chain wendys --market AU \\
        --pdf-url https://www.wendys.com.au/nutrition.pdf
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

# Reuse helpers from the URL-based pipeline so behavior stays consistent.
from ingest_chain_from_url import (  # noqa: E402
    EXTRACTION_PROMPT,
    MAX_RETRIES,
    REPAIR_PROMPT_PREFIX,
    normalize_item,
    parse_json_array,
    validate_items,
    write_staging,
    write_with_backup,
)

EXTRACTOR_VERSION = "gemini_pdf_v1"
MODEL = "gemini-2.5-flash"  # switched from pro to flash — 10x cheaper
PDF_DIR = os.path.join(REPO_ROOT, "data", "chain_pdfs")


def _download_pdf(url: str) -> str:
    """Fetch a remote PDF to data/chain_pdfs/ and return the local path."""
    import requests
    os.makedirs(PDF_DIR, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KcalApp-PdfIngest/1.0)",
        "Accept": "application/pdf,*/*",
    }
    resp = requests.get(url, headers=headers, timeout=60, stream=True)
    resp.raise_for_status()
    fname = hashlib.sha256(url.encode()).hexdigest()[:16] + ".pdf"
    path = os.path.join(PDF_DIR, fname)
    with open(path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)
    return path


def call_gemini_with_pdf(prompt: str, pdf_path: str) -> str:
    """Send a PDF inline to Gemini 2.5 Pro and return the text response."""
    from google import genai
    from google.genai import types
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)

    pdf_bytes = Path(pdf_path).read_bytes()
    if not pdf_bytes:
        raise RuntimeError(f"PDF is empty: {pdf_path}")

    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    response = client.models.generate_content(
        model=MODEL,
        contents=[pdf_part, prompt],
        config=types.GenerateContentConfig(temperature=0.1),
    )
    text = str(getattr(response, "text", "") or "").strip()
    try:
        u = response.usage_metadata
        print(f"      usage: prompt={u.prompt_token_count} "
              f"candidates={u.candidates_token_count} total={u.total_token_count}")
    except Exception:
        pass
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", required=True, help="chain_key e.g. sangeetha")
    parser.add_argument("--market", required=True, help="market_tag e.g. IN")
    parser.add_argument("--pdf-path", help="Local PDF path")
    parser.add_argument("--pdf-url", help="Remote PDF URL (downloaded then uploaded)")
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

    print(f"\n=== INGEST {chain_market} (PDF) ===")
    print(f"run_id: {ingest_run_id}")

    # Resolve PDF path (download if needed)
    if args.pdf_url:
        print(f"\n[1/4] Downloading PDF from {args.pdf_url}")
        pdf_path = _download_pdf(args.pdf_url)
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

    # source_url that gets persisted on each item
    source_url = (args.source_url or args.pdf_url or
                  f"pdf://{os.path.basename(pdf_path)}").strip()

    # Build the extraction prompt (same as URL-based, but with a PDF-specific hint)
    prompt = EXTRACTION_PROMPT.format(
        chain_key=chain_key, market=market, url=source_url
    ) + "\n\nNOTE: You have been given DIRECT ACCESS to the chain's official " \
        "nutrition PDF as your source. Extract menu items with macros directly " \
        "from the PDF — do NOT use Google Search; the PDF IS the source of truth."

    print(f"\n[2/4] Calling {MODEL} with PDF input...")
    t0 = time.time()
    raw_text = call_gemini_with_pdf(prompt, pdf_path)
    print(f"      response_chars={len(raw_text)}  elapsed={time.time()-t0:.1f}s")

    raw_items = parse_json_array(raw_text)
    print(f"      extracted={len(raw_items)} candidate items")

    items = [normalize_item(r, chain_key, market, source_url, ingest_run_id, pdf_hash)
             for r in raw_items]
    # Override extractor_version + extraction_method for traceability
    for it in items:
        it["extractor_version"] = EXTRACTOR_VERSION
        it["extraction_method"] = "pdf_upload"
        it["parse_method"] = "llm_pdf"

    print(f"\n[3/4] Validating with audit rules...")
    passing, failures = validate_items(items, chain_market)
    print(f"      passing={len(passing)}  blocking_failures={len(failures)}")

    retries = 0
    while failures and retries < MAX_RETRIES:
        retries += 1
        print(f"\n[3.{retries}/4] Repair pass {retries}/{MAX_RETRIES}...")
        import json as _json
        repair_prompt = REPAIR_PROMPT_PREFIX.format(
            failures=_json.dumps(failures, indent=2)
        ) + "\n\nOriginal extraction:\n" + raw_text
        try:
            repair_text = call_gemini_with_pdf(repair_prompt, pdf_path)
            raw_items = parse_json_array(repair_text)
            items = [normalize_item(r, chain_key, market, source_url, ingest_run_id, pdf_hash)
                     for r in raw_items]
            for it in items:
                it["extractor_version"] = EXTRACTOR_VERSION
                it["extraction_method"] = "pdf_upload"
                it["parse_method"] = "llm_pdf"
            passing, failures = validate_items(items, chain_market)
            print(f"        after repair: passing={len(passing)}  blocking_failures={len(failures)}")
            raw_text = repair_text
        except Exception as e:
            print(f"        repair pass failed: {e}")
            break

    if failures:
        staging_path = write_staging(chain_key, market, items, failures)
        print(f"\n[4/4] STILL FAILING after {retries} retries.")
        print(f"      Wrote {len(failures)} failures to: {staging_path}")
        return 2

    if args.dry_run:
        print(f"\n[4/4] DRY RUN — would write {len(passing)} items to {chain_market}")
        for it in passing[:5]:
            print(f"       - {it['item_name']}  ({it['estimated_calories']} kcal, "
                  f"{it['estimated_protein_g']}g P, {it['diet_type']})")
        return 0

    if args.commit:
        backup_path = write_with_backup(chain_key, market, passing)
        print(f"\n[4/4] ✅ COMMITTED {len(passing)} items to {chain_market}")
        print(f"      backup: {backup_path}")
        return 0

    # Default = stage-only
    path = write_staging(chain_key, market, passing, [])
    print(f"\n[4/4] Wrote {len(passing)} validated items to staging: {path}")
    print(f"      Review then commit with: --commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())

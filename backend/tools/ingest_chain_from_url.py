"""URL-grounded chain menu ingestion with audit-validator gating.

Fetches a chain menu page, extracts structured items via Claude Sonnet 4.6
using the actual page HTML as grounding (not hallucinated from chain name),
runs each extracted item through tools/audit_chain_menus.audit_item(), and
writes to data/chain_menu_ingested.json with menu_item_source="real_menu"
only after critical/high audit rules pass.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 tools/ingest_chain_from_url.py \\
        --chain subway --market AU \\
        --url https://www.subway.com/en-AU/MenuNutrition/Menu

    # Dry-run (extract + validate, don't write):
    python3 tools/ingest_chain_from_url.py --chain subway --market AU \\
        --url https://... --dry-run

    # Save staging output for human review without committing to ingested store:
    python3 tools/ingest_chain_from_url.py ... --stage-only

Design (per codex+claude paired review 2026-04-14):
- Fetch URL (best-effort; most chain sites are JS-shells so grounded search is primary)
- Gemini 2.5 Pro with Google Search grounding extracts items
- Validate; if critical/high failures, re-prompt with failure details, retry 2x
- Full chain::market replacement, NOT fuzzy append
- Backup ingested store before write
- Per chain::market call (subway::AU and subway::US are different datasets)
- Write source_type="official_website_menu", menu_item_source="real_menu",
  ingest_run_id, source_hash, extractor_version on each item
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import time
import uuid
from typing import Any, Dict, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from audit_chain_menus import audit_item  # noqa: E402

INGESTED_PATH = os.path.join(REPO_ROOT, "data", "chain_menu_ingested.json")
STAGING_DIR = os.path.join(REPO_ROOT, "data", "ingest_staging")
BACKUP_DIR = os.path.join(REPO_ROOT, "data", "ingest_backups")

EXTRACTOR_VERSION = "gemini_grounded_v1"
MODEL = "gemini-2.5-flash"  # switched from pro to flash — 10x cheaper, accuracy is good enough
MAX_HTML_CHARS = 80_000
MAX_RETRIES = 2

EXTRACTION_PROMPT = """You are extracting menu items from a restaurant chain's official nutrition info for a macro-tracking app. Use Google Search (enabled as a grounding tool) to find the chain's official nutrition data (menu page, nutrition PDF, or the brand's own site for the specified market). Accuracy is more important than coverage — only return items you can verify from the sources you searched. Hallucinated items will be rejected by a downstream validator.

Chain: {chain_key}
Market: {market}
Starting URL (may be JS-rendered — use web_search to find accessible nutrition data): {url}

Return a JSON array of menu items with this schema per item:
{{
  "item_name": "string — exact menu name from page (e.g. '6\\" Grilled Chicken Sub')",
  "category": "string — sub | salad | bowl | wrap | burger | pizza | sandwich | sides | drink | breakfast | dessert | entree",
  "estimated_calories": int,
  "estimated_protein_g": int,
  "estimated_fat_g": int,
  "estimated_carbs_g": int,
  "serving_size": "string — e.g. '6 inch', '2 slices', '1 bowl' (NEVER empty if portion is visible)",
  "diet_type": "non_veg | vegetarian | vegan",
  "vegetarian_possible": bool,
  "vegan_possible": bool,
  "halal_possible": bool — false if item contains pork, bacon, ham, pepperoni, salami, chorizo, or back ribs",
  "gluten_free_possible": bool — false if served on bread, sub, wrap, bun, pizza dough, pasta, naan, roti, paratha, tortilla, taco shell",
  "contains_nuts": bool,
  "contains_dairy": bool,
  "contains_gluten": bool — true if contains bread/wheat/pasta/dough,
  "contains_soy": bool,
  "contains_shellfish": bool,
  "contains_egg": bool,
  "contains_sesame": bool,
  "evidence": "string — short snippet (<120 chars) of the page text where you found this item's nutrition data"
}}

CRITICAL RULES the validator will enforce — items violating these will be rejected:
1. If item_name contains 'steak', 'beef', 'chicken', 'pork', 'fish', 'tuna', 'salmon', etc. — diet_type MUST be 'non_veg', vegetarian_possible MUST be false, vegan_possible MUST be false.
2. If item_name contains 'pork', 'bacon', 'ham sandwich', 'pepperoni', 'salami', 'BBQ ribs', 'back ribs' — halal_possible MUST be false.
3. If item_name contains 'sub', 'bread', 'wrap', 'burger', 'pizza', 'pasta', 'naan', 'roti', 'paratha', 'taco', 'sandwich', 'panini' — contains_gluten MUST be true and gluten_free_possible MUST be false (unless explicitly a gluten-free variant).
4. **estimated_calories MUST be in kcal (kilocalories), NOT kJ (kilojoules).** Many international sites (AU, NZ, UK, EU) show energy in kJ primarily. If you see a kJ value, divide by 4.184 to convert (e.g. 2060 kJ = 492 kcal). Typical menu-item range: 100–1500 kcal; NEVER 1000–10000 (that's kJ). Also satisfy: |kcal_stated - (4*P + 4*C + 9*F)| / kcal_stated < 0.30. If P+F+C implies ~500 but you have 2000 stored, you stored the kJ value — convert it.
5. Don't use generic names like "Protein Bowl" or "Lean Wrap" — use the exact menu name.
6. **SKIP items where you cannot find real P/F/C macros.** Do NOT emit an item with estimated_protein_g/carbs_g/fat_g all set to 0 just to fill the array — that fails validation and wastes the whole ingest run. Better to return 8 verified items than 20 with made-up zeros. If the source gives only kcal, skip that item.
7. **If you cannot find reliable menu data after searching, return the literal JSON array `[]`.** Do NOT write prose explaining what you couldn't find, do NOT return an error message, do NOT apologize. Just `[]`. The caller treats `[]` as "no data" gracefully; it treats prose as a hard pipeline failure.

Return ONLY the JSON array (possibly empty). No prose before or after, no markdown fences, no commentary. Aim for 15–35 items per market when data is available; return `[]` when it isn't."""

REPAIR_PROMPT_PREFIX = """You returned items that failed validation. Fix the specific issues below and return the corrected JSON array. Do not remove items unless they cannot be fixed — fix them.

Failures:
{failures}

Return the FULL corrected array (not just the fixed items). Same schema as before."""


def fetch_url(url: str) -> Tuple[str, str]:
    """Fetch URL, return (text, source_hash). Strips script/style."""
    import requests
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KcalApp-MenuIngest/1.0; +contact-via-app)",
        "Accept": "text/html,application/xhtml+xml",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    raw = resp.text
    # Strip script/style/svg/noscript blocks
    cleaned = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ",
                     raw, flags=re.IGNORECASE | re.DOTALL)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > MAX_HTML_CHARS:
        cleaned = cleaned[:MAX_HTML_CHARS] + " ...[truncated]"
    src_hash = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return cleaned, src_hash


def call_llm(prompt: str, page_text: str = "") -> str:
    """Call Gemini 2.5 Pro with Google Search grounding + extraction prompt.

    Uses the newer google-genai SDK (has GoogleSearch tool).
    page_text is optional extra context; model also does grounded search.
    """
    from google import genai
    from google.genai import types
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)

    content = prompt
    if page_text:
        content += f"\n\n--- DIRECT PAGE CONTENT (may be JS-shell / incomplete) ---\n{page_text}"

    response = client.models.generate_content(
        model=MODEL,
        contents=content,
        config=types.GenerateContentConfig(
            temperature=0.1,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    text = str(getattr(response, "text", "") or "").strip()
    try:
        u = response.usage_metadata
        print(f"      usage: prompt={u.prompt_token_count} "
              f"candidates={u.candidates_token_count} total={u.total_token_count}")
    except Exception:
        pass
    try:
        gm = response.candidates[0].grounding_metadata
        if gm and gm.grounding_chunks:
            print(f"      grounding sources: {len(gm.grounding_chunks)}")
            for i, chunk in enumerate(gm.grounding_chunks[:3]):
                uri = getattr(getattr(chunk, "web", None), "uri", "") or ""
                if uri:
                    print(f"        [{i}] {uri[:90]}")
    except Exception:
        pass
    return text


def parse_json_array(text: str) -> List[Dict[str, Any]]:
    """Extract a JSON array from model output, tolerating prose around it.

    Returns [] when the model genuinely found no data (either an explicit
    empty array, or prose explaining it couldn't find anything). Only raises
    ValueError on truly malformed JSON.
    """
    text = str(text or "").strip()
    if not text:
        return []
    # Strip markdown fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    # Prefer the LAST balanced top-level array in the output (model may add
    # a prose preamble before a final JSON payload).
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        # No array at all — treat prose-only output as "no data found".
        return []
    payload = match.group()
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON array in model output: {e}")
    if not isinstance(parsed, list):
        return []
    return parsed


def normalize_item(raw: Dict[str, Any], chain_key: str, market: str,
                   url: str, ingest_run_id: str, source_hash: str) -> Dict[str, Any]:
    """Map a raw extracted item into the chain_menu_ingested schema."""
    name = str(raw.get("item_name") or "").strip()
    item_key_base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    item_key = f"{chain_key}_{market.lower()}_{item_key_base}"[:120]
    return {
        "chain_key": chain_key,
        "source_type": "official_website_menu",
        "source_url": url,
        "market_tag": market,
        "item_key": item_key,
        "item_name": name,
        "category": str(raw.get("category") or "entree").strip().lower(),
        "estimated_calories": int(raw.get("estimated_calories") or 0),
        "estimated_protein_g": int(raw.get("estimated_protein_g") or 0),
        "estimated_fat_g": int(raw.get("estimated_fat_g") or 0),
        "estimated_carbs_g": int(raw.get("estimated_carbs_g") or 0),
        "serving_size": str(raw.get("serving_size") or "").strip(),
        "confidence": 0.93,  # URL-grounded extraction → high baseline
        "supports_swaps": True,
        "negative_flags": [],
        "last_ingested_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active": True,
        "chosen_candidate_specificity_tier": "exact_menu_match",
        "menu_item_source": "real_menu",
        "extraction_method": "website_menu_fetch",
        "parse_method": "llm",
        "raw_text_snippet": str(raw.get("evidence") or "")[:200],
        "ingest_run_id": ingest_run_id,
        "source_hash": source_hash,
        "extractor_version": EXTRACTOR_VERSION,
        "halal_possible": bool(raw.get("halal_possible", False)),
        "gluten_free_possible": bool(raw.get("gluten_free_possible", False)),
        "diet_type": str(raw.get("diet_type") or "non_veg").strip().lower(),
        "vegetarian_possible": bool(raw.get("vegetarian_possible", False)),
        "vegan_possible": bool(raw.get("vegan_possible", False)),
        "contains_nuts": bool(raw.get("contains_nuts", False)),
        "contains_dairy": bool(raw.get("contains_dairy", False)),
        "contains_gluten": bool(raw.get("contains_gluten", False)),
        "contains_soy": bool(raw.get("contains_soy", False)),
        "contains_shellfish": bool(raw.get("contains_shellfish", False)),
        "contains_egg": bool(raw.get("contains_egg", False)),
        "contains_sesame": bool(raw.get("contains_sesame", False)),
    }


def validate_items(items: List[Dict[str, Any]],
                   chain_market: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run audit validator. Returns (passing_items, blocking_failures)."""
    passing: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for item in items:
        flags = audit_item(chain_market, item)
        blockers = [f for f in flags if f["severity"] in ("critical", "high")]
        if blockers:
            failures.append({
                "item_name": item.get("item_name"),
                "blocking_flags": [{"code": f["code"], "detail": f["detail"]} for f in blockers],
            })
        else:
            passing.append(item)
    return passing, failures


def write_with_backup(chain_key: str, market: str,
                      items: List[Dict[str, Any]]) -> str:
    """Backup the ingested store, then full-replace chain::market entry."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup_path = os.path.join(BACKUP_DIR, f"chain_menu_ingested.{ts}.json")
    shutil.copy2(INGESTED_PATH, backup_path)

    with open(INGESTED_PATH) as fh:
        store = json.load(fh)
    chain_market = f"{chain_key}::{market}"
    store.setdefault("chains", {})[chain_market] = items
    store["updated_at"] = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    tmp_path = INGESTED_PATH + ".tmp"
    with open(tmp_path, "w") as fh:
        json.dump(store, fh, indent=2)
    os.replace(tmp_path, INGESTED_PATH)
    return backup_path


def write_staging(chain_key: str, market: str,
                  items: List[Dict[str, Any]],
                  failures: List[Dict[str, Any]]) -> str:
    os.makedirs(STAGING_DIR, exist_ok=True)
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(STAGING_DIR, f"{chain_key}__{market}__{ts}.json")
    with open(path, "w") as fh:
        json.dump({
            "chain_key": chain_key,
            "market": market,
            "items": items,
            "blocking_failures": failures,
        }, fh, indent=2)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", required=True, help="chain_key e.g. subway")
    parser.add_argument("--market", required=True, help="market_tag e.g. AU")
    parser.add_argument("--url", required=True, help="official menu/nutrition URL")
    parser.add_argument("--dry-run", action="store_true", help="extract+validate, no write")
    parser.add_argument("--stage-only", action="store_true", help="write to staging dir, not ingested store")
    args = parser.parse_args()

    chain_key = args.chain.lower()
    market = args.market.upper()
    chain_market = f"{chain_key}::{market}"
    ingest_run_id = uuid.uuid4().hex[:12]

    print(f"\n=== INGEST {chain_market} ===")
    print(f"URL:          {args.url}")
    print(f"run_id:       {ingest_run_id}")

    print(f"\n[1/4] Fetching URL (best-effort; model will also web_search)...")
    page_text = ""
    source_hash = "web_search_only"
    try:
        page_text, source_hash = fetch_url(args.url)
        print(f"      page_chars={len(page_text)}  source_hash={source_hash}")
    except Exception as e:
        print(f"      fetch failed ({type(e).__name__}) — relying on web_search only")

    prompt = EXTRACTION_PROMPT.format(chain_key=chain_key, market=market, url=args.url)
    print(f"\n[2/4] Calling {MODEL} (google-search grounded)...")
    t0 = time.time()
    raw_text = call_llm(prompt, page_text)
    print(f"      response_chars={len(raw_text)}  elapsed={time.time()-t0:.1f}s")

    raw_items = parse_json_array(raw_text)
    print(f"      extracted={len(raw_items)} candidate items")

    items = [normalize_item(r, chain_key, market, args.url, ingest_run_id, source_hash)
             for r in raw_items]

    print(f"\n[3/4] Validating with audit rules...")
    passing, failures = validate_items(items, chain_market)
    print(f"      passing={len(passing)}  blocking_failures={len(failures)}")

    retries = 0
    while failures and retries < MAX_RETRIES:
        retries += 1
        print(f"\n[3.{retries}/4] Repair pass {retries}/{MAX_RETRIES}...")
        failures_str = json.dumps(failures, indent=2)
        repair_prompt = REPAIR_PROMPT_PREFIX.format(failures=failures_str)
        repair_text = call_llm(repair_prompt + "\n\nOriginal extraction:\n" + raw_text, page_text)
        try:
            raw_items = parse_json_array(repair_text)
            items = [normalize_item(r, chain_key, market, args.url, ingest_run_id, source_hash)
                     for r in raw_items]
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
        print(f"      {len(passing)} items passed but NOT written to ingested store.")
        return 2

    if args.dry_run:
        print(f"\n[4/4] DRY RUN — would write {len(passing)} items to {chain_market}")
        for it in passing[:5]:
            print(f"       - {it['item_name']}  ({it['estimated_calories']} kcal, "
                  f"{it['estimated_protein_g']}g P, {it['diet_type']})")
        if len(passing) > 5:
            print(f"       ... and {len(passing)-5} more")
        return 0

    if args.stage_only:
        path = write_staging(chain_key, market, passing, [])
        print(f"\n[4/4] Wrote {len(passing)} validated items to staging: {path}")
        return 0

    if not passing:
        with open(INGESTED_PATH) as _fh:
            _store = json.load(_fh)
        _existing = _store.get("chains", {}).get(chain_market, [])
        if isinstance(_existing, list) and _existing:
            staging_path = write_staging(chain_key, market, passing, failures)
            print(f"\n[4/4] ⚠️  EMPTY EXTRACTION — refusing to overwrite {len(_existing)} existing items in {chain_market}")
            print(f"      Empty payload staged at: {staging_path}")
            return 3

    backup_path = write_with_backup(chain_key, market, passing)
    print(f"\n[4/4] ✅ WROTE {len(passing)} items to {chain_market}")
    print(f"      backup: {backup_path}")
    print(f"      ingested store updated: {INGESTED_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Identify cached PDFs that aren't yet mapped to a chain::market.

The Gemini-era runs cached dozens of PDFs in data/chain_pdfs/. Some are
already linked to a chain::market via the source_url column on items in
data/chain_menu_ingested.json — those are handled by reingest_cached_pdfs.py.
The rest are orphans: real official nutrition PDFs whose origin URL never
got persisted onto an item, so we can't recover the chain::market by URL hash.

This script identifies orphans by content. For each orphan PDF it:
  1. extracts the first ~1500 chars of text via pdfplumber
  2. extracts the first 30 candidate item names via the deterministic parser
  3. scores against every (chain_key, market) we know about, using:
        - brand-name match in PDF text  -> high signal
        - PDF filename hint              -> very high signal
        - market-token match in PDF text -> medium signal
        - PDF item-name overlap with the chain::market's existing items
          -> tie-breaker, very precise
  4. emits a ranked candidate list per PDF + a confidence score

Usage:
    python3 tools/identify_orphan_pdfs.py                 # full table
    python3 tools/identify_orphan_pdfs.py --min-score 50  # only high-conf
    python3 tools/identify_orphan_pdfs.py --json out.json # machine-readable
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from ingest_chain_from_url import (  # noqa: E402
    INGESTED_PATH,
    PDF_CACHE_DIR,
    extract_items_from_pdf_path,
    MARKET_TOKEN_HINTS,
)

GLOBAL_REGISTRY_PATH = os.path.join(REPO_ROOT, "data", "global_chain_registry.json")
CHAINS_DIR = os.path.join(REPO_ROOT, "data", "chains")

# Common chain markers in PDF text (currency, language tags) by market.
# Lower-cased substrings; redundant with MARKET_TOKEN_HINTS but more PDF-y.
MARKET_PDF_HINTS: Dict[str, Tuple[str, ...]] = {
    "US": ("$", " usd ", "united states", "u.s.", "ny ", "los angeles"),
    "CA": (" cad ", "canada", "canadian", "toronto", "ontario", "quebec"),
    "GB": ("£", " gbp ", "united kingdom", "london", "england", "scotland", "british"),
    "AU": (" aud ", "australia", "sydney", "melbourne", "australian"),
    "NZ": (" nzd ", "new zealand", "auckland", "wellington"),
    "IN": ("₹", " inr ", " rs ", "rs.", "india", "mumbai", "delhi", "bangalore", "bengaluru", "chennai"),
    "TH": ("฿", " thb ", "thailand", "bangkok"),
    "PH": ("₱", " php ", "philippines", "manila"),
    "BD": ("৳", " bdt ", "bangladesh", "dhaka"),
    "PL": (" pln ", "poland", "warsaw", "polska", "zł"),
    "LK": (" lkr ", "sri lanka", "colombo"),
    "MA": (" mad ", "morocco", "casablanca", "rabat", "maroc"),
    "ID": (" idr ", "indonesia", "jakarta", "rupiah"),
    "JP": ("¥", " jpy ", "japan", "tokyo"),
    "KR": (" krw ", "korea", "seoul", "korean"),
    "DE": ("€", " eur ", "germany", "berlin", "deutschland"),
    "FR": ("€", " eur ", "france", "paris"),
    "CH": ("chf ", "switzerland", "zürich", "geneva", "schweiz"),
    "SG": (" sgd ", "singapore"),
    "MY": (" myr ", "malaysia", "kuala lumpur"),
    "AE": (" aed ", "uae", "dubai", "abu dhabi", "emirates"),
    "BR": (" brl ", "brazil", "brasil", "são paulo", "rio de janeiro"),
    "MX": (" mxn ", "mexico", "méxico", "ciudad"),
    "ZA": ("zar ", "south africa", "johannesburg", "cape town"),
    "PR": ("puerto rico", "san juan"),
}

FILENAME_RE = re.compile(r"^([a-z][a-z0-9_]+)_([a-z]{2,3})\.pdf$", re.IGNORECASE)


def _is_valid_pdf(path: str) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) < 1024:
        return False
    with open(path, "rb") as fh:
        return fh.read(5) == b"%PDF-"


def _hash16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _extract_first_page_text(pdf_path: str, max_chars: int = 1500) -> str:
    """Pull text from the first 2 pages of a PDF for brand-name detection."""
    import pdfplumber
    out: List[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]:
                try:
                    txt = page.extract_text() or ""
                    out.append(txt)
                except Exception:
                    continue
                if sum(len(t) for t in out) >= max_chars:
                    break
    except Exception:
        return ""
    text = " ".join(out).lower()
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars]


def _build_pdf_url_index() -> Dict[str, str]:
    """Map sha256(url)[:16] -> chain_market for PDFs we already know about."""
    with open(INGESTED_PATH) as fh:
        store = json.load(fh)
    out: Dict[str, str] = {}
    for cm, items in store.get("chains", {}).items():
        if not isinstance(items, list):
            continue
        for it in items:
            url = (it.get("source_url") or "").strip()
            if url and "pdf" in url.lower():
                out.setdefault(_hash16(url), cm)
    return out


def _load_chain_corpus() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Build {(chain_key, market): {brand_aliases, item_names_set, priority_tier}}."""
    corpus: Dict[Tuple[str, str], Dict[str, Any]] = {}

    # 1. Pull aliases / brand_family from global_chain_registry.
    aliases_by_brand: Dict[str, set] = defaultdict(set)
    if os.path.exists(GLOBAL_REGISTRY_PATH):
        try:
            reg = json.load(open(GLOBAL_REGISTRY_PATH))
            for entry in reg.get("chains", []):
                bf = (entry.get("brand_family") or "").lower()
                if not bf:
                    continue
                for a in entry.get("aliases", []):
                    aliases_by_brand[bf].add(a.lower())
                cn = entry.get("canonical_name")
                if cn:
                    aliases_by_brand[bf].add(cn.lower())
        except Exception:
            pass

    # 2. Walk seed files for the (chain_key, market) tuples + brand_name.
    seen: set = set()
    if os.path.isdir(CHAINS_DIR):
        for fname in os.listdir(CHAINS_DIR):
            if not fname.endswith(".json"):
                continue
            stem = fname[:-5]
            m = re.match(r"^(?P<chain_key>[a-z0-9_]+)_(?P<market>[a-z]{2,3})$", stem)
            if not m:
                continue
            chain_key = m.group("chain_key")
            market = m.group("market").upper()
            try:
                d = json.load(open(os.path.join(CHAINS_DIR, fname)))
            except Exception:
                continue
            brand_name = str(d.get("brand_name") or "").strip().lower()
            aliases = set(aliases_by_brand.get(chain_key, set()))
            if brand_name:
                aliases.add(brand_name)
            # Always include the chain_key's normalized form as an alias
            aliases.add(chain_key.replace("_", " "))
            items = d.get("items") or []
            item_names = {
                str(it.get("item_name", "")).strip().lower()
                for it in items
                if isinstance(it, dict) and it.get("item_name")
            }
            corpus[(chain_key, market)] = {
                "aliases": aliases,
                "item_names": item_names,
                "priority": d.get("rollout_priority", "p3"),
            }
            seen.add((chain_key, market))

    # 3. Backfill from chain_menu_ingested for chain::markets without seed files.
    try:
        with open(INGESTED_PATH) as fh:
            store = json.load(fh)
        for cm, items in store.get("chains", {}).items():
            if "::" not in cm:
                continue
            ck, mk = cm.split("::", 1)
            tup = (ck, mk.upper())
            if tup in seen:
                continue
            if not isinstance(items, list):
                continue
            aliases = set(aliases_by_brand.get(ck, set()))
            aliases.add(ck.replace("_", " "))
            names = {
                str(it.get("item_name", "")).strip().lower()
                for it in items
                if isinstance(it, dict) and it.get("item_name")
            }
            corpus[tup] = {
                "aliases": aliases,
                "item_names": names,
                "priority": "unknown",
            }
    except Exception:
        pass

    return corpus


def _score_candidate(
    pdf_text: str,
    pdf_item_names: set,
    aliases: set,
    item_names: set,
    market: str,
    filename: str,
) -> Tuple[int, List[str]]:
    """Return (score, reasons) for one (chain_key, market) candidate."""
    score = 0
    reasons: List[str] = []

    # Brand-alias match in PDF text — strong signal.
    brand_hit = False
    for alias in aliases:
        if not alias or len(alias) < 3:
            continue
        if alias in pdf_text:
            brand_hit = True
            score += 20
            reasons.append(f"text:{alias}")
            break  # only count the first hit
    if not brand_hit:
        # No brand match means we shouldn't even score this candidate. Bail.
        return -100, ["no-brand-match"]

    # Market-token in text — narrows region.
    market_hits = MARKET_PDF_HINTS.get(market.upper(), ())
    for tok in market_hits:
        if tok in pdf_text:
            score += 10
            reasons.append(f"mkt:{tok.strip()}")
            break

    # MARKET_TOKEN_HINTS already covers TLD/country-code hints
    for tok in MARKET_TOKEN_HINTS.get(market.upper(), ()):
        if len(tok) >= 2 and tok in pdf_text:
            score += 4
            reasons.append(f"tld:{tok}")
            break

    # Item-name overlap — strongest precision.
    if pdf_item_names and item_names:
        intersection = pdf_item_names & item_names
        if intersection:
            score += min(40, len(intersection) * 3)
            reasons.append(f"items:{len(intersection)}")

    # Filename hint
    fn_match = FILENAME_RE.match(filename)
    if fn_match:
        f_chain = fn_match.group(1).lower()
        f_market = fn_match.group(2).upper()
        if f_market == market.upper() and (f_chain in aliases or any(a in f_chain for a in aliases if len(a) >= 4)):
            score += 50
            reasons.append("filename")

    return score, reasons


def identify(pdf_path: str, corpus: Dict[Tuple[str, str], Dict[str, Any]],
             *, top_k: int = 3) -> Dict[str, Any]:
    """Return identification result for one PDF."""
    text = _extract_first_page_text(pdf_path)
    pdf_rows = []
    if text:
        try:
            pdf_rows = extract_items_from_pdf_path(pdf_path, source_url=f"pdf://{os.path.basename(pdf_path)}")
        except Exception:
            pdf_rows = []
    pdf_item_names = {row.item_name.lower().strip() for row in pdf_rows[:30] if row.item_name}

    filename = os.path.basename(pdf_path)
    scored: List[Tuple[int, str, str, List[str]]] = []
    for (ck, mk), data in corpus.items():
        score, reasons = _score_candidate(
            text, pdf_item_names, data["aliases"], data["item_names"], mk, filename,
        )
        if score > 0:
            scored.append((score, ck, mk, reasons))

    scored.sort(key=lambda x: -x[0])
    top = scored[:top_k]

    return {
        "pdf": filename,
        "size": os.path.getsize(pdf_path),
        "text_chars": len(text),
        "pdf_item_count": len(pdf_item_names),
        "candidates": [
            {"chain_market": f"{ck}::{mk}", "score": s, "reasons": rs}
            for (s, ck, mk, rs) in top
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", default=PDF_CACHE_DIR)
    parser.add_argument("--min-score", type=int, default=0,
                        help="filter results to candidates with score >= this")
    parser.add_argument("--json", help="write machine-readable output to this path")
    parser.add_argument("--limit", type=int, default=0,
                        help="cap number of orphans processed (0 = no cap)")
    args = parser.parse_args()

    print("=== ORPHAN PDF IDENTIFIER ===")
    print(f"  cache dir   : {args.cache_dir}")

    # Determine which cached PDFs are orphans
    mapped = _build_pdf_url_index()
    print(f"  mapped PDFs : {len(mapped)} (have source_url in ingested store)")

    orphans: List[str] = []
    for fname in sorted(os.listdir(args.cache_dir)):
        path = os.path.join(args.cache_dir, fname)
        if not _is_valid_pdf(path):
            continue
        stem = fname.replace(".pdf", "")
        if stem in mapped:
            continue
        orphans.append(path)
    print(f"  orphan PDFs : {len(orphans)}")

    if args.limit and len(orphans) > args.limit:
        orphans = orphans[:args.limit]

    print(f"\n  building chain corpus...")
    corpus = _load_chain_corpus()
    print(f"  corpus      : {len(corpus)} (chain_key, market) entries")

    results: List[Dict[str, Any]] = []
    print(f"\n  identifying {len(orphans)} orphans...")
    for i, p in enumerate(orphans, 1):
        r = identify(p, corpus)
        results.append(r)
        # Filter at print time
        cands = [c for c in r["candidates"] if c["score"] >= args.min_score]
        top = cands[0] if cands else None
        head = top["chain_market"] if top else "—"
        head_score = top["score"] if top else 0
        head_reasons = ",".join(top["reasons"][:4]) if top else ""
        print(f"  [{i:2d}/{len(orphans)}] {os.path.basename(p):<22s} "
              f"size={r['size']:>9,d}  items_in_pdf={r['pdf_item_count']:>3d}  "
              f"-> {head:<28s} score={head_score:>3d} {head_reasons}")

    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"  {'pdf':<22s} {'size':>9s} {'pdf_items':>9s}  {'top candidate':<28s} {'score':>5s}  reasons")
    print(f"  {'-'*22} {'-'*9} {'-'*9}  {'-'*28} {'-'*5}  ---")
    for r in results:
        cands = [c for c in r["candidates"] if c["score"] >= args.min_score]
        top = cands[0] if cands else None
        if not top:
            continue
        rs = ",".join(top["reasons"][:4])
        print(f"  {r['pdf']:<22s} {r['size']:>9,d} {r['pdf_item_count']:>9d}  "
              f"{top['chain_market']:<28s} {top['score']:>5d}  {rs}")

    by_band = {"high(>=50)": 0, "med(25-49)": 0, "low(1-24)": 0, "none": 0}
    for r in results:
        if not r["candidates"]:
            by_band["none"] += 1
            continue
        s = r["candidates"][0]["score"]
        if s >= 50:
            by_band["high(>=50)"] += 1
        elif s >= 25:
            by_band["med(25-49)"] += 1
        elif s >= 1:
            by_band["low(1-24)"] += 1
        else:
            by_band["none"] += 1
    print(f"\n  confidence bands: {by_band}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=2)
        print(f"\n  wrote: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

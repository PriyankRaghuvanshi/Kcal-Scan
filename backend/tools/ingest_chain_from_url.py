"""Deterministic chain menu ingestion — crawl + HTML/PDF parse, no LLM.

Replaces the prior Gemini-grounded extraction pipeline. Crawls the chain's
official domain (same-host BFS, depth <= 2), scores candidate pages by
keyword (nutrition/allergen/menu/calories) and market token, then parses
each candidate deterministically:

    HTML tables  ->  embedded JSON-LD / __NEXT_DATA__  ->  linked PDFs

Diet/allergen flags are inferred deterministically from item names plus any
allergens column. Items missing P/F/C are skipped (not faked with zeros).
Energy in kJ is converted to kcal. Validator gate is unchanged.

Usage:
    python3 tools/ingest_chain_from_url.py \\
        --chain pizza_hut --market TH \\
        --url https://www.pizzahut.co.th/menu

    # Dry-run / staging:
    python3 tools/ingest_chain_from_url.py ... --dry-run
    python3 tools/ingest_chain_from_url.py ... --stage-only

Library budget: requests, beautifulsoup4, pdfplumber, urllib.parse — that's it.
No extruct, no pandas, no OCR, no Playwright.

Public surface (kept stable for ingest_chain_from_pdf.py / batch_pdf_ingest.py):
    normalize_item, validate_items, write_staging, write_with_backup,
    extract_items_from_html_tables, extract_items_from_embedded_json,
    extract_items_from_pdf_path, download_pdf_to_cache, infer_diet_flags,
    map_table_headers, build_row_from_cells, coerce_energy_to_kcal,
    parse_numeric_value, infer_category, SourceCandidate, ParsedMenuRow.

Legacy LLM symbols (EXTRACTION_PROMPT, REPAIR_PROMPT_PREFIX, MAX_RETRIES,
parse_json_array, MODEL) remain as deprecated stubs so cron_chain_ingest.py
and batch_pdf_ingest.py keep importing without crashing, but invoking them
prints a deprecation warning. Both legacy callers should be migrated.
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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urldefrag

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from audit_chain_menus import (  # noqa: E402
    audit_item,
    DAIRY_TOKENS as _AUDIT_DAIRY_TOKENS,
    EGG_TOKENS as _AUDIT_EGG_TOKENS,
    GLUTEN_TOKENS as _AUDIT_GLUTEN_TOKENS,
    NUT_TOKENS as _AUDIT_NUT_TOKENS,
    PORK_TOKENS as _AUDIT_PORK_TOKENS,
    SHELLFISH_TOKENS as _AUDIT_SHELLFISH_TOKENS,
    _name_has as _audit_name_has,
)

INGESTED_PATH = os.path.join(REPO_ROOT, "data", "chain_menu_ingested.json")
STAGING_DIR = os.path.join(REPO_ROOT, "data", "ingest_staging")
BACKUP_DIR = os.path.join(REPO_ROOT, "data", "ingest_backups")
PDF_CACHE_DIR = os.path.join(REPO_ROOT, "data", "chain_pdfs")

EXTRACTOR_VERSION = "deterministic_crawl_v1"

# Crawl knobs
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_PAGES = 12
DEFAULT_MAX_CANDIDATES = 20
DEFAULT_TARGET_ROWS = 25
HTTP_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; KcalApp-MenuIngest/2.0; +contact-via-app)"

REJECT_PATH_TOKENS = (
    "career", "careers", "jobs", "privacy", "terms", "franchise", "news",
    "blog", "press", "location", "store-locator", "store_locator", "contact",
    "facebook", "instagram", "tiktok", "twitter", "x.com", "youtube",
    "linkedin", "login", "signup", "cart", "checkout",
)

KEYWORD_NUTRITION = ("nutrition", "nutritional", "calories", "kcal", "energy")
KEYWORD_ALLERGEN = ("allergen", "allergy", "allergens")
KEYWORD_MENU = ("menu",)
KEYWORD_DOWNLOAD = ("download", "guide", "information", "facts", "table")

MARKET_TOKEN_HINTS: Dict[str, Tuple[str, ...]] = {
    "AU": ("au", "australia"),
    "GB": ("uk", "gb", "british", "co.uk"),
    "US": ("us", "usa", "united-states"),
    "IN": ("in", "india"),
    "TH": ("th", "thailand", "co.th"),
    "BD": ("bd", "bangladesh", "com.bd"),
    "PH": ("ph", "philippines", "com.ph"),
    "PL": ("pl", "poland", "polska"),
    "LK": ("lk", "sri-lanka", "srilanka"),
    "MA": ("ma", "morocco", "maroc"),
    "KR": ("kr", "korea", "co.kr"),
    "ID": ("id", "indonesia", "co.id"),
    "JP": ("jp", "japan", "co.jp"),
    "DE": ("de", "germany", "deutschland"),
    "FR": ("fr", "france"),
    "SG": ("sg", "singapore", "com.sg"),
    "MY": ("my", "malaysia", "com.my"),
    "AE": ("ae", "uae"),
    "BR": ("br", "brazil", "brasil", "com.br"),
    "MX": ("mx", "mexico"),
    "CA": ("ca", "canada"),
    "NZ": ("nz", "new-zealand"),
    "ZA": ("za", "south-africa", "co.za"),
}

# Header-synonym map for both HTML and PDF tables. All comparisons are
# done after lowercasing + collapsing whitespace.
HEADER_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "name": (
        "name", "item", "menu item", "product", "description", "item name",
        "menu", "products", "food", "produit", "produkt",
    ),
    "kcal": (
        "calories", "kcal", "energy (kcal)", "energy kcal", "cal",
        "calorie", "calories (kcal)", "energy/kcal",
    ),
    "kj": (
        "kj", "energy (kj)", "energy kj", "energy/kj", "kilojoules",
        "energy(kj)",
    ),
    "energy": (
        "energy",  # generic; resolves to kj if value > 1000, else kcal
    ),
    "protein": (
        "protein", "protein (g)", "proteins", "prot", "protein g",
        "protein(g)",
    ),
    "fat": (
        "fat", "total fat", "fat (g)", "fat g", "lipids", "fat(g)",
    ),
    "carbs": (
        "carbs", "carbohydrates", "carbohydrate", "carb", "carbs (g)",
        "carbohydrate (g)", "carbs g", "carb (g)", "carbohydrate g",
        "carbohydrates(g)",
    ),
    "serving": (
        "serving", "serving size", "portion", "size", "per serve",
        "serving (g)", "serve size", "weight", "pack size",
    ),
    "allergens": (
        "allergens", "contains", "allergen info", "allergen information",
    ),
}


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SourceCandidate:
    url: str
    source_type: str  # "page" | "pdf"
    score: int
    depth: int
    anchor_text: str
    discovered_from: str
    content_type: str = ""
    reasons: List[str] = field(default_factory=list)


@dataclass
class ParsedMenuRow:
    item_name: str
    estimated_calories: int
    estimated_protein_g: int
    estimated_fat_g: int
    estimated_carbs_g: int
    serving_size: str = ""
    category: str = "entree"
    evidence: str = ""
    allergens_text: str = ""
    parse_method: str = "html_table"


# ---------------------------------------------------------------------------
# Numeric / unit helpers
# ---------------------------------------------------------------------------


_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def parse_numeric_value(text: str) -> Optional[float]:
    """Pull a single numeric value out of a cell. Rejects ranges + percentages.

    Returns None for empty cells, ranges (e.g. '160-190'), or %DV columns.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    if "%" in s:
        return None
    # Reject ranges like "160-190", "12 - 15", "1,200–1,400"
    if re.search(r"\d\s*[-–—]\s*\d", s):
        return None
    matches = _NUMBER_RE.findall(s.replace(",", "."))
    if not matches:
        return None
    try:
        return float(matches[0])
    except ValueError:
        return None


def coerce_energy_to_kcal(
    energy_value: Optional[float],
    energy_unit: Optional[str],
    protein_g: Optional[float],
    fat_g: Optional[float],
    carbs_g: Optional[float],
) -> Optional[int]:
    """Resolve one energy reading to kcal.

    - explicit 'kj' header -> divide by 4.184
    - explicit 'kcal' header -> use as-is
    - generic 'energy' header -> > 1000 means kj, otherwise kcal
    - if macros imply a kcal that disagrees with the stated value by >30%
      AND value/4.184 fits macros better, treat as kj
    """
    if energy_value is None:
        return None
    unit = (energy_unit or "").strip().lower()
    macro_kcal: Optional[float] = None
    if protein_g is not None and fat_g is not None and carbs_g is not None:
        macro_kcal = 4.0 * protein_g + 9.0 * fat_g + 4.0 * carbs_g

    if unit == "kj":
        return int(round(energy_value / 4.184))
    if unit == "kcal":
        kcal = energy_value
    else:
        # generic 'energy'
        kcal = energy_value / 4.184 if energy_value > 1000 else energy_value

    if macro_kcal and macro_kcal > 50 and kcal > 0:
        diff_direct = abs(kcal - macro_kcal) / macro_kcal
        diff_as_kj = abs((energy_value / 4.184) - macro_kcal) / macro_kcal
        if diff_direct > 0.30 and diff_as_kj < diff_direct:
            kcal = energy_value / 4.184

    if kcal <= 0:
        return None
    return int(round(kcal))


def map_table_headers(headers: List[str]) -> Optional[Dict[str, int]]:
    """Map a header row to {logical_col: index}.

    Returns None unless the table has at least: name + (kcal or kj or energy)
    + protein + fat + carbs.
    """
    norm_headers = [
        re.sub(r"\s+", " ", str(h or "")).strip().lower() for h in headers
    ]
    colmap: Dict[str, int] = {}
    for idx, header in enumerate(norm_headers):
        if not header:
            continue
        for logical, synonyms in HEADER_SYNONYMS.items():
            if logical in colmap:
                continue
            if header in synonyms:
                colmap[logical] = idx
                break
        else:
            # Substring fallback for clearly-named cols (e.g. "energy (kcal)\nper serving")
            for logical, synonyms in HEADER_SYNONYMS.items():
                if logical in colmap:
                    continue
                if any(syn in header for syn in synonyms if len(syn) > 3):
                    colmap[logical] = idx
                    break

    if "name" not in colmap:
        return None
    has_energy = "kcal" in colmap or "kj" in colmap or "energy" in colmap
    if not has_energy:
        return None
    if not all(c in colmap for c in ("protein", "fat", "carbs")):
        return None
    return colmap


def build_row_from_cells(
    cells: List[str],
    colmap: Dict[str, int],
    evidence: str,
) -> Optional[ParsedMenuRow]:
    """Convert one body row into a ParsedMenuRow. Skips invalid rows."""
    def _get(col: str) -> str:
        idx = colmap.get(col)
        if idx is None or idx >= len(cells):
            return ""
        return str(cells[idx] or "").strip()

    name = re.sub(r"\s+", " ", _get("name")).strip()
    if not name or len(name) < 2:
        return None
    if name.lower() in {"item", "name", "product", "menu item", "total"}:
        return None
    # Reject obvious header echoes / footnotes
    if name.startswith("*") or name.startswith("("):
        return None

    p = parse_numeric_value(_get("protein"))
    f = parse_numeric_value(_get("fat"))
    c = parse_numeric_value(_get("carbs"))
    if p is None or f is None or c is None:
        return None

    if "kcal" in colmap:
        kcal = coerce_energy_to_kcal(parse_numeric_value(_get("kcal")), "kcal", p, f, c)
    elif "kj" in colmap:
        kcal = coerce_energy_to_kcal(parse_numeric_value(_get("kj")), "kj", p, f, c)
    else:
        kcal = coerce_energy_to_kcal(parse_numeric_value(_get("energy")), "energy", p, f, c)
    if kcal is None or kcal <= 0:
        return None
    if kcal > 5000:
        # Almost certainly kJ that slipped through, or a per-100g-of-something
        # outlier; trust validator to gate but skip extreme outliers here.
        return None

    serving = re.sub(r"\s+", " ", _get("serving")).strip()
    allergens_text = re.sub(r"\s+", " ", _get("allergens")).strip()

    return ParsedMenuRow(
        item_name=name[:200],
        estimated_calories=kcal,
        estimated_protein_g=int(round(p)),
        estimated_fat_g=int(round(f)),
        estimated_carbs_g=int(round(c)),
        serving_size=serving[:120],
        category=infer_category(name),
        evidence=(evidence or name)[:200],
        allergens_text=allergens_text[:300],
        parse_method="html_table",
    )


# ---------------------------------------------------------------------------
# Diet / allergen / category inference
# ---------------------------------------------------------------------------

# Reuse the audit module's token tuples so inference and validation never
# disagree (a row that the inferrer marks as gluten-free can't then fail the
# audit's gluten check).
PORK_TOKENS = _AUDIT_PORK_TOKENS
GLUTEN_TOKENS = _AUDIT_GLUTEN_TOKENS
DAIRY_TOKENS = _AUDIT_DAIRY_TOKENS
EGG_TOKENS = _AUDIT_EGG_TOKENS
NUT_TOKENS = _AUDIT_NUT_TOKENS
SHELLFISH_TOKENS = _AUDIT_SHELLFISH_TOKENS

# Diet-type inference also needs a meat list; the audit has its own diet
# rules that use a broader set, so keep this aligned with what the audit's
# diet_contradiction check uses.
MEAT_TOKENS = (
    "chicken", "beef", "mutton", "lamb", "fish", "tuna", "salmon", "prawn",
    "shrimp", "bacon", "ham", "pepperoni", "salami", "turkey", "sausage",
    "pork", "anchovy", "anchovies", "duck", "veal", "carnitas", "chorizo",
)
SOY_TOKENS = ("soy", "tofu", "teriyaki", "edamame", "miso", "tempeh")
SESAME_TOKENS = ("sesame", "tahini")


def _has_any(text: str, tokens: Tuple[str, ...]) -> bool:
    """Wrap text in spaces and substring-match each token — mirrors the
    audit module's `_name_has`, so an inferred flag never disagrees with
    the validator's check on the same name."""
    return _audit_name_has(text, tokens)


def infer_category(item_name: str) -> str:
    n = item_name.lower()
    if "pizza" in n:
        return "pizza"
    if any(t in n for t in ("sub ", " sub", "sub.", "submarine")):
        return "sub"
    if "wrap" in n:
        return "wrap"
    if "burger" in n:
        return "burger"
    if "sandwich" in n or "panini" in n:
        return "sandwich"
    if "salad" in n:
        return "salad"
    if "bowl" in n:
        return "bowl"
    if any(t in n for t in ("fries", "side", "wedges", "nugget", "tots")):
        return "sides"
    if any(t in n for t in ("coffee", "latte", "cappuccino", "drink", "smoothie", "juice", "shake", "tea", "cola", "soda")):
        return "drink"
    if any(t in n for t in ("breakfast", "pancake", "muffin", "omelette", "omelet")):
        return "breakfast"
    if any(t in n for t in ("dessert", "cake", "ice cream", "sundae", "cookie", "donut", "doughnut", "brownie", "cheesecake")):
        return "dessert"
    return "entree"


def infer_diet_flags(item_name: str, allergens_text: str = "") -> Dict[str, Any]:
    """Pure-Python diet/allergen flagging — replaces prompt rules 1-3.

    Conservative bias: explicit allergens text wins over name keywords when
    they conflict.
    """
    name = (item_name or "").lower()
    allergens = (allergens_text or "").lower()

    has_meat = _has_any(name, MEAT_TOKENS) or _has_any(name, SHELLFISH_TOKENS)
    has_pork = _has_any(name, PORK_TOKENS)
    has_gluten = _has_any(name, GLUTEN_TOKENS)
    has_dairy = _has_any(name, DAIRY_TOKENS) or "milk" in allergens or "dairy" in allergens
    has_egg = _has_any(name, EGG_TOKENS) or "egg" in allergens
    has_nuts = _has_any(name, NUT_TOKENS) or "nut" in allergens or "tree nut" in allergens
    has_soy = _has_any(name, SOY_TOKENS) or "soy" in allergens or "soya" in allergens
    has_sesame = _has_any(name, SESAME_TOKENS) or "sesame" in allergens
    has_shellfish = _has_any(name, SHELLFISH_TOKENS) or "shellfish" in allergens or "crustacean" in allergens

    if "wheat" in allergens or "gluten" in allergens:
        has_gluten = True

    if has_meat:
        diet_type = "non_veg"
    elif has_dairy or has_egg:
        diet_type = "vegetarian"
    else:
        diet_type = "vegan"

    return {
        "diet_type": diet_type,
        "vegetarian_possible": diet_type != "non_veg",
        "vegan_possible": diet_type == "vegan",
        "halal_possible": not has_pork,
        "gluten_free_possible": not has_gluten,
        "contains_nuts": has_nuts,
        "contains_dairy": has_dairy,
        "contains_gluten": has_gluten,
        "contains_soy": has_soy,
        "contains_shellfish": has_shellfish,
        "contains_egg": has_egg,
        "contains_sesame": has_sesame,
    }


# ---------------------------------------------------------------------------
# HTTP / crawl
# ---------------------------------------------------------------------------


def fetch_html(url: str, *, timeout: int = HTTP_TIMEOUT) -> Tuple[str, str, str]:
    """Fetch a URL and return (text, source_hash, content_type).

    Raises requests.HTTPError on non-2xx. Caller is expected to try/except.
    """
    import requests
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
    }
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    content_type = (resp.headers.get("content-type") or "").lower().split(";")[0].strip()
    raw = resp.text
    src_hash = hashlib.sha256(resp.content).hexdigest()[:16]
    return raw, src_hash, content_type


def _normalize_url(url: str) -> str:
    """Drop the fragment and trailing slash variants for de-dup."""
    cleaned, _ = urldefrag(url)
    return cleaned.rstrip("/")


def _registrable_domain(host: str) -> str:
    """Best-effort registrable-domain match — last 2 labels for most TLDs,
    last 3 for known multi-label suffixes (co.uk, co.in, com.au, com.bd)."""
    parts = host.lower().split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "net", "org", "gov", "ac"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def score_candidate(
    url: str,
    anchor_text: str,
    *,
    start_host: str,
    market: str,
    depth: int,
) -> Tuple[int, List[str]]:
    """Score a discovered URL. Higher = more likely to contain nutrition data."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not host:
        return -100, ["no host"]

    score = 0
    reasons: List[str] = []
    # Reject obvious noise paths
    path_low = (parsed.path or "").lower()
    full_low = (url + " " + anchor_text).lower()
    for tok in REJECT_PATH_TOKENS:
        if tok in path_low:
            return -100, [f"reject:{tok}"]

    if host == start_host:
        score += 40
        reasons.append("same-host")
    elif _registrable_domain(host) == _registrable_domain(start_host):
        score += 30
        reasons.append("same-registrable-domain")
    else:
        return -100, ["off-domain"]

    if any(k in full_low for k in KEYWORD_NUTRITION):
        score += 25
        reasons.append("kw:nutrition")
    if any(k in full_low for k in KEYWORD_ALLERGEN):
        score += 20
        reasons.append("kw:allergen")
    if path_low.endswith(".pdf"):
        score += 15
        reasons.append("ext:pdf")
    if any(k in full_low for k in KEYWORD_MENU):
        score += 10
        reasons.append("kw:menu")
    if any(k in full_low for k in KEYWORD_DOWNLOAD):
        score += 8
        reasons.append("kw:download")

    market_tokens = MARKET_TOKEN_HINTS.get(market.upper(), ())
    if market_tokens and any(t in full_low for t in market_tokens):
        score += 8
        reasons.append("kw:market")

    score -= 5 * depth
    return score, reasons


def _is_pdf_url(url: str, content_type: str = "") -> bool:
    if "application/pdf" in (content_type or ""):
        return True
    return urlparse(url).path.lower().endswith(".pdf")


def crawl_official_source(
    start_url: str,
    chain_key: str,
    market: str,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> List[SourceCandidate]:
    """BFS crawl from start_url, return scored candidates sorted desc."""
    from bs4 import BeautifulSoup

    start_host = urlparse(start_url).netloc.lower()
    seen: set[str] = set()
    candidates: Dict[str, SourceCandidate] = {}

    # Seed
    seed_score, seed_reasons = score_candidate(
        start_url, "", start_host=start_host, market=market, depth=0,
    )
    queue: List[Tuple[str, str, int, str]] = [(start_url, "", 0, start_url)]
    seen.add(_normalize_url(start_url))
    candidates[_normalize_url(start_url)] = SourceCandidate(
        url=start_url,
        source_type="pdf" if _is_pdf_url(start_url) else "page",
        score=max(seed_score, 0),
        depth=0,
        anchor_text="",
        discovered_from=start_url,
        reasons=seed_reasons,
    )

    pages_fetched = 0
    while queue and pages_fetched < max_pages:
        url, anchor, depth, parent = queue.pop(0)
        if depth > max_depth:
            continue
        if _is_pdf_url(url):
            # Don't fetch PDFs for crawling; they're terminal candidates
            continue
        try:
            html, _src_hash, content_type = fetch_html(url)
            pages_fetched += 1
        except Exception as exc:
            print(f"      [crawl] fetch failed depth={depth} {url[:80]}: {type(exc).__name__}")
            continue
        # If the URL turned out to be a PDF, mark and stop here
        if _is_pdf_url(url, content_type):
            cand = candidates.get(_normalize_url(url))
            if cand:
                cand.source_type = "pdf"
                cand.content_type = content_type
            continue
        if "html" not in (content_type or "html"):
            continue

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            continue

        for a in soup.find_all("a", href=True):
            raw_href = (a.get("href") or "").strip()
            if not raw_href or raw_href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            child = urljoin(url, raw_href)
            child_norm = _normalize_url(child)
            if child_norm in seen:
                continue
            anchor_text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            sc, reasons = score_candidate(
                child, anchor_text,
                start_host=start_host, market=market, depth=depth + 1,
            )
            if sc < 0:
                continue
            seen.add(child_norm)
            candidates[child_norm] = SourceCandidate(
                url=child,
                source_type="pdf" if _is_pdf_url(child) else "page",
                score=sc,
                depth=depth + 1,
                anchor_text=anchor_text[:200],
                discovered_from=url,
                reasons=reasons,
            )
            if depth + 1 < max_depth and not _is_pdf_url(child):
                queue.append((child, anchor_text, depth + 1, url))

        # Also surface sitemap.xml links if we're at root
        if depth == 0:
            try:
                from urllib.parse import urlsplit
                root = urlsplit(url)
                sitemap_url = f"{root.scheme}://{root.netloc}/sitemap.xml"
                _maybe_pull_sitemap(sitemap_url, candidates, seen, queue,
                                    start_host, market, max_depth)
            except Exception:
                pass

    ranked = sorted(candidates.values(), key=lambda c: c.score, reverse=True)
    return ranked[:max_candidates]


def _maybe_pull_sitemap(
    sitemap_url: str,
    candidates: Dict[str, SourceCandidate],
    seen: set,
    queue: List[Tuple[str, str, int, str]],
    start_host: str,
    market: str,
    max_depth: int,
) -> None:
    import requests
    try:
        r = requests.get(sitemap_url, headers={"User-Agent": USER_AGENT},
                         timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            return
    except Exception:
        return
    locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
    for loc in locs[:200]:
        loc = loc.strip()
        if not loc:
            continue
        ln = _normalize_url(loc)
        if ln in seen:
            continue
        sc, reasons = score_candidate(
            loc, "", start_host=start_host, market=market, depth=1,
        )
        if sc < 15:  # sitemap is noisy; raise the bar
            continue
        seen.add(ln)
        candidates[ln] = SourceCandidate(
            url=loc,
            source_type="pdf" if _is_pdf_url(loc) else "page",
            score=sc,
            depth=1,
            anchor_text="",
            discovered_from=sitemap_url,
            reasons=reasons + ["sitemap"],
        )
        if not _is_pdf_url(loc) and 1 < max_depth:
            queue.append((loc, "", 1, sitemap_url))


# ---------------------------------------------------------------------------
# HTML / JSON parsers
# ---------------------------------------------------------------------------


def extract_items_from_html_tables(html: str, page_url: str) -> List[ParsedMenuRow]:
    """Parse all <table> elements; return rows from any table with mappable cols."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    rows: List[ParsedMenuRow] = []

    for table in soup.find_all("table"):
        body_rows = table.find_all("tr")
        if not body_rows:
            continue
        # Find the first row that looks like a header
        header_idx = -1
        colmap: Optional[Dict[str, int]] = None
        for i, tr in enumerate(body_rows[:3]):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(("th", "td"))]
            if len(cells) >= 4:
                cm = map_table_headers(cells)
                if cm:
                    colmap = cm
                    header_idx = i
                    break
        if not colmap:
            continue
        for tr in body_rows[header_idx + 1:]:
            cells_html = tr.find_all(("th", "td"))
            if not cells_html:
                continue
            cells = [c.get_text(" ", strip=True) for c in cells_html]
            row = build_row_from_cells(cells, colmap, evidence=page_url)
            if row:
                row.parse_method = "html_table"
                rows.append(row)
    return rows


def extract_items_from_embedded_json(html: str, page_url: str) -> List[ParsedMenuRow]:
    """Pull menu items out of <script type='application/ld+json'> + framework blobs."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    rows: List[ParsedMenuRow] = []

    # 1. JSON-LD
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        body = (script.string or script.get_text() or "").strip()
        if not body:
            continue
        try:
            payload = json.loads(body)
        except Exception:
            continue
        rows.extend(_walk_json_for_items(payload, page_url, "ld_json"))

    # 2. __NEXT_DATA__ / __NUXT__ / __INITIAL_STATE__
    for script_id in ("__NEXT_DATA__", "__NUXT__"):
        tag = soup.find("script", id=script_id)
        if not tag:
            continue
        body = (tag.string or tag.get_text() or "").strip()
        if not body:
            continue
        try:
            payload = json.loads(body)
        except Exception:
            continue
        rows.extend(_walk_json_for_items(payload, page_url, f"hydrate:{script_id}"))

    return rows


def _walk_json_for_items(
    payload: Any,
    page_url: str,
    parse_label: str,
) -> List[ParsedMenuRow]:
    """Walk a JSON tree, yield rows for any node that looks like a nutritional item."""
    rows: List[ParsedMenuRow] = []
    stack: List[Any] = [payload]
    seen_ids: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in seen_ids:
            continue
        seen_ids.add(id(node))
        if isinstance(node, dict):
            row = _row_from_jsonld_node(node, page_url)
            if row:
                row.parse_method = f"embedded_json:{parse_label}"
                rows.append(row)
            for v in node.values():
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(node, list):
            for v in node:
                if isinstance(v, (dict, list)):
                    stack.append(v)
    return rows


def _row_from_jsonld_node(node: Dict[str, Any], page_url: str) -> Optional[ParsedMenuRow]:
    """Recognize schema.org/MenuItem-shaped nodes with NutritionInformation."""
    name = node.get("name") or node.get("itemName") or node.get("title")
    if not isinstance(name, str) or len(name.strip()) < 2:
        return None
    nutr = node.get("nutrition") or node.get("nutritionInformation")
    if not isinstance(nutr, dict):
        return None
    cal_raw = (
        nutr.get("calories")
        or nutr.get("caloricContent")
        or nutr.get("energy")
    )
    p_raw = nutr.get("proteinContent") or nutr.get("protein")
    f_raw = nutr.get("fatContent") or nutr.get("fat")
    c_raw = nutr.get("carbohydrateContent") or nutr.get("carbohydrate") or nutr.get("carbs")
    if not all(x is not None for x in (cal_raw, p_raw, f_raw, c_raw)):
        return None
    p = parse_numeric_value(str(p_raw))
    f = parse_numeric_value(str(f_raw))
    c = parse_numeric_value(str(c_raw))
    if p is None or f is None or c is None:
        return None
    cal_value = parse_numeric_value(str(cal_raw))
    cal_unit = "kcal"
    if isinstance(cal_raw, str) and "kj" in cal_raw.lower():
        cal_unit = "kj"
    elif isinstance(cal_raw, str) and not re.search(r"kcal|cal", cal_raw, re.I):
        cal_unit = "energy"
    kcal = coerce_energy_to_kcal(cal_value, cal_unit, p, f, c)
    if kcal is None or kcal <= 0:
        return None
    serving = node.get("servingSize") or nutr.get("servingSize") or ""
    if not isinstance(serving, str):
        serving = str(serving)
    return ParsedMenuRow(
        item_name=name.strip()[:200],
        estimated_calories=kcal,
        estimated_protein_g=int(round(p)),
        estimated_fat_g=int(round(f)),
        estimated_carbs_g=int(round(c)),
        serving_size=serving.strip()[:120],
        category=infer_category(name),
        evidence=page_url,
        allergens_text="",
        parse_method="embedded_json",
    )


# ---------------------------------------------------------------------------
# PDF parser (shared with ingest_chain_from_pdf.py)
# ---------------------------------------------------------------------------


def download_pdf_to_cache(pdf_url: str, *, cache_dir: str = PDF_CACHE_DIR) -> str:
    """Download a PDF to the cache dir keyed by URL hash; return local path.

    Verifies the downloaded file actually starts with the %PDF- magic bytes —
    chain sites frequently redirect dead PDF URLs to an HTML homepage with a
    200 response, and we'd rather fail loudly than cache HTML as a PDF.
    """
    import requests
    os.makedirs(cache_dir, exist_ok=True)
    fname = hashlib.sha256(pdf_url.encode()).hexdigest()[:16] + ".pdf"
    path = os.path.join(cache_dir, fname)
    if os.path.exists(path) and os.path.getsize(path) > 1024:
        with open(path, "rb") as fh:
            if fh.read(5) == b"%PDF-":
                return path
        os.remove(path)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"}
    resp = requests.get(pdf_url, headers=headers, timeout=60, stream=True)
    resp.raise_for_status()
    content_type = (resp.headers.get("content-type") or "").lower()
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)
    with open(tmp_path, "rb") as fh:
        magic = fh.read(5)
    if magic != b"%PDF-":
        os.remove(tmp_path)
        raise RuntimeError(
            f"Downloaded file is not a PDF (magic={magic!r}, "
            f"content-type={content_type!r}, url={pdf_url[:100]}). "
            f"Likely a soft-404 redirect to an HTML page."
        )
    os.replace(tmp_path, path)
    return path


def extract_items_from_pdf_path(pdf_path: str, source_url: str) -> List[ParsedMenuRow]:
    """Extract rows from a local PDF using pdfplumber. Stitches multi-page tables."""
    import pdfplumber
    rows: List[ParsedMenuRow] = []
    last_colmap: Optional[Dict[str, int]] = None
    last_header_fingerprint: Optional[Tuple[str, ...]] = None

    try:
        pdf = pdfplumber.open(pdf_path)
    except Exception as exc:
        print(f"      [pdf] open failed: {type(exc).__name__}: {exc}")
        return []

    with pdf:
        total_text_len = 0
        for page_idx, page in enumerate(pdf.pages):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            total_text_len += len(text)

            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []
            if not tables:
                try:
                    single = page.extract_table()
                    if single:
                        tables = [single]
                except Exception:
                    pass

            for tbl in tables:
                if not tbl or len(tbl) < 2:
                    continue
                cleaned = [[(cell or "").strip() for cell in r] for r in tbl]
                # Try to map header from first non-empty row
                header_idx = -1
                colmap: Optional[Dict[str, int]] = None
                for i, r in enumerate(cleaned[:3]):
                    if sum(1 for c in r if c) >= 3:
                        cm = map_table_headers(r)
                        if cm:
                            colmap = cm
                            header_idx = i
                            break

                if not colmap:
                    if last_colmap and cleaned and len(cleaned[0]) == max(
                        (max(last_colmap.values()) if last_colmap else 0) + 1, 1
                    ):
                        colmap = last_colmap
                        header_idx = -1
                    else:
                        continue

                fingerprint = tuple(sorted(colmap.keys()))
                if fingerprint != last_header_fingerprint:
                    last_header_fingerprint = fingerprint
                last_colmap = colmap

                body_start = header_idx + 1 if header_idx >= 0 else 0
                for r in cleaned[body_start:]:
                    if not r or all(not c for c in r):
                        continue
                    # Drop repeated header rows mid-table
                    if header_idx >= 0 and r == cleaned[header_idx]:
                        continue
                    row = build_row_from_cells(r, colmap, evidence=source_url)
                    if row:
                        row.parse_method = "pdf_table"
                        rows.append(row)

        if total_text_len < 200 and not rows:
            print(f"      [pdf] image-only PDF detected (text<200, tables=0)")

    # De-dupe by (name, serving)
    out: List[ParsedMenuRow] = []
    seen_keys: set = set()
    for r in rows:
        key = (r.item_name.lower().strip(), r.serving_size.lower().strip())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Normalization / validation / writers
# ---------------------------------------------------------------------------


def normalize_item(
    raw: Dict[str, Any],
    chain_key: str,
    market: str,
    url: str,
    ingest_run_id: str,
    source_hash: str,
    *,
    confidence: float = 0.93,
    extraction_method: str = "website_menu_fetch",
    parse_method: str = "llm",
    extractor_version: Optional[str] = None,
    source_type: str = "official_website_menu",
) -> Dict[str, Any]:
    """Map a raw extracted item into the chain_menu_ingested schema.

    `raw` may be either a ParsedMenuRow.__dict__ or a legacy dict from prior
    LLM output. Diet/allergen flags are preferred from `raw` if present;
    otherwise inferred deterministically.
    """
    name = str(raw.get("item_name") or "").strip()
    item_key_base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    item_key = f"{chain_key}_{market.lower()}_{item_key_base}"[:120]

    inferred = infer_diet_flags(name, str(raw.get("allergens_text") or ""))

    def _flag(key: str) -> Any:
        return raw[key] if key in raw and raw[key] is not None else inferred.get(key)

    return {
        "chain_key": chain_key,
        "source_type": source_type,
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
        "confidence": confidence,
        "supports_swaps": True,
        "negative_flags": [],
        "last_ingested_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active": True,
        "chosen_candidate_specificity_tier": "exact_menu_match",
        "menu_item_source": "real_menu",
        "extraction_method": extraction_method,
        "parse_method": parse_method,
        "raw_text_snippet": str(raw.get("evidence") or "")[:200],
        "ingest_run_id": ingest_run_id,
        "source_hash": source_hash,
        "extractor_version": extractor_version or EXTRACTOR_VERSION,
        "halal_possible": bool(_flag("halal_possible")),
        "gluten_free_possible": bool(_flag("gluten_free_possible")),
        "diet_type": str(_flag("diet_type") or "non_veg").strip().lower(),
        "vegetarian_possible": bool(_flag("vegetarian_possible")),
        "vegan_possible": bool(_flag("vegan_possible")),
        "contains_nuts": bool(_flag("contains_nuts")),
        "contains_dairy": bool(_flag("contains_dairy")),
        "contains_gluten": bool(_flag("contains_gluten")),
        "contains_soy": bool(_flag("contains_soy")),
        "contains_shellfish": bool(_flag("contains_shellfish")),
        "contains_egg": bool(_flag("contains_egg")),
        "contains_sesame": bool(_flag("contains_sesame")),
    }


def validate_items(
    items: List[Dict[str, Any]],
    chain_market: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
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


# ---------------------------------------------------------------------------
# Deprecated LLM-era stubs (kept so legacy importers don't crash)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = "DEPRECATED: deterministic crawler path does not use prompts."
REPAIR_PROMPT_PREFIX = "DEPRECATED: deterministic crawler path does not use repair prompts."
MAX_RETRIES = 0
MODEL = "deterministic"  # legacy callers expect a model-name string


def parse_json_array(text: str) -> List[Dict[str, Any]]:
    """Deprecated. The deterministic pipeline does not parse LLM output."""
    import warnings
    warnings.warn(
        "parse_json_array() is deprecated; deterministic pipeline parses HTML/PDF directly.",
        DeprecationWarning,
        stacklevel=2,
    )
    text = str(text or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def _parse_candidate(
    candidate: SourceCandidate,
    chain_key: str,
    market: str,
) -> Tuple[List[ParsedMenuRow], str]:
    """Parse a single candidate page or PDF. Returns (rows, source_url_used)."""
    if candidate.source_type == "pdf":
        try:
            local_pdf = download_pdf_to_cache(candidate.url)
        except Exception as exc:
            print(f"      [parse] PDF download failed: {type(exc).__name__} {candidate.url[:80]}")
            return [], candidate.url
        rows = extract_items_from_pdf_path(local_pdf, candidate.url)
        return rows, candidate.url

    # Page
    try:
        html, _src_hash, content_type = fetch_html(candidate.url)
    except Exception as exc:
        print(f"      [parse] page fetch failed: {type(exc).__name__} {candidate.url[:80]}")
        return [], candidate.url
    if "html" not in (content_type or "html") and "pdf" not in (content_type or ""):
        return [], candidate.url
    if "pdf" in (content_type or ""):
        try:
            local_pdf = download_pdf_to_cache(candidate.url)
            return extract_items_from_pdf_path(local_pdf, candidate.url), candidate.url
        except Exception:
            return [], candidate.url

    rows = extract_items_from_html_tables(html, candidate.url)
    if len(rows) < 5:
        rows.extend(extract_items_from_embedded_json(html, candidate.url))

    # If still thin, try same-domain PDF anchors from this page
    if len(rows) < 5:
        from bs4 import BeautifulSoup
        try:
            soup = BeautifulSoup(html, "html.parser")
            from urllib.parse import urljoin as _uj
            host = urlparse(candidate.url).netloc.lower()
            for a in soup.find_all("a", href=True):
                child = _uj(candidate.url, a.get("href") or "")
                if not _is_pdf_url(child):
                    continue
                if urlparse(child).netloc.lower() != host:
                    continue
                anchor_text = a.get_text(" ", strip=True).lower()
                if not any(k in (child + " " + anchor_text).lower()
                           for k in KEYWORD_NUTRITION + KEYWORD_ALLERGEN):
                    continue
                try:
                    local_pdf = download_pdf_to_cache(child)
                    pdf_rows = extract_items_from_pdf_path(local_pdf, child)
                    if pdf_rows:
                        rows.extend(pdf_rows)
                        break
                except Exception:
                    continue
        except Exception:
            pass
    return rows, candidate.url


def _dedupe_rows(rows: List[ParsedMenuRow]) -> List[ParsedMenuRow]:
    seen: set = set()
    out: List[ParsedMenuRow] = []
    for r in rows:
        key = (r.item_name.lower().strip(), r.serving_size.lower().strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", required=True, help="chain_key e.g. pizza_hut")
    parser.add_argument("--market", required=True, help="market_tag e.g. TH")
    parser.add_argument("--url", required=True, help="official menu/nutrition URL")
    parser.add_argument("--dry-run", action="store_true",
                        help="extract+validate, no write")
    parser.add_argument("--stage-only", action="store_true",
                        help="write to staging dir, not ingested store")
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--target-rows", type=int, default=DEFAULT_TARGET_ROWS)
    args = parser.parse_args()

    chain_key = args.chain.lower()
    market = args.market.upper()
    chain_market = f"{chain_key}::{market}"
    ingest_run_id = uuid.uuid4().hex[:12]

    print(f"\n=== INGEST {chain_market} (deterministic) ===")
    print(f"start URL:    {args.url}")
    print(f"run_id:       {ingest_run_id}")

    print(f"\n[1/4] Crawling {urlparse(args.url).netloc} (depth<={args.max_depth}, "
          f"max_pages={args.max_pages})...")
    t0 = time.time()
    candidates = crawl_official_source(
        args.url, chain_key, market,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
    )
    print(f"      candidates={len(candidates)}  elapsed={time.time()-t0:.1f}s")
    for i, c in enumerate(candidates[:6]):
        print(f"      [{i}] score={c.score:3d} d={c.depth} {c.source_type:4s} "
              f"{c.url[:96]}  reasons={','.join(c.reasons[:4])}")

    print(f"\n[2/4] Parsing top candidates...")
    accumulated: List[ParsedMenuRow] = []
    parsed_urls: List[str] = []
    for cand in candidates:
        if len(accumulated) >= args.target_rows:
            print(f"      hit target_rows={args.target_rows}; stopping early")
            break
        rows, used = _parse_candidate(cand, chain_key, market)
        if rows:
            print(f"      [{cand.source_type:3s}] +{len(rows):2d} rows from {used[:80]}")
            accumulated.extend(rows)
            parsed_urls.append(used)
        else:
            pass

    accumulated = _dedupe_rows(accumulated)
    print(f"      dedup_total={len(accumulated)}")

    if not accumulated:
        print(f"\n[3/4] No rows extracted — exiting without overwrite")
        if os.path.exists(INGESTED_PATH):
            with open(INGESTED_PATH) as _fh:
                _store = json.load(_fh)
            _existing = _store.get("chains", {}).get(chain_market, [])
            if isinstance(_existing, list) and _existing:
                staging_path = write_staging(chain_key, market, [], [])
                print(f"      Refusing to overwrite {len(_existing)} existing items")
                print(f"      Empty payload staged at: {staging_path}")
                return 3
        return 4

    primary_source = parsed_urls[0] if parsed_urls else args.url
    primary_hash = hashlib.sha256(primary_source.encode()).hexdigest()[:16]
    items = [
        normalize_item(
            row.__dict__, chain_key, market, primary_source, ingest_run_id, primary_hash,
            confidence=0.97,
            extraction_method="deterministic_crawl",
            parse_method=row.parse_method,
            extractor_version=EXTRACTOR_VERSION,
        )
        for row in accumulated
    ]

    print(f"\n[3/4] Validating {len(items)} items with audit rules...")
    passing, failures = validate_items(items, chain_market)
    print(f"      passing={len(passing)}  blocking_failures={len(failures)}")

    if failures:
        staging_path = write_staging(chain_key, market, items, failures)
        print(f"\n[4/4] Validation failures — staged at: {staging_path}")
        print(f"      {len(passing)} passed, {len(failures)} blocked. NOT writing to ingested store.")
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
            print(f"\n[4/4] EMPTY — refusing to overwrite {len(_existing)} existing items in {chain_market}")
            print(f"      Empty payload staged at: {staging_path}")
            return 3

    backup_path = write_with_backup(chain_key, market, passing)
    print(f"\n[4/4] WROTE {len(passing)} items to {chain_market}")
    print(f"      backup: {backup_path}")
    print(f"      ingested store: {INGESTED_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

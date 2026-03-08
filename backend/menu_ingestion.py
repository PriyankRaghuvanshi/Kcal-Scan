from __future__ import annotations

import html
import os
import re
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin, urlparse

try:
    import requests
except Exception:  # pragma: no cover - requests is expected in prod, optional in some tests.
    requests = None  # type: ignore[assignment]

from llm_menu_parser import parse_menu_items_with_optional_llm
from menu_intelligence_store import (
    SOURCE_OCR_MENU,
    SOURCE_REVIEW_TEXT,
    SOURCE_WEBSITE_MENU,
    SOURCE_WEBSITE_TEXT,
    ingest_menu_intelligence,
)


MENU_INGESTION_VERSION = "v1"
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}

_MAX_FETCH_BYTES = 300_000
_MAX_MENU_TEXT_CHARS = 12_000
_MAX_SOURCE_TEXTS = 6
_MENU_LINK_TOKENS = ("menu", "food", "order", "dine", "eat")
_URL_KEYS = (
    "menu_url",
    "menuUrl",
    "website",
    "website_url",
    "websiteUrl",
    "website_uri",
    "websiteUri",
    "url",
)
_RAW_TEXT_KEYS = (
    "menu_text",
    "menuText",
    "raw_menu_text",
    "menu_description",
    "menuDescription",
)

_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b[^>]*>.*?</\1>")
_TAG_RE = re.compile(r"(?is)<[^>]+>")
_SPACE_RE = re.compile(r"[ \t]+")
_LINE_SPLIT_RE = re.compile(r"[\r\n]+")
_PRICE_RE = re.compile(r"[$€£₹]\s*\d+(?:[.,]\d{1,2})?")
_NOISE_LINE_RE = re.compile(r"^[\W\d_]{0,}$")
_A_HREF_RE = re.compile(r"""(?is)<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""")

_SOURCE_PRIORITY = {
    SOURCE_WEBSITE_MENU: 5,
    SOURCE_WEBSITE_TEXT: 4,
    SOURCE_OCR_MENU: 3,
    SOURCE_REVIEW_TEXT: 2,
}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return _normalized(raw).lower() in _TRUE_VALUES


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _canonical_item_key(item_name: str) -> str:
    return " ".join(str(item_name or "").strip().lower().split())


def _looks_like_url(value: str) -> bool:
    token = str(value or "").strip()
    if not token:
        return False
    parsed = urlparse(token)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.netloc)


def _same_domain(left: str, right: str) -> bool:
    l_host = str(urlparse(left).hostname or "").strip().lower()
    r_host = str(urlparse(right).hostname or "").strip().lower()
    if not l_host or not r_host:
        return False
    if l_host == r_host:
        return True
    return l_host.endswith(f".{r_host}") or r_host.endswith(f".{l_host}")


def _is_menu_like_url(url: str, anchor_text: str = "") -> bool:
    probe = f"{str(url or '').lower()} {str(anchor_text or '').lower()}"
    return any(token in probe for token in _MENU_LINK_TOKENS)


def _html_to_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleaned = _SCRIPT_STYLE_RE.sub(" ", str(raw_html))
    cleaned = _TAG_RE.sub("\n", cleaned)
    cleaned = html.unescape(cleaned)
    lines = []
    for row in _LINE_SPLIT_RE.split(cleaned):
        line = _SPACE_RE.sub(" ", str(row or "")).strip()
        if not line:
            continue
        lines.append(line)
    return "\n".join(lines)


def normalize_menu_text(raw_text: str) -> str:
    text = str(raw_text or "")
    if not text:
        return ""
    out: List[str] = []
    seen = set()
    for row in _LINE_SPLIT_RE.split(text):
        line = _SPACE_RE.sub(" ", str(row or "")).strip(" -:\t")
        if not line:
            continue
        if _NOISE_LINE_RE.match(line):
            continue
        if len(line) <= 2:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    normalized = "\n".join(out).strip()
    return normalized[:_MAX_MENU_TEXT_CHARS]


def _deterministic_menu_items(text: str, max_items: int) -> List[Dict[str, Any]]:
    if not text:
        return []
    items: List[Dict[str, Any]] = []
    seen = set()
    for raw in _LINE_SPLIT_RE.split(text):
        line = _normalized(raw)
        if not line:
            continue
        line_no_price = _PRICE_RE.sub("", line).strip(" -:")
        if not line_no_price:
            continue
        lowered = line_no_price.lower()
        # Keep short menu-like lines; skip obvious document noise.
        if len(lowered) < 4 or len(lowered) > 70:
            continue
        if any(token in lowered for token in ("terms", "privacy", "copyright", "all rights reserved")):
            continue
        key = _canonical_item_key(line_no_price)
        if not key or key in seen:
            continue
        seen.add(key)
        conf = 0.62
        if any(token in lowered for token in ("chicken", "paneer", "salad", "bowl", "wrap", "burger", "pizza", "dosa", "idli", "tikka")):
            conf += 0.08
        if len(lowered.split()) > 6:
            conf -= 0.06
        items.append({"item_name": line_no_price, "confidence": round(max(0.35, min(0.92, conf)), 2)})
        if len(items) >= max_items:
            break
    return items


def _extract_menu_links(base_url: str, page_html: str, max_links: int = 2) -> List[str]:
    if not base_url or not page_html:
        return []
    out: List[str] = []
    seen = set()
    for href, label in _A_HREF_RE.findall(page_html):
        absolute = urljoin(base_url, str(href or "").strip())
        if not _looks_like_url(absolute):
            continue
        if not _same_domain(base_url, absolute):
            continue
        if not _is_menu_like_url(absolute, str(label or "")):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
        if len(out) >= max_links:
            break
    return out


def _fetch_url_text(url: str, timeout_sec: float = 4.5) -> Tuple[str, str, str]:
    if not _looks_like_url(url):
        return "", "", ""
    if requests is None:
        return "", "", ""
    try:
        resp = requests.get(
            url,
            timeout=max(2.0, min(8.0, float(timeout_sec))),
            headers={"User-Agent": "CalorieClickMenuBot/1.0 (+https://calorieclick.ai)"},
            allow_redirects=True,
        )
    except Exception:
        return "", "", ""

    if resp.status_code < 200 or resp.status_code >= 300:
        return "", "", ""

    content_type = str(resp.headers.get("content-type") or "").strip().lower()
    body = str(resp.text or "")
    if len(body) > _MAX_FETCH_BYTES:
        body = body[:_MAX_FETCH_BYTES]

    text = _html_to_text(body) if "html" in content_type or "<html" in body[:500].lower() else body
    return normalize_menu_text(text), str(resp.url or url), content_type


def _collect_review_text(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    chunks: List[str] = []

    for key in ("review_text", "reviews_text", "review_snippets", "reviewsText", "editorial_summary"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())
        elif isinstance(value, list):
            for row in value:
                if isinstance(row, str) and row.strip():
                    chunks.append(row.strip())
                elif isinstance(row, dict):
                    snippet = str(row.get("text") or row.get("snippet") or row.get("review") or "").strip()
                    if snippet:
                        chunks.append(snippet)

    reviews = payload.get("reviews")
    if isinstance(reviews, list):
        for row in reviews:
            if not isinstance(row, dict):
                continue
            snippet = str(row.get("text") or row.get("originalText") or row.get("comment") or "").strip()
            if snippet:
                chunks.append(snippet)

    return normalize_menu_text("\n".join(chunks))


def _collect_ocr_text(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    candidates: List[str] = []
    for key in ("ocr_text", "menu_ocr_text", "raw_menu_text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    ocr_lines = payload.get("ocr_lines")
    if isinstance(ocr_lines, list):
        lines = [str(x or "").strip() for x in ocr_lines if str(x or "").strip()]
        if lines:
            candidates.append("\n".join(lines))
    return normalize_menu_text("\n".join(candidates))


def _discover_url_candidates(place: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    payload = place if isinstance(place, dict) else {}
    out: List[Tuple[str, str, str]] = []
    seen = set()

    for key in _URL_KEYS:
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        url = value.strip()
        if not _looks_like_url(url) or url in seen:
            continue
        seen.add(url)
        menu_like = "menu" in key.lower() or _is_menu_like_url(url, key)
        source = SOURCE_WEBSITE_MENU if menu_like else SOURCE_WEBSITE_TEXT
        extraction_method = "direct_menu_url" if menu_like else "website_url"
        out.append((url, source, extraction_method))

    links = payload.get("links")
    if isinstance(links, list):
        for row in links:
            url = ""
            label = ""
            if isinstance(row, str):
                url = row.strip()
            elif isinstance(row, dict):
                url = str(row.get("url") or row.get("href") or "").strip()
                label = str(row.get("label") or row.get("title") or "").strip()
            if not _looks_like_url(url) or url in seen:
                continue
            seen.add(url)
            menu_like = _is_menu_like_url(url, label)
            source = SOURCE_WEBSITE_MENU if menu_like else SOURCE_WEBSITE_TEXT
            extraction_method = "menu_link" if menu_like else "website_link"
            out.append((url, source, extraction_method))

    return out[:3]


def _build_source_records(place: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = place if isinstance(place, dict) else {}
    records: List[Dict[str, Any]] = []

    for key in _RAW_TEXT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            text = normalize_menu_text(value)
            if text:
                records.append(
                    {
                        "menu_source": SOURCE_WEBSITE_TEXT,
                        "extraction_method": f"embedded_{key}",
                        "parse_method_hint": "deterministic",
                        "source_url": "",
                        "raw_text": text,
                    }
                )

    review_text = _collect_review_text(payload)
    if review_text:
        records.append(
            {
                "menu_source": SOURCE_REVIEW_TEXT,
                "extraction_method": "review_snippets",
                "parse_method_hint": "deterministic",
                "source_url": "",
                "raw_text": review_text,
            }
        )

    ocr_text = _collect_ocr_text(payload)
    if ocr_text:
        records.append(
            {
                "menu_source": SOURCE_OCR_MENU,
                "extraction_method": "ocr_text",
                "parse_method_hint": "deterministic",
                "source_url": "",
                "raw_text": ocr_text,
            }
        )

    for url, source, extraction_method in _discover_url_candidates(payload):
        page_text, final_url, content_type = _fetch_url_text(url)
        if page_text:
            records.append(
                {
                    "menu_source": source,
                    "extraction_method": extraction_method,
                    "parse_method_hint": "deterministic",
                    "source_url": final_url or url,
                    "raw_text": page_text,
                }
            )

        if source == SOURCE_WEBSITE_TEXT and "html" in content_type and requests is not None:
            # Best-effort second pass: discover explicit /menu links from same page.
            try:
                html_resp = requests.get(
                    final_url or url,
                    timeout=4.0,
                    headers={"User-Agent": "CalorieClickMenuBot/1.0 (+https://calorieclick.ai)"},
                    allow_redirects=True,
                )
                html_body = str(html_resp.text or "")
            except Exception:
                html_body = ""
            for menu_link in _extract_menu_links(final_url or url, html_body, max_links=2):
                menu_text, menu_final_url, _ = _fetch_url_text(menu_link)
                if not menu_text:
                    continue
                records.append(
                    {
                        "menu_source": SOURCE_WEBSITE_MENU,
                        "extraction_method": "menu_link_fetch",
                        "parse_method_hint": "deterministic",
                        "source_url": menu_final_url or menu_link,
                        "raw_text": menu_text,
                    }
                )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in records:
        key = (
            str(row.get("menu_source") or ""),
            str(row.get("source_url") or ""),
            _canonical_item_key(str(row.get("raw_text") or "")[:220]),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= _MAX_SOURCE_TEXTS:
            break
    return deduped


def _merge_scored_items(items: List[Dict[str, Any]], max_items: int) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    idx_by_key: Dict[str, int] = {}
    for row in items:
        name = str(row.get("item_name") or "").strip()
        key = _canonical_item_key(name)
        if not key:
            continue
        conf = _safe_float(row.get("menu_confidence", row.get("confidence")), 0.0)
        source = str(row.get("menu_source") or row.get("source") or "").strip()
        priority = _SOURCE_PRIORITY.get(source, 1)

        if key not in idx_by_key:
            idx_by_key[key] = len(merged)
            merged.append(row)
            continue

        existing_idx = idx_by_key[key]
        existing = merged[existing_idx]
        existing_conf = _safe_float(existing.get("menu_confidence", existing.get("confidence")), 0.0)
        existing_source = str(existing.get("menu_source") or existing.get("source") or "").strip()
        existing_priority = _SOURCE_PRIORITY.get(existing_source, 1)

        replace = False
        if priority > existing_priority:
            replace = True
        elif priority == existing_priority and conf > existing_conf:
            replace = True

        if replace:
            merged[existing_idx] = row

    merged.sort(
        key=lambda row: (
            _SOURCE_PRIORITY.get(str(row.get("menu_source") or row.get("source") or ""), 1),
            _safe_float(row.get("menu_confidence", row.get("confidence")), 0.0),
        ),
        reverse=True,
    )
    return merged[: max(1, int(max_items or 12))]


def ingest_real_menu_for_place(
    place: Dict[str, Any],
    *,
    max_items: int = 12,
) -> Dict[str, Any]:
    if not _env_bool("ENABLE_REAL_MENU_INGESTION", default=True):
        return {
            "ingested": False,
            "menu_items": [],
            "menu_source": "none",
            "menu_confidence": 0.0,
            "extraction_method": "disabled",
            "parse_method": "none",
            "source_url": "",
            "menu_ingestion_version": MENU_INGESTION_VERSION,
        }

    payload = place if isinstance(place, dict) else {}
    place_id = str(payload.get("place_id") or payload.get("id") or "").strip()
    restaurant_name = str(payload.get("name") or "").strip()
    cuisine = str(payload.get("primary_type") or payload.get("primaryType") or "").strip().replace("_", " ")

    source_records = _build_source_records(payload)
    if not source_records:
        return {
            "ingested": False,
            "menu_items": [],
            "menu_source": "none",
            "menu_confidence": 0.0,
            "extraction_method": "none",
            "parse_method": "none",
            "source_url": "",
            "menu_ingestion_version": MENU_INGESTION_VERSION,
        }

    parsed_rows: List[Dict[str, Any]] = []
    parse_methods = set()
    extraction_methods = set()
    source_urls = set()
    source_tokens = set()

    for record in source_records:
        menu_source = str(record.get("menu_source") or SOURCE_WEBSITE_TEXT).strip()
        extraction_method = str(record.get("extraction_method") or "unknown").strip()
        source_url = str(record.get("source_url") or "").strip()
        raw_text = str(record.get("raw_text") or "").strip()
        if not raw_text:
            continue

        deterministic = _deterministic_menu_items(raw_text, max_items=max_items)
        llm_bundle = parse_menu_items_with_optional_llm(
            raw_text=raw_text,
            deterministic_items=deterministic,
            max_items=max_items,
        )
        parsed_items = llm_bundle.get("parsed_items") if isinstance(llm_bundle.get("parsed_items"), list) else []
        structured_items = (
            llm_bundle.get("structured_items")
            if isinstance(llm_bundle.get("structured_items"), list)
            else []
        )
        parse_method = str(llm_bundle.get("parse_method") or "deterministic").strip()
        parse_methods.add(parse_method)
        extraction_methods.add(extraction_method)
        if source_url:
            source_urls.add(source_url)
        source_tokens.add(menu_source)

        structured_by_key: Dict[str, Dict[str, Any]] = {}
        for row in structured_items:
            if not isinstance(row, dict):
                continue
            key = _canonical_item_key(str(row.get("item_name") or ""))
            if key and key not in structured_by_key:
                structured_by_key[key] = row

        for row in parsed_items:
            if not isinstance(row, dict):
                continue
            item_name = str(row.get("item_name") or "").strip()
            if not item_name:
                continue
            key = _canonical_item_key(item_name)
            structured = structured_by_key.get(key, {})
            conf = _safe_float(
                row.get("confidence", row.get("parser_confidence")),
                _safe_float(llm_bundle.get("parser_confidence"), 0.58),
            )
            snippet = ""
            for line in _LINE_SPLIT_RE.split(raw_text):
                probe = _canonical_item_key(line)
                if not probe:
                    continue
                if key in probe or probe in key:
                    snippet = _normalized(line)
                    break
            if not snippet:
                snippet = item_name

            parsed_rows.append(
                {
                    "item_name": item_name,
                    "category": str(structured.get("category") or "").strip(),
                    "likely_protein": str(structured.get("likely_protein") or "").strip(),
                    "likely_carbs": (
                        structured.get("likely_carbs")
                        if isinstance(structured.get("likely_carbs"), list)
                        else []
                    ),
                    "likely_fats": (
                        structured.get("likely_fats")
                        if isinstance(structured.get("likely_fats"), list)
                        else []
                    ),
                    "health_signals": (
                        structured.get("health_signals")
                        if isinstance(structured.get("health_signals"), list)
                        else []
                    ),
                    "source": menu_source,
                    "menu_source": menu_source,
                    "confidence": round(max(0.35, min(0.95, conf)), 2),
                    "menu_confidence": round(max(0.35, min(0.95, conf)), 2),
                    "source_url": source_url,
                    "extraction_method": extraction_method,
                    "parse_method": parse_method,
                    "parsed_via": "llm" if parse_method == "llm" else "deterministic",
                    "raw_text_snippet": snippet[:180],
                }
            )

    merged_items = _merge_scored_items(parsed_rows, max_items=max_items)
    if not merged_items:
        return {
            "ingested": False,
            "menu_items": [],
            "menu_source": "none",
            "menu_confidence": 0.0,
            "extraction_method": "none",
            "parse_method": "none",
            "source_url": "",
            "menu_ingestion_version": MENU_INGESTION_VERSION,
        }

    if place_id:
        # Persist best-effort. This should never break recommendation response.
        try:
            ingest_menu_intelligence(
                place_id=place_id,
                restaurant_name=restaurant_name,
                cuisine=cuisine,
                menu_items=merged_items,
                source=SOURCE_WEBSITE_MENU if SOURCE_WEBSITE_MENU in source_tokens else SOURCE_WEBSITE_TEXT,
            )
        except Exception:
            pass

    avg_conf = sum(_safe_float(row.get("menu_confidence"), 0.0) for row in merged_items) / max(1, len(merged_items))
    return {
        "ingested": True,
        "menu_items": merged_items,
        "menu_source": SOURCE_WEBSITE_MENU if SOURCE_WEBSITE_MENU in source_tokens else (
            SOURCE_WEBSITE_TEXT
            if SOURCE_WEBSITE_TEXT in source_tokens
            else (SOURCE_OCR_MENU if SOURCE_OCR_MENU in source_tokens else SOURCE_REVIEW_TEXT)
        ),
        "menu_confidence": round(max(0.25, min(0.95, avg_conf)), 2),
        "extraction_method": ",".join(sorted(extraction_methods))[:120],
        "parse_method": "llm" if "llm" in parse_methods else "deterministic",
        "source_url": next(iter(source_urls), ""),
        "menu_ingestion_version": MENU_INGESTION_VERSION,
    }

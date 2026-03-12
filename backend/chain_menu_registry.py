from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from chain_registry import resolve_chain_identity

try:
    from chain_menu_ingestion import get_chain_items_for_registry
except ImportError:
    get_chain_items_for_registry = None


CHAIN_MENU_REGISTRY_VERSION = "v1"
DEFAULT_COUNTRY_CODE = "AU"

# Coverage architecture: chains can be global, regional, or local
# Optional in JSON: coverage_type (global_chain|regional_chain|local_chain), markets (["AU","US"])
# When absent, inferred: country_code=GLOBAL -> global_chain; else regional_chain
COVERAGE_TYPES = ("global_chain", "regional_chain", "local_chain")

# Exposed source token for downstream preference logic.
# This is deterministic seeded data (not scraped live here).
_CHAIN_MENU_SOURCE = "chain_registry"
_CHAIN_EXTRACTION_METHOD = "chain_registry_official_menu"
_CHAIN_PARSE_METHOD = "chain_registry_seed"
_CHAIN_PARSED_VIA = "chain_registry"

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_WORD_RE = re.compile(r"[a-z0-9]+")
_NON_ASCII_APOSTROPHES = {"'", "\u2019", "\u2018", "`"}
_SEPARATOR_SPLIT_RE = re.compile(r"\s*(?:[-\u2013\u2014|,/]| at )\s*", re.IGNORECASE)

_LEADING_LOCATION_TOKENS = {
    "westfield",
    "food",
    "court",
    "mall",
    "plaza",
    "centre",
    "center",
    "station",
    "airport",
    "terminal",
    "level",
}

_TRAILING_LOCATION_TOKENS = {
    "store",
    "outlet",
    "branch",
    "shop",
    "kiosk",
    "food",
    "court",
    "mall",
    "plaza",
    "centre",
    "center",
    "station",
    "airport",
    "terminal",
    "nsw",
    "vic",
    "qld",
    "wa",
    "sa",
    "tas",
    "nt",
    "act",
    "au",
    "australia",
}

_CHAIN_ABBREVIATIONS = {
    "hj": "hungry jacks",
    "gyg": "guzman y gomez",
}

_COUNTRY_ALIASES = {
    "au": "AU",
    "australia": "AU",
    "us": "US",
    "usa": "US",
    "united states": "US",
    "uk": "GB",
    "great britain": "GB",
    "united kingdom": "GB",
    "nz": "NZ",
    "new zealand": "NZ",
    "in": "IN",
    "india": "IN",
    "global": "GLOBAL",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    token = " ".join(str(raw).strip().split()).lower()
    return token in _TRUE_VALUES


def _coverage_path() -> Path:
    override = str(os.getenv("CHAIN_MENU_COVERAGE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "chain_menu_coverage.json"


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_brand(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", raw)
    text = text.encode("ascii", "ignore").decode("ascii")
    for token in _NON_ASCII_APOSTROPHES:
        text = text.replace(token, "")
    text = text.replace("&", " and ")
    normalized = " ".join(_WORD_RE.findall(text.lower()))
    if normalized in _CHAIN_ABBREVIATIONS:
        return _CHAIN_ABBREVIATIONS[normalized]
    return normalized


def _tokenize_name(value: str) -> List[str]:
    return [token for token in _normalize_brand(value).split() if token]


def _strip_leading_location_tokens(tokens: List[str]) -> List[str]:
    out = list(tokens)
    while out and out[0] in _LEADING_LOCATION_TOKENS and len(out) > 1:
        out = out[1:]
    return out


def _strip_trailing_location_tokens(tokens: List[str]) -> List[str]:
    out = list(tokens)
    while out and len(out) > 1:
        tail = out[-1]
        if tail in _TRAILING_LOCATION_TOKENS:
            out = out[:-1]
            continue
        if tail.isdigit():
            out = out[:-1]
            continue
        if len(tail) == 1 and tail.isalpha():
            out = out[:-1]
            continue
        break
    return out


def _place_name_candidates(raw_place_name: Any) -> List[str]:
    base = str(raw_place_name or "").strip()
    if not base:
        return []

    segments = [base]
    paren_removed = re.sub(r"\([^)]*\)", " ", base)
    if paren_removed.strip():
        segments.append(paren_removed)
    segments.extend(_SEPARATOR_SPLIT_RE.split(base))

    out: List[str] = []
    seen = set()
    for segment in segments:
        norm = _normalize_brand(segment)
        if not norm:
            continue
        tokens = [token for token in norm.split() if token]
        if not tokens:
            continue

        variants: List[List[str]] = [tokens]
        trimmed = _strip_trailing_location_tokens(tokens)
        if trimmed != tokens:
            variants.append(trimmed)
        lead_trimmed = _strip_leading_location_tokens(tokens)
        if lead_trimmed != tokens:
            variants.append(lead_trimmed)
            variants.append(_strip_trailing_location_tokens(lead_trimmed))
        if len(tokens) >= 3:
            variants.append(tokens[:3])
            variants.append(tokens[:2])

        for parts in variants:
            candidate = " ".join(part for part in parts if part)
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            out.append(candidate)
    return out


def _normalize_country_code(value: Any) -> str:
    token = _normalize_space(value).lower()
    if not token:
        return ""
    if token in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[token]
    if len(token) == 2 and token.isalpha():
        return token.upper()
    return ""


def _infer_country_code(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    for key in ("country_code", "countryCode", "country", "region", "locale_country"):
        candidate = _normalize_country_code(payload.get(key))
        if candidate:
            return candidate

    text = " ".join(
        [
            str(payload.get("address") or payload.get("vicinity") or ""),
            str(payload.get("formatted_address") or payload.get("formattedAddress") or ""),
        ]
    ).lower()
    if "australia" in text:
        return "AU"
    if "united states" in text or " usa" in f" {text} ":
        return "US"
    if "india" in text:
        return "IN"
    if "new zealand" in text:
        return "NZ"
    if "united kingdom" in text or " uk" in f" {text} ":
        return "GB"
    return ""


@lru_cache(maxsize=1)
def _load_registry() -> Dict[str, Any]:
    path = _coverage_path()
    if not path.exists():
        return {"version": CHAIN_MENU_REGISTRY_VERSION, "chains": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {"version": CHAIN_MENU_REGISTRY_VERSION, "chains": []}

    if not isinstance(data, dict):
        return {"version": CHAIN_MENU_REGISTRY_VERSION, "chains": []}
    chains = data.get("chains")
    if not isinstance(chains, list):
        chains = []
    return {
        "version": str(data.get("version") or CHAIN_MENU_REGISTRY_VERSION),
        "chains": [row for row in chains if isinstance(row, dict)],
    }


def clear_chain_menu_registry_cache() -> None:
    _load_registry.cache_clear()


def _infer_coverage_type(entry: Dict[str, Any]) -> str:
    """Infer coverage_type from entry. Supports scalable expansion schema."""
    explicit = str(entry.get("coverage_type") or "").strip().lower()
    if explicit in COVERAGE_TYPES:
        return explicit
    country = _normalize_country_code(entry.get("country_code")) or "GLOBAL"
    return "global_chain" if country == "GLOBAL" else "regional_chain"


def list_chain_entries(
    country_code: str | None = None,
    include_global: bool = True,
    coverage_type: str | None = None,
) -> List[Dict[str, Any]]:
    """
    List chain entries. Supports scalable expansion:
    - country_code / include_global: legacy filter
    - coverage_type: optional filter by global_chain | regional_chain | local_chain
    """
    registry = _load_registry()
    rows = registry.get("chains") if isinstance(registry.get("chains"), list) else []
    requested_country = _normalize_country_code(country_code)
    req_coverage = str(coverage_type or "").strip().lower() if coverage_type else None

    out: List[Dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        r["coverage_type"] = _infer_coverage_type(r)
        row_country = _normalize_country_code(r.get("country_code")) or "GLOBAL"
        if req_coverage and r["coverage_type"] != req_coverage:
            continue
        if requested_country:
            if row_country == requested_country:
                out.append(r)
            elif include_global and row_country == "GLOBAL":
                out.append(r)
        else:
            out.append(r)
    return out


def _entry_aliases(entry: Dict[str, Any]) -> List[str]:
    aliases = entry.get("chain_aliases") if isinstance(entry.get("chain_aliases"), list) else []
    out: List[str] = []
    seen = set()

    candidates = [entry.get("chain_name"), entry.get("chain_key")] + aliases
    for row in candidates:
        norm = _normalize_brand(row)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _alias_match_score(place_candidate: str, alias_norm: str) -> float:
    if not place_candidate or not alias_norm:
        return 0.0

    if place_candidate == alias_norm:
        return 1.0

    place_tokens = place_candidate.split()
    alias_tokens = alias_norm.split()

    if alias_tokens and place_tokens[: len(alias_tokens)] == alias_tokens:
        suffix_count = len(place_tokens) - len(alias_tokens)
        suffix_penalty = 0.02 * min(5, max(0, suffix_count))
        return max(0.84, 0.98 - suffix_penalty)

    if alias_tokens and len(alias_tokens) <= len(place_tokens) and place_tokens[-len(alias_tokens) :] == alias_tokens:
        prefix = place_tokens[: len(place_tokens) - len(alias_tokens)]
        if prefix and all(token in _LEADING_LOCATION_TOKENS for token in prefix):
            return 0.90

    compact_place = place_candidate.replace(" ", "")
    compact_alias = alias_norm.replace(" ", "")
    if compact_place == compact_alias:
        return 0.97
    if compact_place.startswith(compact_alias):
        return 0.87

    if len(alias_tokens) <= 2 and alias_norm in _CHAIN_ABBREVIATIONS.values():
        if compact_place == compact_alias:
            return 0.96

    return 0.0


def _match_chain_entry(
    *,
    entry: Dict[str, Any],
    place_candidates: List[str],
    resolved_country: str,
) -> Dict[str, Any]:
    entry_country = _normalize_country_code(entry.get("country_code")) or "GLOBAL"
    country_bonus = 0.03 if entry_country == resolved_country else (-0.04 if entry_country != "GLOBAL" else 0.0)

    best_alias = ""
    best_candidate = ""
    best_score = 0.0
    for alias in _entry_aliases(entry):
        for candidate in place_candidates:
            score = _alias_match_score(candidate, alias)
            if score <= 0:
                continue
            score += country_bonus
            if score > best_score:
                best_score = score
                best_alias = alias
                best_candidate = candidate

    return {
        "score": best_score,
        "matched_alias": best_alias,
        "matched_candidate": best_candidate,
        "entry_country": entry_country,
    }


def _menu_items_for_entry(entry: Dict[str, Any], max_items: int = 12) -> List[Dict[str, Any]]:
    items = entry.get("items") if isinstance(entry.get("items"), list) else []
    out: List[Dict[str, Any]] = []
    official_url = str(entry.get("official_menu_source_url") or "").strip()

    for row in items:
        if not isinstance(row, dict):
            continue
        item_name = _normalize_space(row.get("item_name"))
        if not item_name:
            continue

        confidence = float(row.get("menu_item_confidence") or row.get("menu_confidence") or 0.86)
        confidence = max(0.45, min(0.98, confidence))

        out.append(
            {
                "item_name": item_name,
                "category": _normalize_space(row.get("category")),
                "estimated_calories": int(float(row.get("estimated_calories") or 0) or 0),
                "estimated_protein_g": int(float(row.get("estimated_protein_g") or 0) or 0),
                "estimated_carbs_g": int(float(row.get("estimated_carbs_g") or 0) or 0),
                "estimated_fat_g": int(float(row.get("estimated_fat_g") or 0) or 0),
                "estimated_satiety": str(row.get("estimated_satiety") or "").strip().lower(),
                "confidence": round(confidence, 2),
                "menu_confidence": round(confidence, 2),
                "source": _CHAIN_MENU_SOURCE,
                "menu_source": _CHAIN_MENU_SOURCE,
                "menu_item_source": "chain_registry",
                "menu_item_confidence": round(confidence, 2),
                "source_url": str(row.get("source_url") or official_url),
                "extraction_method": _CHAIN_EXTRACTION_METHOD,
                "parse_method": _CHAIN_PARSE_METHOD,
                "parsed_via": _CHAIN_PARSED_VIA,
                "raw_text_snippet": _normalize_space(row.get("raw_text_snippet") or item_name)[:180],
                "chain_id": str(entry.get("chain_id") or "").strip(),
                "chain_key": str(entry.get("chain_key") or "").strip(),
                "chain_name": str(entry.get("chain_name") or "").strip(),
                "canonical_name": str(entry.get("chain_name") or "").strip(),
                "chain_name_resolved": str(entry.get("chain_name") or "").strip(),
                "country_code": str(entry.get("country_code") or "").strip().upper(),
                "source_type": str(entry.get("source_type") or "official_website_menu").strip(),
                "menu_last_updated": str(entry.get("menu_last_updated") or "").strip(),
                "official_menu_source_url": official_url,
            }
        )
        if len(out) >= max(1, int(max_items or 12)):
            break
    return out


def _select_entry_by_identity(
    chains: List[Dict[str, Any]],
    *,
    identity: Dict[str, Any],
    resolved_country: str,
) -> Dict[str, Any] | None:
    chain_id = str(identity.get("chain_id") or "").strip()
    if chain_id:
        for row in chains:
            if str((row or {}).get("chain_id") or "").strip() == chain_id:
                return row

    chain_key = str(identity.get("chain_key") or identity.get("brand_family") or "").strip().lower()
    if not chain_key:
        return None

    exact_country: List[Dict[str, Any]] = []
    global_rows: List[Dict[str, Any]] = []
    for row in chains:
        if str((row or {}).get("chain_key") or "").strip().lower() != chain_key:
            continue
        row_country = _normalize_country_code((row or {}).get("country_code")) or "GLOBAL"
        if row_country == resolved_country:
            exact_country.append(row)
        elif row_country == "GLOBAL":
            global_rows.append(row)

    if exact_country:
        return exact_country[0]
    if global_rows:
        return global_rows[0]
    return None


def resolve_chain_menu_for_place(
    place: Dict[str, Any] | None,
    *,
    country_code: str | None = None,
    max_items: int = 12,
) -> Dict[str, Any]:
    if not _env_bool("ENABLE_CHAIN_MENU_COVERAGE", default=True):
        return {}

    payload = place if isinstance(place, dict) else {}
    place_name = str(payload.get("name") or "").strip()
    place_candidates = _place_name_candidates(place_name)
    if not place_candidates:
        return {}

    resolved_country = _normalize_country_code(country_code) or _infer_country_code(payload) or DEFAULT_COUNTRY_CODE
    chains = list_chain_entries(country_code=resolved_country, include_global=True)

    best_entry: Dict[str, Any] | None = None
    identity = resolve_chain_identity(place_name=place_name, country_code=resolved_country, place=payload)
    best_alias = ""
    best_candidate = ""
    best_entry_country = ""
    best_score = 0.0
    if bool(identity.get("matched")):
        selected = _select_entry_by_identity(
            chains,
            identity=identity,
            resolved_country=resolved_country,
        )
        if selected:
            best_entry = selected
            best_alias = str(identity.get("matched_alias") or "")
            best_candidate = str(identity.get("matched_place_name") or "")
            best_score = float(identity.get("match_confidence") or 0.0)
            best_entry_country = _normalize_country_code(best_entry.get("country_code")) or "GLOBAL"

    if not best_entry:
        for entry in chains:
            candidate = _match_chain_entry(
                entry=entry,
                place_candidates=place_candidates,
                resolved_country=resolved_country,
            )
            score = float(candidate.get("score") or 0.0)
            if score > best_score:
                best_score = score
                best_entry = entry
                best_alias = str(candidate.get("matched_alias") or "")
                best_candidate = str(candidate.get("matched_candidate") or "")
                best_entry_country = str(candidate.get("entry_country") or "")

    if not best_entry or best_score < 0.78:
        return {}

    # Prefer ingested chain items over registry templates (offline ingestion pipeline)
    chain_key = str(best_entry.get("chain_key") or "").strip().lower()
    items: List[Dict[str, Any]] = []
    source_used = "chain_registry_template"
    if get_chain_items_for_registry:
        ingested = get_chain_items_for_registry(
            chain_key, market_tag=resolved_country, max_items=max_items, chain_entry=best_entry,
        )
        if ingested:
            items = ingested
            source_used = "ingested_chain_item"
    if not items:
        items = _menu_items_for_entry(best_entry, max_items=max_items)
    if not items:
        return {}

    avg_conf = sum(float(row.get("menu_confidence") or 0.0) for row in items) / max(1, len(items))
    official_url = str(best_entry.get("official_menu_source_url") or "").strip()
    if source_used == "chain_registry_template":
        source_used = "country_chain_registry" if best_entry_country == resolved_country else "global_chain_registry"
    for row in items:
        if not isinstance(row, dict):
            continue
        row["matched_alias"] = best_alias
        row["chain_source_used"] = source_used
        row["canonical_name"] = str(identity.get("canonical_name") or best_entry.get("chain_name") or "")
        row["chain_name_resolved"] = str(identity.get("canonical_name") or best_entry.get("chain_name") or "")

    return {
        "chain_match": True,
        "chain_match_confidence": round(max(0.2, min(0.99, best_score)), 2),
        "chain_id": str(best_entry.get("chain_id") or "").strip(),
        "chain_key": str(best_entry.get("chain_key") or "").strip(),
        "chain_name": str(best_entry.get("chain_name") or "").strip(),
        "canonical_name": str(identity.get("canonical_name") or best_entry.get("chain_name") or "").strip(),
        "chain_name_resolved": str(identity.get("canonical_name") or best_entry.get("chain_name") or "").strip(),
        "country_code": str(best_entry.get("country_code") or resolved_country).strip().upper(),
        "matched_alias": best_alias,
        "matched_place_name": best_candidate,
        "chain_source_used": source_used,
        "chain_match_detail": {
            "matched": True,
            "chain_id": str(best_entry.get("chain_id") or "").strip(),
            "chain_name": str(identity.get("canonical_name") or best_entry.get("chain_name") or "").strip(),
            "match_confidence": round(max(0.2, min(0.99, best_score)), 2),
            "matched_alias": best_alias,
            "country_code": str(best_entry.get("country_code") or resolved_country).strip().upper(),
            "chain_source_used": source_used,
            "chain_key": str(identity.get("chain_key") or best_entry.get("chain_key") or "").strip(),
            "brand_family": str(identity.get("brand_family") or ""),
        },
        "source_type": str(best_entry.get("source_type") or "official_website_menu").strip(),
        "menu_last_updated": str(best_entry.get("menu_last_updated") or "").strip(),
        "official_menu_source_url": official_url,
        "menu_items": items,
        "menu_source": "chain_menu_ingestion" if source_used == "ingested_chain_item" else _CHAIN_MENU_SOURCE,
        "menu_confidence": round(max(0.45, min(0.98, avg_conf)), 2),
        "extraction_method": _CHAIN_EXTRACTION_METHOD,
        "parse_method": _CHAIN_PARSE_METHOD,
        "source_url": official_url,
        "chain_registry_version": CHAIN_MENU_REGISTRY_VERSION,
    }

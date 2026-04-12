from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple


CHAIN_REGISTRY_VERSION = "v1"
DEFAULT_COUNTRY_CODE = ""

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_WORD_RE = re.compile(r"[a-z0-9]+")
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

_CHAIN_ABBREVIATIONS = {
    "hj": "hungry jacks",
    "gyg": "guzman y gomez",
    "bk": "burger king",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return " ".join(str(raw).strip().split()).lower() in _TRUE_VALUES


def _registry_path() -> Path:
    override = str(os.getenv("GLOBAL_CHAIN_REGISTRY_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "global_chain_registry.json"


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_country_code(value: Any) -> str:
    token = _normalize_space(value).lower()
    if not token:
        return ""
    if token in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[token]
    if len(token) == 2 and token.isalpha():
        return token.upper()
    return ""


def _infer_country_from_latlng(lat: Any, lng: Any) -> str:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return ""
    if lat_f == 0.0 and lng_f == 0.0:
        return ""
    if 24.0 <= lat_f <= 49.5 and -125.0 <= lng_f <= -66.0:
        return "US"
    if 18.0 <= lat_f <= 23.0 and -161.0 <= lng_f <= -154.0:
        return "US"
    if 51.0 <= lat_f <= 72.0 and -169.0 <= lng_f <= -129.0:
        return "US"
    if -44.0 <= lat_f <= -10.0 and 113.0 <= lng_f <= 154.0:
        return "AU"
    if -47.5 <= lat_f <= -33.5 and 165.5 <= lng_f <= 179.5:
        return "NZ"
    if 6.5 <= lat_f <= 37.0 and 68.0 <= lng_f <= 98.0:
        return "IN"
    if 49.0 <= lat_f <= 61.0 and -9.0 <= lng_f <= 2.0:
        return "GB"
    if 1.15 <= lat_f <= 1.5 and 103.5 <= lng_f <= 104.1:
        return "SG"
    if 5.5 <= lat_f <= 20.5 and 97.3 <= lng_f <= 105.6:
        return "TH"
    if 0.8 <= lat_f <= 7.5 and 99.5 <= lng_f <= 119.3:
        return "MY"
    if -11.0 <= lat_f <= 6.1 and 95.0 <= lng_f <= 141.0:
        return "ID"
    if 4.5 <= lat_f <= 21.0 and 116.0 <= lng_f <= 127.0:
        return "PH"
    if 21.5 <= lat_f <= 25.5 and 119.5 <= lng_f <= 122.1:
        return "TW"
    if 22.15 <= lat_f <= 22.6 and 113.8 <= lng_f <= 114.45:
        return "HK"
    if 8.0 <= lat_f <= 23.5 and 102.0 <= lng_f <= 110.0:
        return "VN"
    return ""


def _infer_country_code(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    for key in ("country_code", "countryCode", "country", "region", "locale_country"):
        code = _normalize_country_code(payload.get(key))
        if code:
            return code

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
    if "singapore" in text:
        return "SG"
    if "malaysia" in text:
        return "MY"
    if "thailand" in text:
        return "TH"
    if "indonesia" in text:
        return "ID"
    if "philippines" in text:
        return "PH"
    if "japan" in text:
        return "JP"
    if "canada" in text:
        return "CA"
    if "brazil" in text or "brasil" in text:
        return "BR"
    if "mexico" in text or "méxico" in text:
        return "MX"
    if "germany" in text or "deutschland" in text:
        return "DE"
    if "france" in text:
        return "FR"
    if "south africa" in text:
        return "ZA"
    if "united arab emirates" in text or " uae" in f" {text} ":
        return "AE"
    if "south korea" in text or "republic of korea" in text:
        return "KR"
    if "taiwan" in text:
        return "TW"
    if "hong kong" in text:
        return "HK"
    if "vietnam" in text or "viet nam" in text:
        return "VN"
    if "pakistan" in text:
        return "PK"
    if "bangladesh" in text:
        return "BD"

    latlng_guess = _infer_country_from_latlng(payload.get("lat"), payload.get("lng"))
    if latlng_guess:
        return latlng_guess
    return ""


def _normalize_brand(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ")
    text = text.replace("'", "").replace("`", "").replace("\u2019", "").replace("\u2018", "")
    normalized = " ".join(_WORD_RE.findall(text.lower()))
    return _CHAIN_ABBREVIATIONS.get(normalized, normalized)


def _slug(value: Any) -> str:
    token = _normalize_brand(value).strip().replace(" ", "_")
    return token or "chain"


def _tokenize(value: Any) -> List[str]:
    return [t for t in _normalize_brand(value).split() if t]


def _strip_leading_location_tokens(tokens: List[str]) -> List[str]:
    out = list(tokens)
    while out and out[0] in _LEADING_LOCATION_TOKENS and len(out) > 1:
        out = out[1:]
    return out


def _strip_trailing_location_tokens(tokens: List[str]) -> List[str]:
    out = list(tokens)
    while out and len(out) > 1:
        tail = out[-1]
        if tail in _TRAILING_LOCATION_TOKENS or tail.isdigit():
            out = out[:-1]
            continue
        if len(tail) == 1 and tail.isalpha():
            out = out[:-1]
            continue
        break
    return out


def _place_name_candidates(place_name: Any) -> List[str]:
    raw = str(place_name or "").strip()
    if not raw:
        return []

    segments = [raw]
    paren_removed = re.sub(r"\([^)]*\)", " ", raw)
    if paren_removed.strip():
        segments.append(paren_removed)
    segments.extend(_SEPARATOR_SPLIT_RE.split(raw))

    out: List[str] = []
    seen = set()
    for segment in segments:
        tokens = _tokenize(segment)
        if not tokens:
            continue

        variants: List[List[str]] = [tokens]
        tail = _strip_trailing_location_tokens(tokens)
        if tail != tokens:
            variants.append(tail)
        head = _strip_leading_location_tokens(tokens)
        if head != tokens:
            variants.append(head)
            variants.append(_strip_trailing_location_tokens(head))
        if len(tokens) >= 3:
            variants.append(tokens[:3])
            variants.append(tokens[:2])

        for candidate_tokens in variants:
            candidate = " ".join(candidate_tokens).strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            out.append(candidate)
    return out


def _dedupe_aliases(values: List[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for row in values:
        plain = _normalize_space(row)
        if not plain:
            continue
        key = _normalize_brand(plain)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(plain)
    return out


def _normalize_country_codes(values: Any) -> List[str]:
    rows = values if isinstance(values, list) else ([values] if values else [])
    out: List[str] = []
    seen = set()
    for row in rows:
        code = _normalize_country_code(row)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    if not out:
        out = ["GLOBAL"]
    return out


def _safe_int(value: Any, default: int = 2) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return int(default)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any] | None:
    payload = entry if isinstance(entry, dict) else {}
    canonical_name = _normalize_space(payload.get("canonical_name") or payload.get("chain_name"))
    if not canonical_name:
        return None

    country_codes = _normalize_country_codes(payload.get("country_codes") or payload.get("country_code"))
    country_suffix = country_codes[0].lower() if country_codes and country_codes[0] != "GLOBAL" else "global"
    chain_id = _normalize_space(payload.get("chain_id")) or f"{_slug(canonical_name)}_{country_suffix}"

    aliases = _dedupe_aliases(
        [canonical_name] + (payload.get("aliases") if isinstance(payload.get("aliases"), list) else [])
    )
    known_variants = _dedupe_aliases(payload.get("known_variants") if isinstance(payload.get("known_variants"), list) else [])
    domains = _dedupe_aliases(
        payload.get("official_website_domains")
        if isinstance(payload.get("official_website_domains"), list)
        else []
    )
    brand_family = _normalize_space(payload.get("brand_family")) or _slug(canonical_name)
    parent_brand = _normalize_space(payload.get("parent_brand"))

    normalized_tokens = sorted({token for alias in aliases for token in _tokenize(alias)})
    source_metadata = payload.get("source_metadata") if isinstance(payload.get("source_metadata"), dict) else {}
    priority_tier = _safe_int(payload.get("priority_tier"), 2)
    if priority_tier < 1:
        priority_tier = 1
    if priority_tier > 5:
        priority_tier = 5

    return {
        "chain_id": chain_id,
        "canonical_name": canonical_name,
        "aliases": aliases,
        "country_codes": country_codes,
        "parent_brand": parent_brand,
        "brand_family": brand_family,
        "priority_tier": priority_tier,
        "known_variants": known_variants,
        "normalized_tokens": normalized_tokens,
        "official_website_domains": domains,
        "notes": _normalize_space(payload.get("notes")),
        "source_metadata": {
            "seed_type": str(source_metadata.get("seed_type") or payload.get("seed_type") or "curated_open_data"),
            "source_ref": str(source_metadata.get("source_ref") or payload.get("source_ref") or ""),
            "updated_at": str(source_metadata.get("updated_at") or payload.get("updated_at") or _now_iso()),
        },
    }


@lru_cache(maxsize=1)
def _load_registry() -> Dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {"version": CHAIN_REGISTRY_VERSION, "chains": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {"version": CHAIN_REGISTRY_VERSION, "chains": []}

    if not isinstance(data, dict):
        return {"version": CHAIN_REGISTRY_VERSION, "chains": []}
    chains = data.get("chains")
    if not isinstance(chains, list):
        chains = []

    normalized: List[Dict[str, Any]] = []
    for row in chains:
        if not isinstance(row, dict):
            continue
        entry = _normalize_entry(row)
        if entry:
            normalized.append(entry)
    return {"version": str(data.get("version") or CHAIN_REGISTRY_VERSION), "chains": normalized}


def clear_chain_registry_cache() -> None:
    _load_registry.cache_clear()


def _save_registry(registry: Dict[str, Any], path: Path | None = None) -> None:
    target = path or _registry_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(registry, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")


def list_registry_entries(country_code: str | None = None, include_global: bool = True) -> List[Dict[str, Any]]:
    registry = _load_registry()
    rows = registry.get("chains") if isinstance(registry.get("chains"), list) else []
    requested = _normalize_country_code(country_code)
    if not requested:
        return [dict(row) for row in rows if isinstance(row, dict)]

    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        country_codes = row.get("country_codes") if isinstance(row.get("country_codes"), list) else []
        if requested in country_codes or (include_global and "GLOBAL" in country_codes):
            out.append(dict(row))
    return out


def _country_match_weight(entry_country_codes: List[str], requested_country: str) -> float:
    if requested_country and requested_country in entry_country_codes:
        return 0.04
    if "GLOBAL" in entry_country_codes:
        return 0.0
    if requested_country:
        return -0.07
    return 0.0


def _alias_match_score(place_candidate: str, alias: str) -> float:
    p = _normalize_brand(place_candidate)
    a = _normalize_brand(alias)
    if not p or not a:
        return 0.0

    if p == a:
        return 1.0
    p_tokens = p.split()
    a_tokens = a.split()

    if a_tokens and p_tokens[: len(a_tokens)] == a_tokens:
        suffix_count = len(p_tokens) - len(a_tokens)
        suffix_penalty = 0.02 * min(5, max(0, suffix_count))
        return max(0.84, 0.98 - suffix_penalty)

    compact_p = p.replace(" ", "")
    compact_a = a.replace(" ", "")
    if compact_p == compact_a:
        return 0.97
    if compact_p.startswith(compact_a):
        return 0.87
    return 0.0


def resolve_chain_identity(
    *,
    place_name: Any,
    country_code: Any = "",
    place: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not _env_bool("ENABLE_GLOBAL_CHAIN_REGISTRY", default=True):
        return {"matched": False}

    payload = place if isinstance(place, dict) else {}
    resolved_country = (
        _normalize_country_code(country_code)
        or _infer_country_code(payload)
        or DEFAULT_COUNTRY_CODE
    )
    candidates = _place_name_candidates(place_name)
    if not candidates:
        return {"matched": False}

    rows = list_registry_entries(country_code=resolved_country, include_global=True)
    best_entry: Dict[str, Any] | None = None
    best_alias = ""
    best_candidate = ""
    best_score = 0.0

    for entry in rows:
        aliases = entry.get("aliases") if isinstance(entry.get("aliases"), list) else []
        country_codes = entry.get("country_codes") if isinstance(entry.get("country_codes"), list) else ["GLOBAL"]
        country_weight = _country_match_weight(country_codes, resolved_country)
        for alias in aliases:
            for candidate in candidates:
                score = _alias_match_score(candidate, alias) + country_weight
                if score > best_score:
                    best_score = score
                    best_entry = entry
                    best_alias = _normalize_space(alias)
                    best_candidate = _normalize_space(candidate)

    if not best_entry or best_score < 0.78:
        return {
            "matched": False,
            "country_code": resolved_country,
            "normalized_place_name": candidates[0],
        }

    country_codes = best_entry.get("country_codes") if isinstance(best_entry.get("country_codes"), list) else ["GLOBAL"]
    source_used = "country_chain_registry" if resolved_country in country_codes else "global_chain_registry"
    return {
        "matched": True,
        "chain_id": str(best_entry.get("chain_id") or ""),
        "chain_key": _slug(best_entry.get("brand_family") or best_entry.get("canonical_name")),
        "canonical_name": str(best_entry.get("canonical_name") or ""),
        "brand_family": str(best_entry.get("brand_family") or ""),
        "parent_brand": str(best_entry.get("parent_brand") or ""),
        "match_confidence": round(max(0.2, min(0.99, best_score)), 2),
        "matched_alias": best_alias,
        "matched_place_name": best_candidate,
        "country_code": resolved_country,
        "chain_source_used": source_used,
        "registry_version": CHAIN_REGISTRY_VERSION,
    }


def _find_existing_entry(entries: List[Dict[str, Any]], franchise_name: str, country_code: str) -> Tuple[int, Dict[str, Any] | None]:
    probe = _normalize_brand(franchise_name)
    for idx, entry in enumerate(entries):
        aliases = entry.get("aliases") if isinstance(entry.get("aliases"), list) else []
        alias_norms = {_normalize_brand(x) for x in aliases}
        if probe in alias_norms:
            countries = entry.get("country_codes") if isinstance(entry.get("country_codes"), list) else []
            if not country_code or country_code in countries or "GLOBAL" in countries:
                return idx, entry
    return -1, None


def _country_overlap(left: List[str], right: List[str]) -> bool:
    lset = {str(x or "").strip().upper() for x in (left or []) if str(x or "").strip()}
    rset = {str(x or "").strip().upper() for x in (right or []) if str(x or "").strip()}
    if not lset or not rset:
        return True
    if "GLOBAL" in lset or "GLOBAL" in rset:
        return True
    return bool(lset.intersection(rset))


def _find_existing_entry_for_record(entries: List[Dict[str, Any]], record: Dict[str, Any]) -> Tuple[int, Dict[str, Any] | None]:
    probe_id = str(record.get("chain_id") or "").strip()
    probe_family = _normalize_brand(record.get("brand_family") or record.get("canonical_name"))
    probe_aliases = {_normalize_brand(x) for x in (record.get("aliases") if isinstance(record.get("aliases"), list) else [])}
    probe_aliases.discard("")
    probe_countries = record.get("country_codes") if isinstance(record.get("country_codes"), list) else []

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if probe_id and str(entry.get("chain_id") or "").strip() == probe_id:
            return idx, entry

        entry_family = _normalize_brand(entry.get("brand_family") or entry.get("canonical_name"))
        entry_aliases = {_normalize_brand(x) for x in (entry.get("aliases") if isinstance(entry.get("aliases"), list) else [])}
        entry_aliases.discard("")
        entry_countries = entry.get("country_codes") if isinstance(entry.get("country_codes"), list) else []

        alias_overlap = bool(probe_aliases and entry_aliases and probe_aliases.intersection(entry_aliases))
        family_overlap = bool(probe_family and entry_family and probe_family == entry_family)
        if (alias_overlap or family_overlap) and _country_overlap(probe_countries, entry_countries):
            return idx, entry

    return -1, None


def _merge_chain_record(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    canonical_name = str(existing.get("canonical_name") or incoming.get("canonical_name") or "").strip()
    aliases = _dedupe_aliases(
        (existing.get("aliases") if isinstance(existing.get("aliases"), list) else [])
        + (incoming.get("aliases") if isinstance(incoming.get("aliases"), list) else [])
    )
    country_codes = _normalize_country_codes(
        (existing.get("country_codes") if isinstance(existing.get("country_codes"), list) else [])
        + (incoming.get("country_codes") if isinstance(incoming.get("country_codes"), list) else [])
    )
    known_variants = _dedupe_aliases(
        (existing.get("known_variants") if isinstance(existing.get("known_variants"), list) else [])
        + (incoming.get("known_variants") if isinstance(incoming.get("known_variants"), list) else [])
    )
    domains = _dedupe_aliases(
        (existing.get("official_website_domains") if isinstance(existing.get("official_website_domains"), list) else [])
        + (incoming.get("official_website_domains") if isinstance(incoming.get("official_website_domains"), list) else [])
    )

    notes_parts = []
    for token in (existing.get("notes"), incoming.get("notes")):
        text = _normalize_space(token)
        if text and text not in notes_parts:
            notes_parts.append(text)
    notes = " | ".join(notes_parts)

    existing_tier = _safe_int(existing.get("priority_tier"), 2)
    incoming_tier = _safe_int(incoming.get("priority_tier"), 2)
    merged_tier = min(max(1, existing_tier), max(1, incoming_tier))

    seed_types = []
    for row in (
        (existing.get("source_metadata") if isinstance(existing.get("source_metadata"), dict) else {}).get("seed_type"),
        (incoming.get("source_metadata") if isinstance(incoming.get("source_metadata"), dict) else {}).get("seed_type"),
    ):
        text = _normalize_space(row)
        if text and text not in seed_types:
            seed_types.append(text)

    source_refs = []
    for row in (
        (existing.get("source_metadata") if isinstance(existing.get("source_metadata"), dict) else {}).get("source_ref"),
        (incoming.get("source_metadata") if isinstance(incoming.get("source_metadata"), dict) else {}).get("source_ref"),
    ):
        text = _normalize_space(row)
        if text and text not in source_refs:
            source_refs.append(text)

    return _normalize_entry(
        {
            "chain_id": str(existing.get("chain_id") or incoming.get("chain_id") or "").strip(),
            "canonical_name": canonical_name,
            "aliases": aliases,
            "country_codes": country_codes,
            "parent_brand": str(existing.get("parent_brand") or incoming.get("parent_brand") or "").strip(),
            "brand_family": str(existing.get("brand_family") or incoming.get("brand_family") or "").strip(),
            "priority_tier": merged_tier,
            "known_variants": known_variants,
            "official_website_domains": domains,
            "notes": notes,
            "source_metadata": {
                "seed_type": "+".join(seed_types) if seed_types else "curated_open_data",
                "source_ref": "+".join(source_refs),
                "updated_at": _now_iso(),
            },
        }
    ) or dict(existing)


def merge_user_franchise_list(
    franchise_names: List[Any],
    *,
    country_code: str | None = None,
    persist: bool = False,
) -> Dict[str, Any]:
    registry = _load_registry()
    entries = [dict(row) for row in (registry.get("chains") if isinstance(registry.get("chains"), list) else [])]
    requested_country = _normalize_country_code(country_code) or "GLOBAL"

    added_chains = 0
    updated_aliases = 0
    skipped = 0

    for row in franchise_names or []:
        franchise_name = _normalize_space(row)
        if not franchise_name:
            continue

        idx, existing = _find_existing_entry(entries, franchise_name, requested_country)
        if idx >= 0 and isinstance(existing, dict):
            aliases = existing.get("aliases") if isinstance(existing.get("aliases"), list) else []
            updated = _dedupe_aliases(aliases + [franchise_name])
            if len(updated) > len(aliases):
                existing["aliases"] = updated
                existing["known_variants"] = _dedupe_aliases(
                    (existing.get("known_variants") if isinstance(existing.get("known_variants"), list) else [])
                    + [franchise_name]
                )
                meta = existing.get("source_metadata") if isinstance(existing.get("source_metadata"), dict) else {}
                meta["updated_at"] = _now_iso()
                meta["seed_type"] = str(meta.get("seed_type") or "curated_open_data")
                existing["source_metadata"] = meta
                entries[idx] = existing
                updated_aliases += 1
            else:
                skipped += 1
            continue

        key = _slug(franchise_name)
        suffix = requested_country.lower() if requested_country != "GLOBAL" else "global"
        new_entry = _normalize_entry(
            {
                "chain_id": f"{key}_{suffix}",
                "canonical_name": franchise_name,
                "aliases": [franchise_name],
                "country_codes": [requested_country],
                "brand_family": key,
                "known_variants": [franchise_name],
                "official_website_domains": [],
                "notes": "Added from user franchise list seed",
                "source_metadata": {
                    "seed_type": "user_franchise_list",
                    "source_ref": "manual_user_list",
                    "updated_at": _now_iso(),
                },
            }
        )
        if new_entry:
            entries.append(new_entry)
            added_chains += 1
        else:
            skipped += 1

    result = {
        "version": CHAIN_REGISTRY_VERSION,
        "chains": entries,
        "summary": {
            "input_count": len(franchise_names or []),
            "added_chains": added_chains,
            "updated_aliases": updated_aliases,
            "skipped": skipped,
            "country_code": requested_country,
        },
    }

    if persist:
        _save_registry({"version": CHAIN_REGISTRY_VERSION, "chains": entries})
        clear_chain_registry_cache()

    return result


def merge_user_chain_records(
    chain_records: List[Any],
    *,
    default_country_code: str | None = None,
    persist: bool = False,
) -> Dict[str, Any]:
    registry = _load_registry()
    entries = [dict(row) for row in (registry.get("chains") if isinstance(registry.get("chains"), list) else [])]
    default_country = _normalize_country_code(default_country_code) or "GLOBAL"

    added_chains = 0
    merged_chains = 0
    skipped = 0

    for row in chain_records or []:
        if not isinstance(row, dict):
            skipped += 1
            continue

        payload = dict(row)
        if not payload.get("country_codes") and default_country:
            payload["country_codes"] = [default_country]
        normalized = _normalize_entry(payload)
        if not normalized:
            skipped += 1
            continue

        idx, existing = _find_existing_entry_for_record(entries, normalized)
        if idx >= 0 and isinstance(existing, dict):
            entries[idx] = _merge_chain_record(existing, normalized)
            merged_chains += 1
        else:
            entries.append(normalized)
            added_chains += 1

    result = {
        "version": CHAIN_REGISTRY_VERSION,
        "chains": entries,
        "summary": {
            "input_count": len(chain_records or []),
            "added_chains": added_chains,
            "merged_chains": merged_chains,
            "skipped": skipped,
            "default_country_code": default_country,
        },
    }

    if persist:
        _save_registry({"version": CHAIN_REGISTRY_VERSION, "chains": entries})
        clear_chain_registry_cache()

    return result

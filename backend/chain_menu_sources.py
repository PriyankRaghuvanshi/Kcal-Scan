"""
Chain menu source adapters for offline ingestion.
fetch_chain_source / parse_chain_source structure. No live fetch in hot path.
First 4 chains: real adapter scaffolding with curated seed fallback.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from chain_menu_normalization import normalize_raw_item

# Chain keys for first 10 trust-critical chains
FIRST_10_CHAINS = (
    "subway",
    "mcdonalds",
    "kfc",
    "hungry_jacks",
    "dominos",
    "pizza_hut",
    "guzman_y_gomez",
    "oporto",
    "grilld",
    "boost_juice",
)

# Adapters with full scaffolding (first 4)
ADAPTER_CHAINS = ("subway", "mcdonalds", "kfc", "dominos")

# Market suffix for AU
AU_SUFFIX = "_au"


def _coverage_path() -> Path:
    override = str(os.getenv("CHAIN_MENU_COVERAGE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "chain_menu_coverage.json"


def _load_coverage() -> Dict[str, Any]:
    path = _coverage_path()
    if not path.exists():
        return {"chains": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"chains": []}
    return data if isinstance(data, dict) else {"chains": []}


def _find_chain_entry(chain_key: str, market_tag: str = "AU") -> Optional[Dict[str, Any]]:
    data = _load_coverage()
    key_norm = str(chain_key or "").strip().lower()
    market = str(market_tag or "AU").strip().upper()
    for c in data.get("chains") or []:
        if not isinstance(c, dict):
            continue
        ckey = str(c.get("chain_key") or "").strip().lower()
        ccountry = str(c.get("country_code") or "").strip().upper()
        if ckey == key_norm and (ccountry == market or ccountry == "GLOBAL"):
            return c
    for c in data.get("chains") or []:
        if not isinstance(c, dict):
            continue
        ckey = str(c.get("chain_key") or "").strip().lower()
        if ckey == key_norm:
            return c
    return None


def fetch_chain_source(
    chain_key: str,
    market_tag: str = "AU",
    *,
    _fetch_fn: Optional[Callable[[str, str], Optional[str]]] = None,
) -> Optional[str]:
    """
    Fetch raw content for a chain. Background/offline only.
    Returns None when using curated seed (no live fetch).
    _fetch_fn allows injection for testing.
    """
    if _fetch_fn:
        return _fetch_fn(chain_key, market_tag)
    return None


def parse_chain_source(
    raw_content: Optional[str],
    chain_key: str,
    market_tag: str = "AU",
    *,
    source_url: str = "",
    source_type: str = "official_website_menu",
    fallback_to_seed: bool = True,
) -> List[Dict[str, Any]]:
    """
    Parse raw content into normalized items.
    If raw_content is None and fallback_to_seed, use curated seed from chain_menu_coverage.
    """
    items: List[Dict[str, Any]] = []
    entry = _find_chain_entry(chain_key, market_tag) if fallback_to_seed else None
    raw_items: List[Dict[str, Any]] = []

    if raw_content and isinstance(raw_content, str) and raw_content.strip():
        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict) and "items" in parsed:
                raw_items = parsed.get("items") or []
            elif isinstance(parsed, list):
                raw_items = parsed
        except Exception:
            pass

    if not raw_items and entry:
        raw_items = entry.get("items") or []
        source_url = source_url or str(entry.get("official_menu_source_url") or "")
        source_type = source_type or str(entry.get("source_type") or "official_website_menu")

    for row in raw_items[:30]:
        if not isinstance(row, dict):
            continue
        norm = normalize_raw_item(
            row,
            chain_key=chain_key,
            market_tag=market_tag,
            source_type=source_type,
            source_url=source_url,
        )
        if norm:
            items.append(norm)
    return items


def load_chain_seed(chain_key: str, market_tag: str = "AU") -> Optional[Dict[str, Any]]:
    """Load curated seed for a chain. Used by ingestion when no live fetch."""
    return _find_chain_entry(chain_key, market_tag)


def get_chain_source_url(chain_key: str, market_tag: str = "AU") -> str:
    """Official menu/nutrition URL for chain. For audit/debug."""
    entry = _find_chain_entry(chain_key, market_tag)
    if entry:
        return str(entry.get("official_menu_source_url") or "")
    urls = {
        "subway": "https://www.subway.com/en-AU/MenuNutrition/Menu",
        "mcdonalds": "https://mcdonalds.com.au/menu",
        "kfc": "https://www.kfc.com.au/menu",
        "dominos": "https://www.dominos.com.au/menu",
        "hungry_jacks": "https://www.hungryjacks.com.au/menu",
        "pizza_hut": "https://www.pizzahut.com.au/menu",
        "guzman_y_gomez": "https://www.guzmanygomez.com.au/food",
        "oporto": "https://oporto.com.au/menu",
        "grilld": "https://www.grilld.com.au/menu",
        "boost_juice": "https://www.boostjuice.com.au/menu",
    }
    return urls.get(str(chain_key or "").strip().lower(), "")

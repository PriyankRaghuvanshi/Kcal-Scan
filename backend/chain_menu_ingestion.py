"""
Chain menu ingestion: offline/background pipeline to ingest chain menu/nutrition data
into a local store. Powers fast live recommendations with specific chain-backed items.
No live fetch in /places/healthy. No LLM.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from chain_menu_normalization import to_registry_menu_item
from chain_menu_sources import (
    FIRST_10_CHAINS,
    get_chain_source_url,
    load_chain_seed,
    parse_chain_source,
)

INGESTION_STORE_VERSION = "v1"


def _ingested_store_path() -> Path:
    override = str(os.getenv("CHAIN_MENU_INGESTED_STORE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "chain_menu_ingested.json"


@lru_cache(maxsize=1)
def _load_store_cached(path_str: str, mtime: float) -> Dict[str, Any]:
    """Cached store loader keyed on (path, mtime). When the file changes, the
    cache key changes and the cache auto-refreshes. The 22MB JSON was being
    reparsed inside every get_chain_items cache miss, which caused /analyze/text
    to time out at >30s in production (P0 — shipped in App Store)."""
    path = Path(path_str)
    if not path.exists():
        return {"version": INGESTION_STORE_VERSION, "chains": {}, "updated_at": ""}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"version": INGESTION_STORE_VERSION, "chains": {}, "updated_at": ""}
    if not isinstance(data, dict):
        return {"version": INGESTION_STORE_VERSION, "chains": {}, "updated_at": ""}
    chains = data.get("chains")
    if not isinstance(chains, dict):
        chains = {}
    return {
        "version": str(data.get("version") or INGESTION_STORE_VERSION),
        "chains": chains,
        "updated_at": str(data.get("updated_at") or ""),
    }


def _load_store() -> Dict[str, Any]:
    path = _ingested_store_path()
    try:
        mtime = path.stat().st_mtime if path.exists() else 0.0
    except Exception:
        mtime = 0.0
    return _load_store_cached(str(path), mtime)


def _save_store(data: Dict[str, Any]) -> None:
    path = _ingested_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clear_ingested_store_cache() -> None:
    """Clear LRU caches for store reads (call after ingestion)."""
    get_chain_items.cache_clear()
    _load_store_cached.cache_clear()


@lru_cache(maxsize=128)
def get_chain_items(
    chain_key: str,
    market_tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get ingested items for a chain. Returns empty list if none.
    Used by live path - reads from cache only, no fetch.
    """
    key = str(chain_key or "").strip().lower()
    market = str(market_tag or "AU").strip().upper()
    if not key:
        return []
    data = _load_store()
    chains = data.get("chains") or {}
    store_key = f"{key}::{market}"
    items = chains.get(store_key)
    if not isinstance(items, list):
        store_key_global = f"{key}::GLOBAL"
        items = chains.get(store_key_global)
    if not isinstance(items, list):
        return []
    return [dict(i) for i in items if isinstance(i, dict)]


def get_chain_item_by_name(
    chain_key: str,
    item_name: str,
    market_tag: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get one ingested item by approximate name match."""
    items = get_chain_items(chain_key, market_tag)
    name_norm = str(item_name or "").strip().lower()
    if not name_norm:
        return None
    for item in items:
        iname = str(item.get("item_name") or "").strip().lower()
        if iname == name_norm or name_norm in iname or iname in name_norm:
            return dict(item)
    return None


def list_ingested_chain_keys() -> List[str]:
    """List chain_keys that have ingested data."""
    data = _load_store()
    chains = data.get("chains") or {}
    seen: set = set()
    for store_key in chains:
        part = str(store_key).split("::")[0]
        if part:
            seen.add(part)
    return sorted(seen)


def run_ingestion_for_chain(
    chain_key: str,
    market_tag: str = "AU",
    *,
    max_items: int = 30,
) -> Dict[str, Any]:
    """
    Ingest one chain. Uses curated seed (no live fetch).
    Returns summary with item_count, status.
    """
    key = str(chain_key or "").strip().lower()
    market = str(market_tag or "AU").strip().upper()
    if not key:
        return {"chain_key": "", "status": "error", "item_count": 0, "error": "missing chain_key"}

    entry = load_chain_seed(key, market)
    items = parse_chain_source(
        None,
        chain_key=key,
        market_tag=market,
        fallback_to_seed=True,
    )
    items = items[:max_items]
    if not items:
        return {"chain_key": key, "status": "no_items", "item_count": 0}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for item in items:
        item["last_ingested_at"] = ts
    store_key = f"{key}::{market}"
    data = _load_store()
    chains = data.get("chains") or {}
    chains[store_key] = items
    data["chains"] = chains
    _save_store(data)
    clear_ingested_store_cache()
    return {"chain_key": key, "status": "ok", "item_count": len(items)}


def run_ingestion_all(
    *,
    chain_keys: Optional[List[str]] = None,
    market_tag: str = "AU",
    max_items_per_chain: int = 30,
) -> Dict[str, Any]:
    """Ingest all first 10 chains (or provided list)."""
    keys = chain_keys or list(FIRST_10_CHAINS)
    results = []
    for key in keys:
        r = run_ingestion_for_chain(key, market_tag=market_tag, max_items=max_items_per_chain)
        results.append(r)
    return {
        "results": results,
        "total_items": sum(r.get("item_count", 0) for r in results),
    }


def get_chain_items_for_registry(
    chain_key: str,
    market_tag: Optional[str] = None,
    max_items: int = 12,
    chain_entry: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Get ingested items formatted for chain_registry / resolve_chain_menu_for_place.
    Returns list of menu item dicts with menu_item_source=ingested_chain_item.
    """
    raw = get_chain_items(chain_key, market_tag)
    if not raw:
        return []
    out = []
    for item in raw[:max_items]:
        reg = to_registry_menu_item(item, chain_entry)
        out.append(reg)
    return out

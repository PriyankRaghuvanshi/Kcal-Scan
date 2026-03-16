"""
Sync chain menu seed data into Supabase chain_menu_profiles and chain_menu_items.
Offline/background only. No live fetch. Fail-open.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _slug_for_item_key(name: str) -> str:
    """Derive a safe item_key slug from item_name (lowercase, alphanumeric + underscore)."""
    if not name or not str(name).strip():
        return ""
    s = str(name).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "item"


def _load_chain_seed_for_sync(chain_key: str, market_tag: str) -> Optional[Dict[str, Any]]:
    """Load chain seed from data/chains/{chain_key}_{market_tag}.json. Returns None if missing."""
    key = str(chain_key or "").strip().lower()
    market = str(market_tag or "AU").strip().lower()
    if not key:
        return None
    base = Path(__file__).resolve().parent
    path = base / "data" / "chains" / f"{key}_{market}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _ensure_item_scores(item: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure protein_density_score and fat_loss_fit_score exist on item."""
    out = dict(item)
    cal = int(float(item.get("estimated_calories") or 0))
    protein = int(float(item.get("estimated_protein_g") or 0))
    fat = int(float(item.get("estimated_fat_g") or 0))
    neg_flags = item.get("negative_flags")
    nflags = len(neg_flags) if isinstance(neg_flags, list) else 0
    if cal and "protein_density_score" not in out:
        out["protein_density_score"] = round((protein / cal) * 100, 2)
    if "fat_loss_fit_score" not in out:
        out["fat_loss_fit_score"] = round(
            (protein * 2) - (cal / 100) - (fat * 0.5) - (2 * nflags), 2
        )
    return out


def _seed_items_to_rows(
    raw_items: List[Dict[str, Any]],
    chain_key: str,
    market_tag: str,
    seed_source_url: str = "",
) -> List[Dict[str, Any]]:
    """
    Transform seed items into rows for upsert. Preserves required fields; derives item_key
    from item_name when missing. Ensures unique item_key within batch.
    """
    seen: Dict[str, int] = {}
    rows: List[Dict[str, Any]] = []
    for i, raw in enumerate(raw_items or []):
        if not isinstance(raw, dict):
            continue
        item = _ensure_item_scores(raw)
        item_name = str(item.get("item_name") or item.get("name") or "").strip()
        item_key = str(item.get("item_key") or "").strip()
        if not item_key and item_name:
            base = _slug_for_item_key(item_name)
            item_key = base
            cnt = seen.get(base, 0) + 1
            seen[base] = cnt
            if cnt > 1:
                item_key = f"{base}_{cnt}"
        if not item_key:
            item_key = f"item_{i + 1}"
        item["item_key"] = item_key
        # Preserve / set required fields with safe defaults
        item.setdefault("item_name", item_name or "Menu item")
        item.setdefault("category", str(item.get("category") or "").strip() or "entree")
        item.setdefault("estimated_calories", int(float(item.get("estimated_calories") or 0)) or 500)
        item.setdefault("estimated_protein_g", int(float(item.get("estimated_protein_g") or 0)) or 25)
        item.setdefault("estimated_carbs_g", int(float(item.get("estimated_carbs_g") or 0)) or 40)
        item.setdefault("estimated_fat_g", int(float(item.get("estimated_fat_g") or 0)) or 20)
        item.setdefault("vegetarian_possible", bool(item.get("vegetarian_possible")))
        item.setdefault("vegan_possible", bool(item.get("vegan_possible")))
        item.setdefault("confidence", round(float(item.get("confidence") or 0.7), 2))
        item.setdefault("negative_flags", item.get("negative_flags") if isinstance(item.get("negative_flags"), list) else [])
        item.setdefault("menu_item_source", str(item.get("menu_item_source") or "seed_estimated").strip())
        item.setdefault("source_url", str(item.get("source_url") or seed_source_url or "").strip())
        if "protein_density_score" not in item:
            item["protein_density_score"] = round(
                (item["estimated_protein_g"] / max(1, item["estimated_calories"])) * 100, 2
            )
        if "fat_loss_fit_score" not in item:
            item["fat_loss_fit_score"] = round(
                (item["estimated_protein_g"] * 2)
                - (item["estimated_calories"] / 100)
                - (item["estimated_fat_g"] * 0.5)
                - (2 * len(item["negative_flags"])),
                2,
            )
        rows.append(item)
    return rows


def sync_chain_menu_to_supabase(
    chain_key: str,
    market_tag: str = "AU",
    *,
    load_seed: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Load chain seed, upsert profile and items to Supabase. Idempotent.
    load_seed(chain_key, market_tag) can be injected for tests; default uses file loader.
    Returns success: {"ok": True, "chain_key", "market_tag", "item_count"};
    failure: {"ok": False, "chain_key", "market_tag", "item_count": 0, "error"}.
    """
    key = str(chain_key or "").strip().lower()
    market = str(market_tag or "AU").strip().upper()
    base_result = {"chain_key": key, "market_tag": market, "item_count": 0}
    if not key:
        return {**base_result, "ok": False, "error": "missing_chain_key"}

    loader = load_seed if load_seed is not None else _load_chain_seed_for_sync
    seed = loader(key, market) if callable(loader) else None
    if not seed:
        return {**base_result, "ok": False, "error": "no_seed"}
    raw_items = seed.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return {**base_result, "ok": False, "error": "no_items"}

    seed_source_url = str(seed.get("source_url") or "").strip()
    items = _seed_items_to_rows(raw_items, key, market, seed_source_url)
    if not items:
        return {**base_result, "ok": False, "error": "no_items"}

    # Hard failure if any row is missing item_key
    for i, row in enumerate(items):
        ik = str(row.get("item_key") or "").strip()
        if not ik:
            return {
                **base_result,
                "ok": False,
                "error": "missing_item_key",
                "bad_item": {"index": i, "item_name": row.get("item_name"), "payload": row},
            }
    try:
        from supabase_intelligence_store import upsert_chain_menu_profile, upsert_chain_menu_items
    except ImportError:
        return {**base_result, "ok": False, "error": "store_unavailable"}

    profile_row = {
        "chain_key": key,
        "market_tag": market,
        "brand_name": str(seed.get("brand_name") or "").strip() or key,
        "source_url": seed_source_url,
        "source_type": str(seed.get("source_type") or "seed_ingestion").strip(),
        "store_name_variants": seed.get("store_name_variants") if isinstance(seed.get("store_name_variants"), list) else [],
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    upsert_chain_menu_profile(profile_row)
    n = upsert_chain_menu_items(key, market, items)
    if n == 0:
        return {**base_result, "ok": False, "error": "no_chain_menu_items_written"}
    return {"ok": True, "chain_key": key, "market_tag": market, "item_count": n}

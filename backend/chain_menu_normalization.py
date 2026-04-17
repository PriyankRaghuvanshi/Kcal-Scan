"""
Chain menu normalization: schema and normalization for ingested chain items.
No LLM. Deterministic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Normalized ingested item schema fields
INGESTED_ITEM_SCHEMA = (
    "chain_key",
    "source_type",
    "source_url",
    "market_tag",
    "item_key",
    "item_name",
    "category",
    "estimated_calories",
    "estimated_protein_g",
    "estimated_fat_g",
    "estimated_carbs_g",
    "serving_size",
    "confidence",
    "supports_swaps",
    "negative_flags",
    "last_ingested_at",
    "active",
)

# Negative flags for ranking
NEGATIVE_FLAGS = (
    "fried",
    "sugary_drink",
    "combo",
    "dessert_heavy",
    "high_calorie",
    "high_carbs",
    "processed",
    "low_protein",
)

# Specificity tiers for ingested items
TIER_EXACT_MENU_MATCH = "exact_menu_match"
TIER_CHAIN_REGISTRY = "chain_registry"
SOURCE_INGESTED_CHAIN_ITEM = "ingested_chain_item"
SOURCE_CHAIN_REGISTRY_TEMPLATE = "chain_registry_template"


def _safe_str(v: Any, default: str = "") -> str:
    s = str(v or "").strip()
    return s if s else default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _normalize_item_key(name: str, chain_key: str) -> str:
    """Generate stable item_key from item_name and chain_key."""
    import re
    base = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower())
    base = re.sub(r"_+", "_", base).strip("_")
    chain = str(chain_key or "").strip().lower().replace(" ", "_")
    if not base:
        return f"{chain}_item"
    return f"{chain}_{base}"[:80]


def normalize_raw_item(
    raw: Dict[str, Any],
    *,
    chain_key: str,
    market_tag: str = "AU",
    source_type: str = "official_website_menu",
    source_url: str = "",
    last_ingested_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Normalize raw source item into ingested schema.
    Returns dict with INGESTED_ITEM_SCHEMA fields + specificity tier.
    """
    item_name = _safe_str(raw.get("item_name") or raw.get("name") or raw.get("title"))
    if not item_name:
        return {}

    category = _safe_str(raw.get("category") or raw.get("item_type") or "main")
    confidence = max(0.45, min(0.98, _safe_float(raw.get("confidence") or raw.get("menu_item_confidence") or raw.get("menu_confidence"), 0.86)))
    neg_flags = raw.get("negative_flags")
    if isinstance(neg_flags, list):
        neg_flags = [str(f) for f in neg_flags if f]
    elif isinstance(neg_flags, str) and neg_flags:
        neg_flags = [f.strip() for f in neg_flags.split(",") if f.strip()]
    else:
        neg_flags = []

    ts = last_ingested_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "chain_key": str(chain_key or "").strip().lower(),
        "source_type": _safe_str(source_type) or "official_website_menu",
        "source_url": _safe_str(source_url),
        "market_tag": str(market_tag or "AU").strip().upper(),
        "item_key": _normalize_item_key(item_name, chain_key),
        "item_name": item_name,
        "category": category,
        "estimated_calories": _safe_int(raw.get("estimated_calories") or raw.get("calories"), 0),
        "estimated_protein_g": _safe_int(raw.get("estimated_protein_g") or raw.get("protein_g"), 0),
        "estimated_fat_g": _safe_int(raw.get("estimated_fat_g") or raw.get("fat_g"), 0),
        "estimated_carbs_g": _safe_int(raw.get("estimated_carbs_g") or raw.get("carbs_g"), 0),
        "serving_size": _safe_str(raw.get("serving_size") or raw.get("portion")),
        "confidence": round(confidence, 2),
        "supports_swaps": bool(raw.get("supports_swaps", True)),
        "negative_flags": neg_flags,
        "last_ingested_at": ts,
        "active": bool(raw.get("active", True)),
        "chosen_candidate_specificity_tier": TIER_EXACT_MENU_MATCH,
        "menu_item_source": SOURCE_INGESTED_CHAIN_ITEM,
    }


def to_registry_menu_item(ingested: Dict[str, Any], chain_entry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Convert normalized ingested item to chain_registry menu item format
    for use in resolve_chain_menu_for_place.
    """
    entry = chain_entry or {}
    # Preserve high-trust source tags ("real_menu") through the transform.
    # menu_item_scoring.py blends 75% source_anchor for real_menu vs 28% for
    # generic ingested_chain_item — overwriting real_menu here loses that boost.
    raw_source = str(ingested.get("menu_item_source") or "").strip().lower()
    effective_source = raw_source if raw_source in {"real_menu", "official_published", "user_scan"} else SOURCE_INGESTED_CHAIN_ITEM
    return {
        "item_name": ingested.get("item_name"),
        "category": ingested.get("category"),
        "estimated_calories": ingested.get("estimated_calories", 0),
        "estimated_protein_g": ingested.get("estimated_protein_g", 0),
        "estimated_carbs_g": ingested.get("estimated_carbs_g", 0),
        "estimated_fat_g": ingested.get("estimated_fat_g", 0),
        "estimated_satiety": "high" if (ingested.get("estimated_protein_g") or 0) >= 25 else "medium",
        "confidence": ingested.get("confidence", 0.86),
        "menu_confidence": ingested.get("confidence", 0.86),
        "source": effective_source,
        "menu_source": effective_source,
        "menu_item_source": effective_source,
        "menu_item_confidence": ingested.get("confidence", 0.86),
        "source_url": ingested.get("source_url") or str(entry.get("official_menu_source_url") or ""),
        "extraction_method": "chain_menu_ingestion",
        "parse_method": "chain_menu_normalization",
        "parsed_via": "chain_menu_ingestion",
        "chain_key": ingested.get("chain_key"),
        "chosen_candidate_specificity_tier": ingested.get("chosen_candidate_specificity_tier", TIER_EXACT_MENU_MATCH),
        "last_ingested_at": ingested.get("last_ingested_at"),
        "image_url": ingested.get("image_url") or None,
    }

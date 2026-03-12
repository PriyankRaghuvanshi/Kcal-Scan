"""
Chain coverage roadmap for Healthy Nearby.
Structured schema for chain metadata, menu templates, and swap templates.
Enables systematic expansion; adding a chain is config/data work, not custom logic.
No LLM. Integrates with chain_menu_registry.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

# -----------------------------------------------------------------------------
# Schema enums
# -----------------------------------------------------------------------------

ROLLOUT_PRIORITY = (
    "p0_core_trust",      # Highest trust builders (Subway, McDonald's, etc.)
    "p1_high_value",      # Strong healthy-option relevance
    "p2_regional_growth", # Regional expansion targets
    "p3_long_tail",       # Lower priority, long-tail chains
)

CONFIDENCE_TIER = (
    "tier_1_strong",  # Strong nutrition data, verified
    "tier_2_good",    # Good data, some inference
    "tier_3_basic",   # Basic templates, heuristic
)

COVERAGE_STATUS = (
    "planned",   # Roadmap only, not yet in chain_menu_registry
    "partial",  # Some items/templates, needs expansion
    "live",     # In chain_menu_registry, serving traffic
    "enriched", # Full templates + swaps, high quality
)

ROADMAP_VERSION = "v1"


def _roadmap_path() -> Path:
    override = str(os.getenv("CHAIN_COVERAGE_ROADMAP_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "chain_coverage_roadmap.json"


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _normalize_brand(v: Any) -> str:
    raw = str(v or "")
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ").replace("'", "").replace("`", "")
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


@lru_cache(maxsize=1)
def _load_roadmap() -> Dict[str, Any]:
    path = _roadmap_path()
    if not path.exists():
        return {"version": ROADMAP_VERSION, "chains": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"version": ROADMAP_VERSION, "chains": []}
    if not isinstance(data, dict):
        return {"version": ROADMAP_VERSION, "chains": []}
    chains = data.get("chains")
    if not isinstance(chains, list):
        chains = []
    return {
        "version": str(data.get("version") or ROADMAP_VERSION),
        "chains": [c for c in chains if isinstance(c, dict)],
    }


def clear_roadmap_cache() -> None:
    _load_roadmap.cache_clear()


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def list_chain_roadmap(
    *,
    rollout_priority: Optional[str] = None,
    coverage_status: Optional[str] = None,
    market_tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List all chain roadmap entries, optionally filtered."""
    data = _load_roadmap()
    chains = data.get("chains") or []
    out = []
    for c in chains:
        if rollout_priority and str(c.get("rollout_priority") or "").strip() != rollout_priority:
            continue
        if coverage_status and str(c.get("coverage_status") or "").strip() != coverage_status:
            continue
        if market_tag:
            tags = c.get("market_tags") or []
            if not isinstance(tags, list):
                tags = []
            tag_norm = str(market_tag or "").strip().upper()
            if tag_norm and tag_norm not in [str(t).upper() for t in tags]:
                continue
        out.append(dict(c))
    return out


def get_chain_roadmap(chain_key: str) -> Optional[Dict[str, Any]]:
    """Get roadmap entry for a chain by chain_key."""
    key = str(chain_key or "").strip().lower()
    if not key:
        return None
    data = _load_roadmap()
    for c in (data.get("chains") or []):
        if str(c.get("chain_key") or "").strip().lower() == key:
            return dict(c)
    return None


def get_chain_templates(
    chain_key: str,
    *,
    market: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get menu templates for a chain. Optionally filter by market."""
    entry = get_chain_roadmap(chain_key)
    if not entry:
        return []
    templates = entry.get("menu_templates") or []
    if not isinstance(templates, list):
        return []
    if not market:
        return [dict(t) for t in templates if isinstance(t, dict)]
    market_upper = str(market or "").strip().upper()
    out = []
    for t in templates:
        if not isinstance(t, dict):
            continue
        markets = t.get("markets") or []
        if not isinstance(markets, list):
            markets = []
        if not markets or market_upper in [str(m).upper() for m in markets]:
            out.append(dict(t))
    return out


def get_chain_swaps(
    chain_key: str,
    *,
    template_key: Optional[str] = None,
    market: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get swap templates for a chain. Optionally filter by template_key or market.
    When template_key is provided, returns only swaps listed in that template's recommended_swap_keys.
    """
    entry = get_chain_roadmap(chain_key)
    if not entry:
        return []
    swaps = entry.get("swap_templates") or []
    if not isinstance(swaps, list):
        return []
    allowed_swap_keys: Optional[set] = None
    if template_key:
        for t in entry.get("menu_templates") or []:
            if isinstance(t, dict) and str(t.get("template_key") or "").strip() == template_key:
                rec = t.get("recommended_swap_keys") or []
                allowed_swap_keys = set(str(k or "").strip() for k in rec) if isinstance(rec, list) else set()
                break
        if allowed_swap_keys is None:
            return []
    out = []
    for s in swaps:
        if not isinstance(s, dict):
            continue
        if allowed_swap_keys is not None:
            sk = str(s.get("swap_key") or "").strip()
            if sk not in allowed_swap_keys:
                continue
        if market:
            markets = s.get("markets") or []
            if isinstance(markets, list) and markets and str(market).upper() not in [str(m).upper() for m in markets]:
                continue
        out.append(dict(s))
    return out


def match_chain_by_alias(place_name: str) -> Optional[Dict[str, Any]]:
    """
    Match a place name to a roadmap chain by alias.
    Returns the first matching chain with highest alias match strength.
    """
    name_norm = _normalize_brand(place_name)
    if not name_norm:
        return None
    data = _load_roadmap()
    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for c in (data.get("chains") or []):
        aliases = c.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        aliases = [str(a or "").strip().lower() for a in aliases if a]
        display = str(c.get("display_name") or c.get("chain_key") or "").strip().lower()
        if display:
            aliases.append(_normalize_brand(display))
        for alias in aliases:
            if not alias:
                continue
            alias_norm = _normalize_brand(alias)
            if not alias_norm:
                continue
            if alias_norm in name_norm or name_norm in alias_norm:
                score = len(alias_norm) / max(1, len(name_norm)) if alias_norm in name_norm else 0.5
                if score > best_score:
                    best_score = score
                    best = dict(c)
    return best


def list_chains_by_market(market_tag: str) -> List[Dict[str, Any]]:
    """List chains that have the given market_tag."""
    return list_chain_roadmap(market_tag=market_tag)


def validate_roadmap_schema() -> List[str]:
    """Validate roadmap schema. Returns list of error messages (empty if valid)."""
    errors: List[str] = []
    data = _load_roadmap()
    chains = data.get("chains") or []
    seen_keys: set = set()
    for i, c in enumerate(chains):
        if not isinstance(c, dict):
            errors.append(f"Chain[{i}]: not a dict")
            continue
        key = str(c.get("chain_key") or "").strip().lower()
        if not key:
            errors.append(f"Chain[{i}]: missing chain_key")
        elif key in seen_keys:
            errors.append(f"Chain[{i}]: duplicate chain_key={key}")
        seen_keys.add(key)
        aliases = c.get("aliases") or []
        status = str(c.get("coverage_status") or "planned").strip()
        if status in ("live", "partial") and (not aliases or not isinstance(aliases, list)):
            errors.append(f"Chain[{i}] {key}: live/partial must have non-empty aliases")
        rollout = str(c.get("rollout_priority") or "").strip()
        if rollout and rollout not in ROLLOUT_PRIORITY:
            errors.append(f"Chain[{i}] {key}: invalid rollout_priority={rollout}")
    return errors

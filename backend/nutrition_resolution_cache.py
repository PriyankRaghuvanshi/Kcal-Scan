"""
Nutrition resolution cache for food scan pipeline.
Caches USDA/common-food nutrition lookups by normalized food key to avoid repeated API calls.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

CACHE_VERSION = "v1"
DEFAULT_TTL_HOURS = 168  # 7 days

# Singular/plural normalization: map plural to singular for common foods
_PLURAL_TO_SINGULAR: Dict[str, str] = {
    "eggs": "egg",
    "oats": "oat",
    "bananas": "banana",
    "potatoes": "potato",
    "avocados": "avocado",
}

# Spelling variants: map to canonical form
_SPELLING_ALIASES: Dict[str, str] = {
    "yoghurt": "yogurt",
    "daal": "dal",
    "dhaal": "dal",
}

# Weak descriptors to strip when they don't materially change lookup (where safe)
_WEAK_DESCRIPTORS = frozenset({
    "cooked", "raw", "boiled", "steamed", "baked", "grilled", "roasted", "fried",
    "fresh", "plain", "simple", "basic", "regular", "normal", "standard",
    "with", "and", "plus", "extra", "added", "a", "an", "the",
    "piece", "pieces", "slice", "slices", "cup", "cups", "bowl", "bowls",
    "serving", "servings", "portion", "portions", "medium", "large", "small",
})
# Keep these when they distinguish foods (chicken breast vs thigh, white vs brown rice, etc.)
_STRONG_DESCRIPTORS = frozenset({
    "breast", "thigh", "white", "brown", "whole", "skim", "low-fat", "full-fat",
    "whey", "plant", "protein", "greek", "dal", "paneer", "roti", "naan", "whole-grain",
})


def normalize_food_lookup_key(food_name: str, serving_context: Optional[Dict[str, Any]] = None) -> str:
    """
    Normalize food name to a stable lookup key for cache.
    - Lowercase, trim punctuation/noise
    - Normalize singular/plural for common foods
    - Strip weak descriptors that do not materially change lookup
    - Preserve meaningful distinctions (chicken breast vs thigh, white vs brown rice, etc.)
    """
    if not food_name or not isinstance(food_name, str):
        return ""
    raw = str(food_name).strip().lower()
    raw = re.sub(r"[^\w\s\-]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return ""

    tokens = [t for t in raw.split() if t]
    kept: list[str] = []
    for t in tokens:
        t = _SPELLING_ALIASES.get(t, t)
        if t in _WEAK_DESCRIPTORS and t not in _STRONG_DESCRIPTORS:
            continue
        if t in _PLURAL_TO_SINGULAR:
            t = _PLURAL_TO_SINGULAR[t]
        kept.append(t)
    key = " ".join(kept).strip()
    return key or raw


def _cache_path() -> Path:
    override = str(os.getenv("NUTRITION_RESOLUTION_CACHE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "nutrition_resolution_cache.json"


def _now_utc() -> float:
    return time.time()


def get_cached_nutrition_resolution(key: str) -> Optional[Dict[str, Any]]:
    """
    Get cached nutrition resolution for a normalized lookup key.
    Returns None if miss or expired.
    """
    k = str(key or "").strip()
    if not k:
        return None
    path = _cache_path()
    if not path.exists():
        return None
    _lock = getattr(get_cached_nutrition_resolution, "_lock", None)
    if _lock is None:
        setattr(get_cached_nutrition_resolution, "_lock", threading.Lock())
        _lock = getattr(get_cached_nutrition_resolution, "_lock")
    with _lock:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
    entries = data.get("entries") if isinstance(data.get("entries"), dict) else {}
    entry = entries.get(k)
    if not isinstance(entry, dict):
        return None
    ttl_hours = float(entry.get("ttl_hours", DEFAULT_TTL_HOURS) or DEFAULT_TTL_HOURS)
    expires_at = float(entry.get("expires_at", 0) or 0)
    if expires_at <= 0 or _now_utc() > expires_at:
        return None
    return dict(entry)


def set_cached_nutrition_resolution(key: str, value: Dict[str, Any], ttl_hours: int = 168) -> None:
    """
    Store nutrition resolution for a normalized lookup key.
    value should include: macros_per_100g, micros_per_100g (optional), source, fdc_id (optional),
    resolved_name, confidence, created_at, expires_at.
    """
    k = str(key or "").strip()
    if not k:
        return
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _now_utc()
    expires_at = now + (ttl_hours * 3600)
    entry = dict(value)
    entry["lookup_key"] = k
    entry["created_at"] = entry.get("created_at") or now
    entry["expires_at"] = expires_at
    entry["ttl_hours"] = ttl_hours
    _lock = getattr(set_cached_nutrition_resolution, "_lock", None)
    if _lock is None:
        setattr(set_cached_nutrition_resolution, "_lock", threading.Lock())
        _lock = getattr(set_cached_nutrition_resolution, "_lock")
    with _lock:
        try:
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as f:
                        raw = f.read()
                    data = json.loads(raw) if raw.strip() else {"version": CACHE_VERSION, "entries": {}}
                except Exception:
                    data = {"version": CACHE_VERSION, "entries": {}}
            else:
                data = {"version": CACHE_VERSION, "entries": {}}
            if not isinstance(data.get("entries"), dict):
                data["entries"] = {}
            data["entries"][k] = entry
            data["version"] = CACHE_VERSION
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            pass


def resolve_nutrition_with_cache(
    food_item: Dict[str, Any],
    resolver_fn: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Resolve nutrition for a food item, using cache when available.
    food_item must have 'name'.
    resolver_fn(name) returns dict with: macros100, micros100 (optional), fdc_id (optional),
    description (optional), dataType (optional), source, resolved_name, confidence.
    Returns same shape; adds _cache_hit: True/False.
    """
    name = str((food_item or {}).get("name") or "").strip()
    if not name:
        return {"_cache_hit": False, "_resolved": False}
    key = normalize_food_lookup_key(name)
    if not key:
        key = name.lower().strip()
    cached = get_cached_nutrition_resolution(key)
    if cached:
        out = {
            "macros100": cached.get("macros100"),
            "micros100": cached.get("micros100"),
            "fdc_id": cached.get("fdc_id"),
            "description": cached.get("description"),
            "dataType": cached.get("dataType"),
        }
        out["_cache_hit"] = True
        return out
    try:
        resolved = resolver_fn(name)
        if resolved and isinstance(resolved, dict):
            resolved["_cache_hit"] = False
            store = {
                "lookup_key": key,
                "resolved_name": resolved.get("resolved_name", name),
                "source": str(resolved.get("source", "usda")),
                "macros100": resolved.get("macros100"),
                "micros100": resolved.get("micros100"),
                "fdc_id": resolved.get("fdc_id"),
                "description": resolved.get("description"),
                "dataType": resolved.get("dataType"),
                "confidence": float(resolved.get("confidence", 0.8)),
            }
            set_cached_nutrition_resolution(key, store, ttl_hours=DEFAULT_TTL_HOURS)
        return resolved
    except Exception:
        return {"_cache_hit": False, "_resolved": False}

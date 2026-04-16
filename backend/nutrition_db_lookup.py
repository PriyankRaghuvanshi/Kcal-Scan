"""
Nutrition database lookup — USDA FoodData Central.
Matches restaurant menu item names to verified nutritional science data.
Returns macros from USDA instead of pure LLM guessing.

This is Layer 1 of the 1M-item system:
- Tier 1: Chain PDF real_menu (±5%) — our 4,000+ items
- Tier 2: USDA database match (±15%) — covers every common dish
- Tier 3: LLM estimation (±25-40%) — fallback for unknown items
"""
from __future__ import annotations

import os
import json
import time
import logging
from typing import Dict, Any, Optional, List
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

USDA_API_KEY = os.getenv("USDA_API_KEY", "DEMO_KEY")
USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}
_LAST_CALL = 0.0


def _rate_limit():
    """USDA limits to 1000 req/hr. Space calls by 4s minimum."""
    global _LAST_CALL
    elapsed = time.time() - _LAST_CALL
    if elapsed < 4.0:
        time.sleep(4.0 - elapsed)
    _LAST_CALL = time.time()


def lookup_nutrition(
    item_name: str,
    cuisine_hint: str = "",
    serving_g: float = 300.0,
) -> Optional[Dict[str, Any]]:
    """
    Look up nutrition from USDA FoodData Central.
    Returns per-serving macros (not per-100g) for typical restaurant portion.
    """
    query = str(item_name or "").strip()
    if not query or len(query) < 2:
        return None

    cache_key = f"{query.lower()}::{cuisine_hint.lower()}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    search_query = query
    if cuisine_hint:
        search_query = f"{query} {cuisine_hint}"

    try:
        _rate_limit()
        resp = requests.get(
            USDA_SEARCH_URL,
            params={
                "query": search_query,
                "pageSize": 5,
                "api_key": USDA_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("USDA lookup failed for %r: %s", query, str(e)[:120])
        _CACHE[cache_key] = None
        return None

    foods = data.get("foods", [])
    if not foods:
        _CACHE[cache_key] = None
        return None

    # Pick best match (first result from USDA's relevance ranking)
    best = foods[0]
    nutrients = {n["nutrientName"]: n["value"] for n in best.get("foodNutrients", [])}

    # USDA returns per-100g. Convert to per-serving.
    factor = serving_g / 100.0
    cal_100 = float(nutrients.get("Energy", 0))
    pro_100 = float(nutrients.get("Protein", 0))
    fat_100 = float(nutrients.get("Total lipid (fat)", 0))
    carb_100 = float(nutrients.get("Carbohydrate, by difference", 0))

    if cal_100 <= 0:
        _CACHE[cache_key] = None
        return None

    result = {
        "item_name": str(best.get("description", query)),
        "estimated_calories": round(cal_100 * factor),
        "estimated_protein_g": round(pro_100 * factor, 1),
        "estimated_fat_g": round(fat_100 * factor, 1),
        "estimated_carbs_g": round(carb_100 * factor, 1),
        "source": "usda_fooddata_central",
        "confidence": 0.78,
        "usda_fdc_id": best.get("fdcId"),
        "usda_description": best.get("description"),
        "serving_size_g": serving_g,
        "per_100g": {
            "calories": round(cal_100),
            "protein_g": round(pro_100, 1),
            "fat_g": round(fat_100, 1),
            "carbs_g": round(carb_100, 1),
        },
    }

    _CACHE[cache_key] = result
    return result


def bulk_lookup(
    items: List[str],
    cuisine_hint: str = "",
    serving_g: float = 300.0,
) -> List[Optional[Dict[str, Any]]]:
    """Look up multiple items. Rate-limited."""
    return [lookup_nutrition(item, cuisine_hint, serving_g) for item in items]


# Common Indian dish portion sizes (typical restaurant serving)
PORTION_HINTS = {
    "biryani": 350,
    "curry": 250,
    "dal": 200,
    "roti": 60,
    "naan": 80,
    "rice": 200,
    "dosa": 150,
    "idli": 120,
    "samosa": 80,
    "paratha": 100,
    "paneer": 250,
    "chicken": 300,
    "pizza": 200,
    "burger": 250,
    "sandwich": 200,
    "wrap": 250,
    "salad": 300,
    "soup": 300,
    "pasta": 300,
    "smoothie": 400,
    "coffee": 350,
    "shake": 400,
    "ice cream": 150,
    "cake": 120,
    "momo": 200,
    "roll": 200,
    "frankie": 200,
}


def estimate_serving_size(item_name: str) -> float:
    """Estimate portion size from item name keywords."""
    name_lc = item_name.lower()
    for keyword, grams in PORTION_HINTS.items():
        if keyword in name_lc:
            return float(grams)
    return 300.0  # default restaurant portion

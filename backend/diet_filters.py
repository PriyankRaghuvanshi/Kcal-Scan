"""
Diet preference filtering for Healthy Nearby.
Filters and ranks candidates for vegetarian and vegan users.
No LLM. Deterministic. Conservative when uncertain.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

DIET_OMNIVORE = "omnivore"
DIET_VEGETARIAN = "vegetarian"
DIET_VEGAN = "vegan"
DIET_PREFERENCES = (DIET_OMNIVORE, DIET_VEGETARIAN, DIET_VEGAN)

# Item flags (explicit on candidates; or inferred from name)
FLAG_CONTAINS_MEAT = "contains_meat"
FLAG_CONTAINS_CHICKEN = "contains_chicken"
FLAG_CONTAINS_FISH = "contains_fish"
FLAG_CONTAINS_EGG = "contains_egg"
FLAG_CONTAINS_DAIRY = "contains_dairy"
FLAG_CONTAINS_WHEY = "contains_whey"
FLAG_VEGETARIAN_POSSIBLE = "vegetarian_possible"
FLAG_VEGAN_POSSIBLE = "vegan_possible"

# Name tokens that imply non-vegetarian
MEAT_TOKENS = (
    "chicken", "meat", "beef", "pork", "lamb", "bacon", "ham", "sausage",
    "turkey", "steak", "burger", "kebab", "tandoori", "tikka", "biryani",
    "teriyaki", "salmon", "tuna", "fish", "shrimp", "prawn", "seafood",
    "grilled chicken", "chicken breast", "chicken wrap", "chicken sub",
    "meatball", "bbq", "rotisserie",
)
FISH_TOKENS = ("fish", "salmon", "tuna", "shrimp", "prawn", "seafood", "sashimi")
EGG_TOKENS = ("egg", "eggs", "omelette", "bhurji", "egg dosa", "egg and")
DAIRY_TOKENS = ("yogurt", "cheese", "milk", "cream", "butter", "paneer", "ghee", "naan")
WHEY_TOKENS = ("whey", "protein smoothie", "protein shake")
# Explicit vegetarian/vegan signals in name
VEGETARIAN_TOKENS = ("paneer", "dal", "chana", "roti", "idli", "dosa", "sambar", "veg", "veggie", "vegetable", "salad", "quinoa", "tofu")
VEGAN_TOKENS = ("dal", "chana", "roti", "idli", "plain dosa", "veg curry", "vegan", "avocado", "plant", "tofu", "hummus")


def normalize_diet_preference(value: Any) -> str:
    """Normalize diet_preference to omnivore | vegetarian | vegan."""
    s = str(value or "").strip().lower()
    if s in ("veg", "vegetarian"):
        return DIET_VEGETARIAN
    if s == "vegan":
        return DIET_VEGAN
    return DIET_OMNIVORE


def _name_tokens(text: str) -> set:
    """Lowercase tokens from item name for matching."""
    if not text or not isinstance(text, str):
        return set()
    cleaned = re.sub(r"[^\w\s]", " ", str(text).strip().lower())
    return set(w for w in cleaned.split() if len(w) >= 2)


def _infer_diet_flags_from_name(name: str) -> Dict[str, bool]:
    """Infer diet compatibility flags from item name. Conservative: if uncertain, assume not safe."""
    tokens = _name_tokens(name)
    name_lower = name.lower()
    out: Dict[str, bool] = {}
    # Skip meat if explicitly veg/vegan
    if "veggie" in name_lower or "vegan" in name_lower or "vegetarian" in name_lower:
        out[FLAG_CONTAINS_MEAT] = False
        out[FLAG_CONTAINS_CHICKEN] = False
        out[FLAG_CONTAINS_FISH] = False
    else:
        out[FLAG_CONTAINS_MEAT] = any(t in tokens or t in name_lower for t in ("meat", "beef", "pork", "lamb", "bacon", "turkey", "steak", "meatball"))
        out[FLAG_CONTAINS_CHICKEN] = "chicken" in tokens or "chicken" in name_lower
        out[FLAG_CONTAINS_FISH] = any(t in tokens or t in name_lower for t in ("fish", "salmon", "tuna", "shrimp", "prawn", "seafood", "sashimi"))
    out[FLAG_CONTAINS_EGG] = any(t in tokens for t in ("egg", "eggs", "omelette", "bhurji"))
    out[FLAG_CONTAINS_DAIRY] = any(t in tokens or t in name_lower for t in ("yogurt", "cheese", "milk", "cream", "butter", "paneer", "ghee", "naan"))
    out[FLAG_CONTAINS_WHEY] = "whey" in tokens or "whey" in name_lower
    # Positive signals
    out[FLAG_VEGETARIAN_POSSIBLE] = (
        any(t in tokens or t in name_lower for t in ("paneer", "dal", "chana", "idli", "roti", "veggie", "veg", "vegetable", "salad", "tofu", "quinoa"))
        and not (out.get(FLAG_CONTAINS_MEAT, False) or out.get(FLAG_CONTAINS_CHICKEN, False) or out.get(FLAG_CONTAINS_FISH, False))
    )
    out[FLAG_VEGAN_POSSIBLE] = (
        any(t in tokens or t in name_lower for t in ("dal", "chana", "idli", "plain dosa", "veg curry", "vegan", "avocado", "tofu", "hummus"))
        and not (out.get(FLAG_CONTAINS_MEAT, False) or out.get(FLAG_CONTAINS_CHICKEN, False) or out.get(FLAG_CONTAINS_FISH, False) or out.get(FLAG_CONTAINS_EGG, False) or out.get(FLAG_CONTAINS_DAIRY, False))
    )
    return out


def is_item_allowed_for_diet(item: Dict[str, Any], diet_preference: str) -> bool:
    """
    Return True if item is allowed for the given diet.
    Omnivore: all allowed.
    Vegetarian: exclude meat, chicken, fish.
    Vegan: exclude meat, chicken, fish, egg, dairy, whey.
    When uncertain, conservative filtering (exclude).
    """
    diet = normalize_diet_preference(diet_preference)
    if diet == DIET_OMNIVORE:
        return True

    name = str(item.get("item_name") or item.get("name") or item.get("candidate_name") or "").strip()
    flags = dict(item.get("diet_flags") or {})
    if not flags and name:
        flags = _infer_diet_flags_from_name(name)

    # Explicit flags override inference when present
    if item.get("contains_meat") is True or (item.get("contains_meat") is None and flags.get(FLAG_CONTAINS_MEAT)):
        return False
    if item.get("contains_chicken") is True or (item.get("contains_chicken") is None and flags.get(FLAG_CONTAINS_CHICKEN)):
        return False
    if item.get("contains_fish") is True or (item.get("contains_fish") is None and flags.get(FLAG_CONTAINS_FISH)):
        return False

    if diet == DIET_VEGETARIAN:
        return True  # After excluding meat/chicken/fish

    # Vegan: also exclude egg, dairy, whey
    if item.get("contains_egg") is True or (item.get("contains_egg") is None and flags.get(FLAG_CONTAINS_EGG)):
        return False
    if item.get("contains_dairy") is True or (item.get("contains_dairy") is None and flags.get(FLAG_CONTAINS_DAIRY)):
        return False
    if item.get("contains_whey") is True or (item.get("contains_whey") is None and flags.get(FLAG_CONTAINS_WHEY)):
        return False
    return True


def filter_candidates_for_diet(
    candidates: List[Dict[str, Any]],
    diet_preference: str,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Filter candidates to only diet-compatible items.
    Returns (filtered_list, excluded_count).
    """
    diet = normalize_diet_preference(diet_preference)
    if diet == DIET_OMNIVORE:
        return candidates, 0

    filtered = []
    excluded = 0
    for c in candidates:
        if is_item_allowed_for_diet(c, diet):
            filtered.append(c)
        else:
            excluded += 1
    return filtered, excluded


def apply_diet_flags(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add inferred diet_flags to item for trace/audit.
    Returns a copy with diet_flags added.
    """
    out = dict(item)
    name = str(item.get("item_name") or item.get("name") or item.get("candidate_name") or "").strip()
    if name and not item.get("diet_flags"):
        out["diet_flags"] = _infer_diet_flags_from_name(name)
    return out

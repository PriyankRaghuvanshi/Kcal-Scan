from __future__ import annotations

from typing import Any, Dict, List, Tuple

from nutrition_mode import (
    NutritionMode,
    get_menu_item_score_weights,
    is_cut_mode,
    normalize_nutrition_mode,
)
from personalization_profiles import (
    goal_menu_macro_adjustment,
    get_goal_adjusted_menu_weights,
    normalize_personalization_goal,
    personalization_goal_value,
)
from restaurant_macro_estimator import estimate_restaurant_macros
from llm_explanation_copy import maybe_rewrite_explanation_copy
from llm_menu_parser import infer_place_menu_items_with_optional_llm
from menu_intelligence_store import (
    SOURCE_HEURISTIC,
    SOURCE_LLM_INFERRED,
    SOURCE_OCR_MENU,
    SOURCE_REVIEW_TEXT,
    SOURCE_SCRAPED_MENU,
    SOURCE_WEBSITE_MENU,
    SOURCE_WEBSITE_TEXT,
    get_menu_items_by_place_id,
    ingest_menu_intelligence,
)
from menu_ingestion import ingest_real_menu_for_place
from recommendation_feedback_store import get_place_item_feedback_signal


MENU_RECOMMENDATION_VERSION = "v1"

# Backward-compatible default weight export.
MENU_ITEM_SCORE_WEIGHTS: Dict[str, float] = get_menu_item_score_weights(NutritionMode.DEFAULT)

# Centralized place-type mappings for heuristic item generation (v1 deterministic fallback).
PLACE_MENU_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "grill_chicken",
        "tokens": ("grill", "grilled", "bbq", "kebab", "rotisserie", "chicken"),
        "items": [
            {"item_name": "Grilled chicken bowl", "estimated_calories": 520, "estimated_protein_g": 42},
            {"item_name": "Chicken salad plate", "estimated_calories": 430, "estimated_protein_g": 35},
            {"item_name": "Chicken wrap (light sauce)", "estimated_calories": 500, "estimated_protein_g": 34},
        ],
    },
    {
        "rule_id": "salad_poke",
        "tokens": ("salad", "poke", "healthy", "bowl", "vegan", "vegetarian"),
        "items": [
            {"item_name": "Protein poke bowl", "estimated_calories": 500, "estimated_protein_g": 36},
            {"item_name": "Chicken quinoa salad", "estimated_calories": 460, "estimated_protein_g": 34},
            {"item_name": "Tofu grain bowl", "estimated_calories": 480, "estimated_protein_g": 27},
        ],
    },
    {
        "rule_id": "sushi_japanese",
        "tokens": ("sushi", "japanese", "sashimi", "teriyaki", "ramen"),
        "items": [
            {"item_name": "Salmon sashimi set", "estimated_calories": 420, "estimated_protein_g": 38},
            {"item_name": "Chicken teriyaki rice bowl", "estimated_calories": 560, "estimated_protein_g": 36},
            {"item_name": "Tuna poke bowl", "estimated_calories": 520, "estimated_protein_g": 37},
        ],
    },
    {
        "rule_id": "mexican",
        "tokens": ("mexican", "burrito", "taco", "chipotle", "quesadilla"),
        "items": [
            {"item_name": "Chicken burrito bowl", "estimated_calories": 560, "estimated_protein_g": 40},
            {"item_name": "Steak fajita plate", "estimated_calories": 590, "estimated_protein_g": 39},
            {"item_name": "Chicken soft taco combo", "estimated_calories": 530, "estimated_protein_g": 32},
        ],
    },
    {
        "rule_id": "burger_fast_food",
        "tokens": ("burger", "fast_food", "fast food", "sandwich", "drive"),
        "items": [
            {"item_name": "Single grilled chicken burger", "estimated_calories": 470, "estimated_protein_g": 28},
            {"item_name": "Grilled chicken wrap", "estimated_calories": 500, "estimated_protein_g": 31},
            {"item_name": "6-piece nuggets (no fries)", "estimated_calories": 360, "estimated_protein_g": 21},
        ],
    },
    {
        "rule_id": "cafe",
        "tokens": ("cafe", "coffee", "brunch", "bakery"),
        "items": [
            {"item_name": "Egg and chicken plate", "estimated_calories": 430, "estimated_protein_g": 30},
            {"item_name": "Greek yogurt protein bowl", "estimated_calories": 390, "estimated_protein_g": 26},
            {"item_name": "Chicken sandwich (no fries)", "estimated_calories": 520, "estimated_protein_g": 32},
        ],
    },
    {
        "rule_id": "indian",
        "tokens": ("indian", "tandoori", "curry", "dal", "paneer", "biryani"),
        "items": [
            {"item_name": "Tandoori chicken + roti", "estimated_calories": 580, "estimated_protein_g": 40},
            {"item_name": "Dal + grilled paneer plate", "estimated_calories": 620, "estimated_protein_g": 33},
            {"item_name": "Chicken tikka bowl", "estimated_calories": 540, "estimated_protein_g": 38},
        ],
    },
    {
        "rule_id": "south_indian_temple_canteen",
        "tokens": ("south indian", "idli", "dosa", "sambar", "udupi", "canteen", "temple"),
        "items": [
            {"item_name": "Idli + sambar", "estimated_calories": 360, "estimated_protein_g": 13},
            {"item_name": "Plain dosa + sambar", "estimated_calories": 420, "estimated_protein_g": 14},
            {"item_name": "Veg meal (light rice + dal)", "estimated_calories": 520, "estimated_protein_g": 16},
        ],
    },
    {
        "rule_id": "thai_chinese",
        "tokens": ("thai", "chinese", "wok", "stir fry", "noodle"),
        "items": [
            {"item_name": "Chicken stir-fry + steamed rice", "estimated_calories": 560, "estimated_protein_g": 35},
            {"item_name": "Tofu stir-fry bowl", "estimated_calories": 520, "estimated_protein_g": 27},
            {"item_name": "Shrimp rice bowl", "estimated_calories": 540, "estimated_protein_g": 33},
        ],
    },
    {
        "rule_id": "pizza",
        "tokens": ("pizza", "pizzeria", "slice"),
        "items": [
            {"item_name": "2 thin-crust chicken slices", "estimated_calories": 590, "estimated_protein_g": 28},
            {"item_name": "Protein-topped personal pizza", "estimated_calories": 640, "estimated_protein_g": 32},
            {"item_name": "Chicken side salad + 1 slice", "estimated_calories": 500, "estimated_protein_g": 26},
        ],
    },
    {
        "rule_id": "mediterranean",
        "tokens": ("mediterranean", "shawarma", "falafel", "hummus"),
        "items": [
            {"item_name": "Chicken shawarma bowl", "estimated_calories": 540, "estimated_protein_g": 38},
            {"item_name": "Grilled kebab plate", "estimated_calories": 560, "estimated_protein_g": 40},
            {"item_name": "Falafel + salad combo", "estimated_calories": 520, "estimated_protein_g": 22},
        ],
    },
]

FALLBACK_ITEMS: List[Dict[str, Any]] = [
    {"item_name": "Lighter menu option", "estimated_calories": 520, "estimated_protein_g": 30},
    {"item_name": "Lean protein + simple side", "estimated_calories": 500, "estimated_protein_g": 28},
    {"item_name": "Lower-fried option with water", "estimated_calories": 540, "estimated_protein_g": 26},
]

# Centralized menu-item penalty weights by mode. These are additive penalties subtracted
# from the base nutrition score so high-protein, lower-calorie meals dominate ranking.
MENU_ITEM_PENALTY_WEIGHTS_BY_MODE: Dict[NutritionMode, Dict[str, float]] = {
    NutritionMode.DEFAULT: {
        "processing_penalty": 0.10,
        "fried_penalty": 0.07,
        "sugar_penalty": 0.05,
    },
    NutritionMode.CUT: {
        "processing_penalty": 0.13,
        "fried_penalty": 0.10,
        "sugar_penalty": 0.08,
    },
}

_FIBER_SATIETY_POSITIVE_TOKENS = (
    "salad",
    "vegetable",
    "veggie",
    "lentil",
    "dal",
    "bean",
    "chickpea",
    "brown rice",
    "quinoa",
    "wholegrain",
    "whole grain",
    "oats",
    "idli",
    "dosa",
    "sambar",
)

_ULTRA_PROCESSED_TOKENS = (
    "loaded",
    "double",
    "triple",
    "combo",
    "bucket",
    "family",
    "ultra",
    "processed",
    "frozen",
    "instant",
    "cheesy",
)

_FRIED_TOKENS = (
    "fried",
    "deep fried",
    "crispy",
    "tempura",
    "fries",
    "nuggets",
)

_SUGAR_TOKENS = (
    "shake",
    "soda",
    "cola",
    "sweet",
    "dessert",
    "pastry",
    "cake",
    "ice cream",
    "brownie",
    "muffin",
)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _place_text(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    name = str(payload.get("name") or "").strip().lower()
    address = str(payload.get("address") or payload.get("vicinity") or "").strip().lower()
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    type_text = " ".join(str(t or "").strip().lower() for t in types)
    return " ".join(x for x in [name, address, type_text] if x)


def _place_id(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    return str(payload.get("place_id") or payload.get("id") or "").strip()


def _place_name(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    return str(payload.get("name") or "").strip()


def _infer_cuisine(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    primary_type = str(payload.get("primary_type") or payload.get("primaryType") or "").strip()
    if primary_type:
        return primary_type.replace("_", " ").strip()

    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    for token in types:
        token_str = str(token or "").strip()
        if token_str and token_str not in {"restaurant", "food", "point_of_interest", "establishment"}:
            return token_str.replace("_", " ").strip()
    return ""


def _menu_item_source_from_menu_source(menu_source: Any) -> str:
    token = str(menu_source or "").strip().lower()
    if token in {
        "structured_menu",
        "menu_intelligence_store",
        "scraped_menu",
        "website_menu",
        "website_text",
        "review_text",
        "ocr_menu",
        "real_menu",
    }:
        return "real_menu"
    if token == "llm_inferred":
        return "llm_inferred"
    return "heuristic"


def _display_label_for_menu_item(source: str, confidence: float) -> str:
    conf = _clamp(_safe_float(confidence, 0.5), 0.0, 1.0)
    if source == "real_menu":
        return "Best Menu Item" if conf >= 0.72 else "Likely Better Choice"
    if source == "llm_inferred":
        if conf >= 0.75:
            return "Likely Better Choice"
        if conf >= 0.58:
            return "Suggested Lighter Option"
        if conf >= 0.45:
            return "Estimated Best Fit"
        return "Needs Menu Check"
    if conf >= 0.7:
        return "Estimated Best Fit"
    if conf >= 0.52:
        return "Suggested Lighter Option"
    return "Needs Menu Check"


def _coarse_item_name_for_context(cuisine_hint: str) -> str:
    text = str(cuisine_hint or "").strip().lower()
    if any(token in text for token in ("south indian", "idli", "dosa", "udupi", "temple", "canteen")):
        return "Idli or plain dosa-style option"
    if "indian" in text:
        return "Simpler tandoori or dal + roti option"
    if any(token in text for token in ("cafe", "coffee", "bakery", "brunch")):
        return "Lighter cafe meal option"
    if any(token in text for token in ("burger", "fast food", "fast_food", "fried chicken")):
        return "Lighter grilled or single-item option"
    if "pizza" in text:
        return "Lighter thin-crust option"
    if any(token in text for token in ("sushi", "japanese")):
        return "Sashimi or simple rice-bowl option"
    if any(token in text for token in ("mexican", "burrito", "taco")):
        return "Lighter bowl or taco-style option"
    return "Lighter menu option"


def _final_item_name(
    *,
    item_name: str,
    source: str,
    confidence: float,
    cuisine_hint: str,
) -> str:
    text = str(item_name or "").strip()
    if not text:
        return _coarse_item_name_for_context(cuisine_hint)
    if source == "real_menu":
        return text

    lower_item = text.lower()
    lower_cuisine = str(cuisine_hint or "").lower()
    is_south_indian_context = any(
        token in lower_cuisine for token in ("south indian", "idli", "dosa", "udupi", "temple", "canteen")
    )

    # Avoid unrealistic western fallback names in cuisine-specific contexts.
    if is_south_indian_context and any(token in lower_item for token in ("grilled protein bowl", "protein wrap")):
        return "Idli or plain dosa-style option"

    if _safe_float(confidence, 0.0) < 0.55:
        return _coarse_item_name_for_context(cuisine_hint)
    return text


def _order_type_for_item(source: str, confidence: float) -> str:
    conf = _clamp(_safe_float(confidence, 0.5), 0.0, 1.0)
    if source == "real_menu" and conf >= 0.72:
        return "exact"
    if conf >= 0.56:
        return "likely"
    return "estimated"


def _build_swap_plan(
    *,
    item_name: str,
    cuisine_hint: str,
    source: str,
    confidence: float,
    calories: int,
) -> Dict[str, Any]:
    text = str(item_name or "").strip().lower()
    cuisine = str(cuisine_hint or "").strip().lower()
    skip_items: List[str] = []
    add_items: List[str] = []

    if any(token in text for token in ("fries", "fried", "crispy", "combo", "bucket")):
        skip_items.append("fried sides")
    if any(token in text for token in ("shake", "soda", "cola", "dessert", "pastry")):
        skip_items.append("sugary drinks or desserts")
    if any(token in cuisine for token in ("indian", "south indian", "canteen", "temple")):
        skip_items.append("creamy or deep-fried extras")
        add_items.append("salad or dal-based side")
    if any(token in cuisine for token in ("burger", "fast food", "fast_food")):
        skip_items.append("fries and sugary drinks")
        add_items.append("extra salad or lean protein")
    if "pizza" in cuisine or "pizza" in text:
        skip_items.append("cheesy dips")
        add_items.append("side salad")
    if any(token in cuisine for token in ("cafe", "bakery", "coffee")):
        skip_items.append("pastries")
        add_items.append("water or unsweetened drink")

    if calories >= 700 and "large portion" not in skip_items:
        skip_items.append("large portions")
    if not add_items:
        add_items.append("extra vegetables")
    if not skip_items:
        skip_items.append("heavy sauces")

    # Deduplicate while preserving order.
    seen_skip = set()
    dedup_skip: List[str] = []
    for item in skip_items:
        token = str(item or "").strip().lower()
        if not token or token in seen_skip:
            continue
        seen_skip.add(token)
        dedup_skip.append(str(item).strip())

    seen_add = set()
    dedup_add: List[str] = []
    for item in add_items:
        token = str(item or "").strip().lower()
        if not token or token in seen_add:
            continue
        seen_add.add(token)
        dedup_add.append(str(item).strip())

    order_type = _order_type_for_item(source, confidence)
    if order_type == "exact":
        swap_suggestion = f"Order this, skip {dedup_skip[0]}, add {dedup_add[0]}."
    elif order_type == "likely":
        swap_suggestion = f"Likely best move: pick this style, skip {dedup_skip[0]}."
    else:
        swap_suggestion = f"Suggested lighter option: avoid {dedup_skip[0]} and add {dedup_add[0]}."

    return {
        "order_type": order_type,
        "swap_suggestion": swap_suggestion,
        "skip_items": dedup_skip[:3],
        "add_items": dedup_add[:3],
    }


def _ingest_menu_snapshot(
    place: Dict[str, Any],
    menu_items: List[Dict[str, Any]],
    source: str,
) -> None:
    place_id = _place_id(place)
    if not place_id:
        return

    try:
        ingest_menu_intelligence(
            place_id=place_id,
            restaurant_name=_place_name(place),
            cuisine=_infer_cuisine(place),
            menu_items=menu_items,
            source=source,
        )
    except Exception:
        # Persistence should never break recommendation responses.
        pass


def _menu_source_items(place: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    payload = place if isinstance(place, dict) else {}
    candidates: List[Any] = []

    for key in ("menu_items", "menuItems", "menu", "items"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            candidates = value
            break

    normalized: List[Dict[str, Any]] = []
    for item in candidates:
        if isinstance(item, str) and item.strip():
            normalized.append({"item_name": item.strip()})
            continue

        if not isinstance(item, dict):
            continue

        item_name = str(item.get("item_name") or item.get("name") or item.get("title") or "").strip()
        if not item_name:
            continue

        normalized.append(
            {
                "item_name": item_name,
                "estimated_calories": int(_safe_float(item.get("estimated_calories", item.get("calories")), 0) or 0),
                "estimated_protein_g": int(_safe_float(item.get("estimated_protein_g", item.get("protein_g")), 0) or 0),
                "estimated_carbs_g": int(_safe_float(item.get("estimated_carbs_g", item.get("carbs_g")), 0) or 0),
                "estimated_fat_g": int(_safe_float(item.get("estimated_fat_g", item.get("fat_g")), 0) or 0),
                "estimated_satiety": str(item.get("estimated_satiety") or "").strip().lower(),
                "confidence": float(_safe_float(item.get("confidence"), 0.0) or 0.0),
                "menu_confidence": float(_safe_float(item.get("menu_confidence", item.get("confidence")), 0.0) or 0.0),
                "source": str(item.get("source") or item.get("menu_source") or "").strip().lower(),
                "menu_source": str(item.get("menu_source") or item.get("source") or "").strip().lower(),
                "source_url": str(item.get("source_url") or "").strip(),
                "extraction_method": str(item.get("extraction_method") or "").strip(),
                "parse_method": str(item.get("parse_method") or "").strip(),
                "parsed_via": str(item.get("parsed_via") or "").strip(),
                "raw_text_snippet": str(item.get("raw_text_snippet") or "").strip()[:180],
                "category": str(item.get("category") or "").strip(),
                "likely_protein": str(item.get("likely_protein") or "").strip(),
                "likely_carbs": item.get("likely_carbs") if isinstance(item.get("likely_carbs"), list) else [],
                "likely_fats": item.get("likely_fats") if isinstance(item.get("likely_fats"), list) else [],
                "health_signals": item.get("health_signals") if isinstance(item.get("health_signals"), list) else [],
            }
        )

    return normalized, bool(normalized)


def _rule_match(place_text: str) -> Dict[str, Any] | None:
    best_rule = None
    best_hits = 0
    for rule in PLACE_MENU_RULES:
        hits = sum(1 for token in rule.get("tokens", ()) if token in place_text)
        if hits > best_hits:
            best_hits = hits
            best_rule = rule
    return best_rule


def _heuristic_menu_items(place: Dict[str, Any]) -> List[Dict[str, Any]]:
    place_text = _place_text(place)
    rule = _rule_match(place_text)
    if rule and isinstance(rule.get("items"), list):
        return [dict(item) for item in rule["items"][:3]]
    return [dict(item) for item in FALLBACK_ITEMS]


def _infer_nutrition_from_name(item_name: str) -> Tuple[int, int]:
    text = str(item_name or "").strip().lower()
    kcal = 520
    protein = 30

    if any(token in text for token in ("salad", "soup")):
        kcal -= 90
        protein -= 2
    if any(token in text for token in ("bowl", "grilled", "chicken", "tikka", "kebab", "shawarma", "sashimi", "steak", "shrimp")):
        protein += 9
    if any(token in text for token in ("burger", "pizza", "fried", "crispy", "butter", "creamy", "loaded", "nachos")):
        kcal += 140
        protein -= 4
    if any(token in text for token in ("tofu", "paneer", "dal", "lentil", "bean")):
        protein += 4

    return int(_clamp(kcal, 300, 900)), int(_clamp(protein, 14, 60))


def _satiety_label(calories: int, protein_g: int, requested_label: str | None = None) -> str:
    if requested_label in {"high", "medium", "low"}:
        return str(requested_label)

    if protein_g >= 35 and calories <= 650:
        return "high"
    if protein_g >= 24 and calories <= 720:
        return "medium"
    return "low"


def _fiber_satiety_score(
    *,
    item_text: str,
    satiety_label: str,
    health_signals: List[str],
    calories: int,
    protein_g: int,
) -> float:
    score = 50.0
    if satiety_label == "high":
        score += 24.0
    elif satiety_label == "medium":
        score += 12.0
    if any(token in item_text for token in _FIBER_SATIETY_POSITIVE_TOKENS):
        score += 12.0
    if "high_fiber" in health_signals:
        score += 10.0
    if "fried" in health_signals or "deep_fried" in health_signals:
        score -= 10.0
    if calories <= 620 and protein_g >= 30:
        score += 6.0
    return _clamp(score, 20.0, 100.0)


def _penalty_scores(item_text: str, health_signals: List[str]) -> Dict[str, float]:
    processing_penalty = 0.0
    fried_penalty = 0.0
    sugar_penalty = 0.0

    if any(token in item_text for token in _ULTRA_PROCESSED_TOKENS):
        processing_penalty += 32.0
    if "calorie_dense" in health_signals:
        processing_penalty += 20.0
    if "creamy_sauce" in health_signals:
        processing_penalty += 14.0
    if "sugary_drink" in health_signals:
        processing_penalty += 10.0

    if any(token in item_text for token in _FRIED_TOKENS):
        fried_penalty += 36.0
    if "fried" in health_signals:
        fried_penalty += 24.0
    if "deep_fried" in health_signals:
        fried_penalty += 20.0

    if any(token in item_text for token in _SUGAR_TOKENS):
        sugar_penalty += 34.0
    if "sugary_drink" in health_signals:
        sugar_penalty += 28.0

    return {
        "processing_penalty": _clamp(processing_penalty, 0.0, 100.0),
        "fried_penalty": _clamp(fried_penalty, 0.0, 100.0),
        "sugar_penalty": _clamp(sugar_penalty, 0.0, 100.0),
    }


def _sorted_scored_items(scored_items: List[Dict[str, Any]], mode: NutritionMode | str) -> List[Dict[str, Any]]:
    resolved_mode = normalize_nutrition_mode(mode)

    if is_cut_mode(resolved_mode):
        return sorted(
            scored_items,
            key=lambda row: (
                int(row.get("item_score", 0)),
                int(row.get("item_score_breakdown", {}).get("calorie_control", 0)),
                int(row.get("item_score_breakdown", {}).get("protein_density", 0)),
            ),
            reverse=True,
        )

    return sorted(scored_items, key=lambda row: int(row.get("item_score", 0)), reverse=True)


def score_menu_item(
    item: Dict[str, Any],
    context: Dict[str, Any] | None = None,
    mode: NutritionMode | str | None = None,
    personalization_goal: Any = None,
) -> Dict[str, Any]:
    payload = item if isinstance(item, dict) else {}
    context_payload = context if isinstance(context, dict) else {}

    resolved_mode = normalize_nutrition_mode(mode or context_payload.get("mode"))
    resolved_goal = normalize_personalization_goal(personalization_goal or context_payload.get("personalization_goal"))
    goal_value = personalization_goal_value(resolved_goal)
    cut_mode_active = is_cut_mode(resolved_mode)
    weights = get_menu_item_score_weights(resolved_mode)
    if resolved_goal:
        weights = get_goal_adjusted_menu_weights(weights, resolved_goal)

    item_name = str(payload.get("item_name") or payload.get("name") or "Menu item").strip() or "Menu item"
    raw_item_name = item_name
    raw_item_source = str(
        payload.get("menu_item_source")
        or payload.get("menu_source")
        or payload.get("source")
        or _menu_item_source_from_menu_source(context_payload.get("menu_source"))
    ).strip().lower()
    if raw_item_source in {
        "real_menu",
        "structured_menu",
        "menu_intelligence_store",
        "scraped_menu",
        "user_scan",
        "website_menu",
        "website_text",
        "review_text",
        "ocr_menu",
    }:
        menu_item_source = "real_menu"
    elif raw_item_source in {"llm_inferred", "llm"}:
        menu_item_source = "llm_inferred"
    else:
        menu_item_source = "heuristic"
    source_confidence = _safe_float(
        payload.get("menu_item_confidence", payload.get("menu_confidence", payload.get("confidence"))),
        0.0,
    )
    source_url = str(payload.get("source_url") or "").strip()
    extraction_method = str(payload.get("extraction_method") or "").strip()
    parse_method = str(payload.get("parse_method") or "").strip()
    parsed_via = str(payload.get("parsed_via") or "").strip()
    raw_text_snippet = str(payload.get("raw_text_snippet") or "").strip()[:180]
    category = str(payload.get("category") or "").strip()
    likely_protein = str(payload.get("likely_protein") or "").strip()
    likely_carbs = payload.get("likely_carbs") if isinstance(payload.get("likely_carbs"), list) else []
    likely_fats = payload.get("likely_fats") if isinstance(payload.get("likely_fats"), list) else []
    health_signals = payload.get("health_signals") if isinstance(payload.get("health_signals"), list) else []

    input_calories = int(_safe_float(payload.get("estimated_calories", payload.get("calories")), 0) or 0)
    input_protein = int(_safe_float(payload.get("estimated_protein_g", payload.get("protein_g")), 0) or 0)

    macro_estimate = estimate_restaurant_macros(
        item_name=item_name,
        cuisine_hint=str(context_payload.get("cuisine_hint") or context_payload.get("place_text") or ""),
        place=context_payload.get("place") if isinstance(context_payload.get("place"), dict) else None,
        input_calories=input_calories if input_calories > 0 else None,
        input_protein_g=input_protein if input_protein > 0 else None,
    )

    calories = int(_safe_float(macro_estimate.get("estimated_calories"), 520) or 520)
    protein_g = int(_safe_float(macro_estimate.get("estimated_protein_g"), 30) or 30)
    carbs_g = int(_safe_float(macro_estimate.get("estimated_carbs_g"), 45) or 45)
    fat_g = int(_safe_float(macro_estimate.get("estimated_fat_g"), 18) or 18)
    satiety = str(macro_estimate.get("estimated_satiety") or "medium")
    nutrition_conf = float(_safe_float(macro_estimate.get("macro_confidence"), 0.56) or 0.56)
    macro_estimation_version = str(macro_estimate.get("macro_estimation_version") or "v1")

    protein_density = _clamp((protein_g / max(1.0, calories)) * 1450.0, 20.0, 100.0)
    calorie_control = _clamp(100.0 - abs(float(calories) - 500.0) / 4.6, 14.0, 100.0)
    satiety = _satiety_label(calories, protein_g, satiety)
    text = item_name.lower()
    health_signals = [str(x).strip().lower() for x in (health_signals or []) if str(x).strip()]
    fiber_satiety = _fiber_satiety_score(
        item_text=text,
        satiety_label=satiety,
        health_signals=health_signals,
        calories=calories,
        protein_g=protein_g,
    )

    fat_loss_score = (protein_density * 0.46) + (calorie_control * 0.30) + (fiber_satiety * 0.24)
    if any(token in text for token in ("fried", "crispy", "loaded", "creamy", "double", "extra cheese", "shake")):
        fat_loss_score -= 16.0
    if any(token in text for token in ("grilled", "salad", "bowl", "sashimi", "tandoori", "stir-fry", "lean")):
        fat_loss_score += 8.0
    fat_loss_score = _clamp(fat_loss_score, 10.0, 100.0)

    penalty_weights = MENU_ITEM_PENALTY_WEIGHTS_BY_MODE.get(resolved_mode, MENU_ITEM_PENALTY_WEIGHTS_BY_MODE[NutritionMode.DEFAULT])
    penalties = _penalty_scores(text, health_signals)
    weighted_penalty = (
        penalties["processing_penalty"] * penalty_weights["processing_penalty"]
        + penalties["fried_penalty"] * penalty_weights["fried_penalty"]
        + penalties["sugar_penalty"] * penalty_weights["sugar_penalty"]
    )

    item_score = (
        protein_density * weights["protein_density"]
        + calorie_control * weights["calorie_control"]
        + fiber_satiety * weights["satiety"]
        + fat_loss_score * weights["fat_loss_friendliness"]
    )
    item_score -= weighted_penalty

    # Cut mode applies stricter calorie guardrails while still rewarding high protein.
    if cut_mode_active:
        if calories >= 700:
            item_score -= 10.0
        elif calories >= 620:
            item_score -= 5.0

        if protein_g >= 40 and calories <= 600:
            item_score += 3.0

    item_score += goal_menu_macro_adjustment(
        resolved_goal,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )

    feedback_signal: Dict[str, Any] = {}
    feedback_adjustment = 0.0
    feedback_events_count = 0
    feedback_follow_rate = 0.0
    feedback_signal_confidence = 0.0
    feedback_signal_source = "none"

    place_ctx = context_payload.get("place") if isinstance(context_payload.get("place"), dict) else {}
    feedback_place_id = str(place_ctx.get("place_id") or place_ctx.get("id") or "").strip()

    if feedback_place_id:
        try:
            feedback_signal = get_place_item_feedback_signal(feedback_place_id, item_name)
            feedback_adjustment = float(_safe_float(feedback_signal.get("score_adjustment"), 0.0) or 0.0)
            feedback_events_count = int(_safe_float(feedback_signal.get("events_count"), 0.0) or 0)
            feedback_follow_rate = float(_safe_float(feedback_signal.get("follow_rate"), 0.0) or 0.0)
            feedback_signal_confidence = float(_safe_float(feedback_signal.get("signal_confidence"), 0.0) or 0.0)
            feedback_signal_source = str(feedback_signal.get("signal_source") or "none")
            item_score += feedback_adjustment
        except Exception:
            feedback_signal = {}

    item_score = int(round(_clamp(item_score, 1.0, 100.0)))

    fat_loss_threshold = 74 if cut_mode_active else 70
    fat_loss_signal_threshold = 68 if cut_mode_active else 65
    fat_loss_friendly = bool(item_score >= fat_loss_threshold and fat_loss_score >= fat_loss_signal_threshold)

    cut_friendly = bool(
        cut_mode_active
        and item_score >= 74
        and calorie_control >= 68
        and protein_density >= 60
    )

    tags: List[str] = []
    if protein_density >= 78:
        tags.append("high_protein")
    if calorie_control >= 72:
        tags.append("calorie_control")
    if satiety == "high":
        tags.append("high_satiety")
    if fiber_satiety >= 72:
        tags.append("fiber_satiety")
    if fat_loss_friendly:
        tags.append("fat_loss_friendly")
    if penalties["processing_penalty"] >= 25 or penalties["fried_penalty"] >= 25 or penalties["sugar_penalty"] >= 25:
        tags.append("processed_penalty")
    if cut_mode_active:
        tags.append("cut_mode")
    if cut_friendly:
        tags.append("cut_friendly")
    if goal_value:
        tags.append(f"goal_{goal_value}")
    if feedback_events_count >= 5 and feedback_follow_rate >= 0.60:
        tags.append("recommendation_proven")
    elif feedback_events_count >= 3 and feedback_adjustment >= 1.0:
        tags.append("feedback_positive")
    elif feedback_events_count >= 3 and feedback_adjustment <= -1.0:
        tags.append("feedback_negative")
    if not tags:
        tags.append("balanced_option")

    short_reason = "High protein and filling for moderate calories."
    if not fat_loss_friendly:
        short_reason = "Decent fallback; watch portion and sauces."
    elif calorie_control < 60:
        short_reason = "Strong protein, but portion control matters."
    elif fiber_satiety >= 72:
        short_reason = "High protein with better satiety for fewer calories."

    cut_warning = ""
    if cut_mode_active:
        if cut_friendly:
            short_reason = "Cut-friendly: high protein for manageable calories."
        else:
            if calories > 620:
                cut_warning = "Too calorie-dense for cut days."
            elif protein_g < 28:
                cut_warning = "Protein is low for a cut-focused meal."
            else:
                cut_warning = "Use portion control for cut days."
            short_reason = "Use care on cut days; choose lighter swaps if available."

    confidence = nutrition_conf
    if context_payload.get("menu_source") == "heuristic":
        confidence -= 0.12
    elif context_payload.get("menu_source") == "llm_inferred":
        confidence -= 0.06
    if context_payload.get("place_text"):
        place_text = str(context_payload.get("place_text") or "")
        if any(token in place_text for token in ("grill", "salad", "sushi", "healthy", "bowl")):
            confidence += 0.05

    if cut_mode_active:
        if cut_friendly:
            confidence += 0.03
        elif calories > 650:
            confidence -= 0.08

    confidence = round(_clamp(confidence, 0.35, 0.93), 2)
    source_anchor = source_confidence if source_confidence > 0 else confidence
    if menu_item_source == "real_menu":
        # Real extracted menu evidence should dominate confidence so exact order labels are possible.
        blended_confidence = (confidence * 0.25) + (source_anchor * 0.75)
    elif menu_item_source == "llm_inferred":
        blended_confidence = (confidence * 0.64) + (source_anchor * 0.36)
    else:
        blended_confidence = (confidence * 0.72) + (source_anchor * 0.28)

    menu_item_confidence = round(_clamp(blended_confidence, 0.25, 0.97), 2)
    cuisine_hint = str(context_payload.get("cuisine_hint") or context_payload.get("place_text") or "")
    display_label = _display_label_for_menu_item(menu_item_source, menu_item_confidence)
    item_name = _final_item_name(
        item_name=item_name,
        source=menu_item_source,
        confidence=menu_item_confidence,
        cuisine_hint=cuisine_hint,
    )
    swap_plan = _build_swap_plan(
        item_name=item_name,
        cuisine_hint=cuisine_hint,
        source=menu_item_source,
        confidence=menu_item_confidence,
        calories=calories,
    )
    place_ctx = context_payload.get("place") if isinstance(context_payload.get("place"), dict) else {}
    place_name = str(place_ctx.get("name") or "").strip()
    rewritten = maybe_rewrite_explanation_copy(
        place_name=place_name,
        cuisine=cuisine_hint,
        recommended_order=raw_item_name,
        estimated_calories=calories,
        estimated_protein_g=protein_g,
        goal=goal_value,
        confidence=confidence,
        recommendation_source=menu_item_source,
        menu_item_confidence=menu_item_confidence,
        base_why_this_works=short_reason,
        base_short_reason=short_reason,
    )
    short_reason = str(rewritten.get("short_reason") or short_reason)
    why_this_works = str(rewritten.get("why_this_works") or short_reason)
    copy_method = str(rewritten.get("copy_method") or "deterministic")
    copy_confidence = round(_clamp(_safe_float(rewritten.get("copy_confidence"), menu_item_confidence), 0.2, 0.95), 2)
    copy_version = str(rewritten.get("copy_version") or "v1")

    return {
        "item_name": item_name,
        "raw_item_name": raw_item_name,
        "item_score": item_score,
        "item_score_breakdown": {
            "protein_density": int(round(_clamp(protein_density, 0.0, 100.0))),
            "calorie_control": int(round(_clamp(calorie_control, 0.0, 100.0))),
            "satiety": int(round(_clamp(fiber_satiety, 0.0, 100.0))),
            "fat_loss_friendliness": int(round(_clamp(fat_loss_score, 0.0, 100.0))),
            # v2 explicit dimensions (keeps legacy keys above for compatibility)
            "protein_density_score": int(round(_clamp(protein_density, 0.0, 100.0))),
            "calorie_control_score": int(round(_clamp(calorie_control, 0.0, 100.0))),
            "fiber_satiety_score": int(round(_clamp(fiber_satiety, 0.0, 100.0))),
            "fat_loss_score": int(round(_clamp(fat_loss_score, 0.0, 100.0))),
            "processing_penalty": int(round(_clamp(penalties["processing_penalty"], 0.0, 100.0))),
            "fried_penalty": int(round(_clamp(penalties["fried_penalty"], 0.0, 100.0))),
            "sugar_penalty": int(round(_clamp(penalties["sugar_penalty"], 0.0, 100.0))),
        },
        "estimated_calories": int(calories),
        "estimated_protein_g": int(protein_g),
        "estimated_carbs_g": int(carbs_g),
        "estimated_fat_g": int(fat_g),
        "estimated_satiety": satiety,
        "macro_confidence": round(float(nutrition_conf), 2),
        "macro_estimation_version": macro_estimation_version,
        "fat_loss_friendly": fat_loss_friendly,
        "short_reason": short_reason,
        "why_this_works": why_this_works,
        "confidence": confidence,
        "order_confidence": menu_item_confidence,
        "menu_item_source": menu_item_source,
        "menu_item_confidence": menu_item_confidence,
        "menu_source": menu_item_source,
        "menu_confidence": menu_item_confidence,
        "order_type": swap_plan["order_type"],
        "swap_suggestion": swap_plan["swap_suggestion"],
        "skip_items": swap_plan["skip_items"],
        "add_items": swap_plan["add_items"],
        "source_url": source_url,
        "extraction_method": extraction_method,
        "parse_method": parse_method,
        "parsed_via": parsed_via,
        "raw_text_snippet": raw_text_snippet,
        "category": category,
        "likely_protein": likely_protein,
        "likely_carbs": likely_carbs[:4],
        "likely_fats": likely_fats[:4],
        "health_signals": health_signals[:6],
        "display_label": display_label,
        "copy_method": copy_method,
        "copy_confidence": copy_confidence,
        "copy_version": copy_version,
        "recommendation_tags": tags,
        "recommendation_version": MENU_RECOMMENDATION_VERSION,
        "cut_mode_active": cut_mode_active,
        "cut_friendly": cut_friendly,
        "cut_warning": cut_warning,
        "feedback_events_count": feedback_events_count,
        "feedback_follow_rate": round(_clamp(feedback_follow_rate, 0.0, 1.0), 3),
        "feedback_signal_confidence": round(_clamp(feedback_signal_confidence, 0.0, 1.0), 3),
        "feedback_score_adjustment": round(float(feedback_adjustment), 3),
        "feedback_signal_source": feedback_signal_source,
        "personalization_goal": goal_value,
    }


def rank_menu_items_for_place(
    place: Dict[str, Any],
    menu_items: List[Dict[str, Any]],
    mode: NutritionMode | str = NutritionMode.DEFAULT,
    personalization_goal: Any = None,
) -> List[Dict[str, Any]]:
    place_text = _place_text(place)
    cuisine_hint = _infer_cuisine(place)
    if not isinstance(menu_items, list) or not menu_items:
        return []

    resolved_mode = normalize_nutrition_mode(mode)

    scored: List[Dict[str, Any]] = []
    for item in menu_items:
        if not isinstance(item, dict):
            continue
        out = score_menu_item(
            item,
            context={
                "place_text": place_text,
                "cuisine_hint": cuisine_hint,
                "menu_source": "structured_menu",
                "mode": resolved_mode.value,
                "place": place,
                "personalization_goal": personalization_goal,
            },
            mode=resolved_mode,
            personalization_goal=personalization_goal,
        )
        scored.append(out)

    scored = _sorted_scored_items(scored, mode=resolved_mode)
    return scored[:3]


def recommend_menu_items_for_place(
    place: Dict[str, Any],
    health_score: float | None = None,
    mode: NutritionMode | str = NutritionMode.DEFAULT,
    personalization_goal: Any = None,
) -> Dict[str, Any]:
    source_items, has_structured_menu = _menu_source_items(place)

    resolved_mode = normalize_nutrition_mode(mode)
    resolved_goal = normalize_personalization_goal(personalization_goal)
    goal_value = personalization_goal_value(resolved_goal)
    cut_mode_active = is_cut_mode(resolved_mode)

    place_id = _place_id(place)
    stored_items = get_menu_items_by_place_id(place_id) if place_id and not has_structured_menu else []
    stored_has_real_menu = any(
        str((row or {}).get("source") or (row or {}).get("menu_source") or "").strip().lower()
        in {
            "real_menu",
            "structured_menu",
            "menu_intelligence_store",
            "scraped_menu",
            "user_scan",
            SOURCE_WEBSITE_MENU,
            SOURCE_WEBSITE_TEXT,
            SOURCE_REVIEW_TEXT,
            SOURCE_OCR_MENU,
        }
        for row in stored_items
        if isinstance(row, dict)
    )

    ingestion_bundle: Dict[str, Any] = {}
    if not has_structured_menu and (not stored_items or not stored_has_real_menu):
        try:
            ingestion_bundle = ingest_real_menu_for_place(place, max_items=12)
        except Exception:
            ingestion_bundle = {}

    ingested_items = (
        ingestion_bundle.get("menu_items")
        if isinstance(ingestion_bundle.get("menu_items"), list)
        else []
    )

    if has_structured_menu:
        menu_source = "structured_menu"
        menu_items = source_items
        _ingest_menu_snapshot(place, menu_items, SOURCE_SCRAPED_MENU)
    elif ingested_items:
        menu_source = str(ingestion_bundle.get("menu_source") or SOURCE_WEBSITE_TEXT)
        menu_items = ingested_items
    elif stored_items:
        menu_source = "menu_intelligence_store"
        menu_items = stored_items
    else:
        heuristic_items = _heuristic_menu_items(place)
        llm_bundle = infer_place_menu_items_with_optional_llm(
            place=place,
            heuristic_items=heuristic_items,
            max_items=3,
        )
        menu_source = "llm_inferred" if str(llm_bundle.get("parse_method") or "") == "llm_inferred" else "heuristic"
        parsed_items = llm_bundle.get("parsed_items") if isinstance(llm_bundle.get("parsed_items"), list) else []
        menu_items = parsed_items if parsed_items else heuristic_items
        _ingest_menu_snapshot(
            place,
            menu_items,
            SOURCE_LLM_INFERRED if menu_source == "llm_inferred" else SOURCE_HEURISTIC,
        )

    place_text = _place_text(place)
    cuisine_hint = _infer_cuisine(place)
    scored_items: List[Dict[str, Any]] = []
    for item in menu_items:
        scored = score_menu_item(
            item,
            context={
                "place_text": place_text,
                "cuisine_hint": cuisine_hint,
                "menu_source": menu_source,
                "mode": resolved_mode.value,
                "place": place,
                "personalization_goal": personalization_goal,
            },
            mode=resolved_mode,
            personalization_goal=personalization_goal,
        )

        # Nudge rank by venue-level health score when available, without overriding item fundamentals.
        if health_score is not None:
            hs = _clamp(_safe_float(health_score, 5.0), 1.0, 10.0)
            bump = (hs - 5.0) * (1.4 if cut_mode_active else 1.2)
            scored["item_score"] = int(_clamp(int(scored["item_score"]) + bump, 1.0, 100.0))
            scored["fat_loss_friendly"] = bool(scored["item_score"] >= (74 if cut_mode_active else 70))
            if cut_mode_active:
                scored["cut_friendly"] = bool(scored["item_score"] >= 74)

        scored_items.append(scored)

    scored_items = _sorted_scored_items(scored_items, mode=resolved_mode)
    top_items = scored_items[:3]
    top_item = top_items[0] if top_items else None
    menu_confidence = round(
        _safe_float(
            ingestion_bundle.get("menu_confidence"),
            _safe_float(
                (top_item or {}).get("menu_item_confidence"),
                _safe_float((top_item or {}).get("confidence"), 0.0),
            ),
        ),
        2,
    )
    extraction_method = str(
        ingestion_bundle.get("extraction_method")
        or ((top_item or {}).get("extraction_method") if isinstance(top_item, dict) else "")
        or ""
    ).strip()
    parse_method = str(
        ingestion_bundle.get("parse_method")
        or ((top_item or {}).get("parse_method") if isinstance(top_item, dict) else "")
        or ""
    ).strip()
    source_url = str(
        ingestion_bundle.get("source_url")
        or ((top_item or {}).get("source_url") if isinstance(top_item, dict) else "")
        or ""
    ).strip()

    return {
        "menu_item_scoring_available": bool(top_items),
        "menu_items_source": menu_source,
        "menu_source": menu_source,
        "menu_confidence": menu_confidence,
        "extraction_method": extraction_method,
        "parse_method": parse_method,
        "source_url": source_url,
        "menu_ingestion_version": str(
            ingestion_bundle.get("menu_ingestion_version")
            or MENU_RECOMMENDATION_VERSION
        ),
        "menu_intelligence_place_id": place_id,
        "menu_intelligence_available": bool(place_id),
        "top_menu_items": top_items,
        "best_menu_items": top_items,
        "top_menu_item": top_item,
        "top_item": str(top_item.get("item_name")) if isinstance(top_item, dict) else "",
        "cut_mode_active": cut_mode_active,
        "personalization_goal": goal_value,
    }

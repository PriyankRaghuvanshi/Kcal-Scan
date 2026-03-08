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
from menu_intelligence_store import (
    SOURCE_HEURISTIC,
    SOURCE_SCRAPED_MENU,
    get_menu_items_by_place_id,
    ingest_menu_intelligence,
)
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
    {"item_name": "Grilled protein bowl", "estimated_calories": 520, "estimated_protein_g": 34},
    {"item_name": "Chicken salad plate", "estimated_calories": 450, "estimated_protein_g": 30},
    {"item_name": "Protein wrap (light sauce)", "estimated_calories": 500, "estimated_protein_g": 31},
]


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

    protein_density = _clamp((protein_g / max(1.0, calories)) * 1400.0, 25.0, 100.0)
    calorie_control = _clamp(100.0 - abs(float(calories) - 520.0) / 4.8, 20.0, 100.0)
    satiety = _satiety_label(calories, protein_g, satiety)
    satiety_score = 92.0 if satiety == "high" else 72.0 if satiety == "medium" else 48.0

    text = item_name.lower()
    fat_loss = (protein_density * 0.44) + (calorie_control * 0.34) + (satiety_score * 0.22)
    if any(token in text for token in ("fried", "crispy", "loaded", "creamy", "double", "extra cheese", "shake")):
        fat_loss -= 16.0
    if any(token in text for token in ("grilled", "salad", "bowl", "sashimi", "tandoori", "stir-fry", "lean")):
        fat_loss += 8.0
    fat_loss = _clamp(fat_loss, 10.0, 100.0)

    item_score = (
        protein_density * weights["protein_density"]
        + calorie_control * weights["calorie_control"]
        + satiety_score * weights["satiety"]
        + fat_loss * weights["fat_loss_friendliness"]
    )

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
    fat_loss_friendly = bool(item_score >= fat_loss_threshold and fat_loss >= fat_loss_signal_threshold)

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
    if fat_loss_friendly:
        tags.append("fat_loss_friendly")
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

    return {
        "item_name": item_name,
        "item_score": item_score,
        "item_score_breakdown": {
            "protein_density": int(round(_clamp(protein_density, 0.0, 100.0))),
            "calorie_control": int(round(_clamp(calorie_control, 0.0, 100.0))),
            "satiety": int(round(_clamp(satiety_score, 0.0, 100.0))),
            "fat_loss_friendliness": int(round(_clamp(fat_loss, 0.0, 100.0))),
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
        "confidence": confidence,
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

    if stored_items:
        menu_source = "menu_intelligence_store"
        menu_items = stored_items
    elif has_structured_menu:
        menu_source = "structured_menu"
        menu_items = source_items
        _ingest_menu_snapshot(place, menu_items, SOURCE_SCRAPED_MENU)
    else:
        menu_source = "heuristic"
        menu_items = _heuristic_menu_items(place)
        _ingest_menu_snapshot(place, menu_items, SOURCE_HEURISTIC)

    place_text = _place_text(place)
    scored_items: List[Dict[str, Any]] = []
    for item in menu_items:
        scored = score_menu_item(
            item,
            context={
                "place_text": place_text,
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

    return {
        "menu_item_scoring_available": bool(top_items),
        "menu_items_source": menu_source,
        "menu_intelligence_place_id": place_id,
        "menu_intelligence_available": bool(place_id),
        "top_menu_items": top_items,
        "best_menu_items": top_items,
        "top_menu_item": top_item,
        "top_item": str(top_item.get("item_name")) if isinstance(top_item, dict) else "",
        "cut_mode_active": cut_mode_active,
        "personalization_goal": goal_value,
    }

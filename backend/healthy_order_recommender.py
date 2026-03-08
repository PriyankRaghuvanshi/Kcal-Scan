from __future__ import annotations

from typing import Any, Dict, List

from llm_explanation_copy import maybe_rewrite_explanation_copy
from nutrition_mode import NutritionMode, is_cut_mode, normalize_nutrition_mode
from personalization_profiles import (
    get_personalized_reason,
    normalize_personalization_goal,
    personalization_goal_value,
    personalize_order_for_goal,
)
from restaurant_macro_estimator import estimate_restaurant_macros


RECOMMENDATION_VERSION = "v1"

# Central place to tune cuisine/category recommendation logic.
# v1 keeps this deterministic and metadata-based (name/type/cuisine keywords only).
CUISINE_ORDER_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "grill_bbq",
        "tokens": ("grill", "grilled", "bbq", "kebab", "rotisserie"),
        "best_order": "Grilled chicken bowl",
        "better_swap": "Go easy on creamy sauces",
        "avoid_if_cutting": "Large fried combo meals",
        "estimated_calories": 520,
        "estimated_protein_g": 42,
        "estimated_satiety": "high",
        "order_strategy_tags": ["high_protein", "lower_calorie", "fat_loss_friendly"],
        "short_reason": "High protein and better calorie control than fried options.",
    },
    {
        "rule_id": "salad_bowl_poke",
        "tokens": ("salad", "bowl", "poke", "healthy", "vegan", "vegetarian"),
        "best_order": "Protein salad or poke bowl",
        "better_swap": "Choose light dressing on the side",
        "avoid_if_cutting": "Sugar-heavy sauces and crispy toppings",
        "estimated_calories": 460,
        "estimated_protein_g": 34,
        "estimated_satiety": "high",
        "order_strategy_tags": ["high_protein", "fiber_support", "fat_loss_friendly"],
        "short_reason": "Lean protein plus volume keeps you fuller for fewer calories.",
    },
    {
        "rule_id": "sushi_japanese",
        "tokens": ("sushi", "japanese", "ramen", "teriyaki", "sashimi"),
        "best_order": "Sashimi with rice-controlled bowl",
        "better_swap": "Pick sashimi or grilled rolls over tempura",
        "avoid_if_cutting": "Tempura platters and mayo-heavy rolls",
        "estimated_calories": 540,
        "estimated_protein_g": 38,
        "estimated_satiety": "high",
        "order_strategy_tags": ["high_protein", "portion_control", "fat_loss_friendly"],
        "short_reason": "Great protein quality with easier portion control.",
    },
    {
        "rule_id": "mexican",
        "tokens": ("mexican", "burrito", "taco", "quesadilla", "chipotle"),
        "best_order": "Chicken burrito bowl",
        "better_swap": "Skip chips, choose extra salsa and veggies",
        "avoid_if_cutting": "Loaded nachos and creamy queso-heavy combos",
        "estimated_calories": 560,
        "estimated_protein_g": 40,
        "estimated_satiety": "high",
        "order_strategy_tags": ["high_protein", "lower_calorie", "better_swap"],
        "short_reason": "Bowl format keeps protein high and calories easier to manage.",
    },
    {
        "rule_id": "burger_fast_food",
        "tokens": ("burger", "fast_food", "fast food", "drive", "sandwich"),
        "best_order": "Single grilled chicken burger",
        "better_swap": "Skip fries and pick water or zero-sugar drink",
        "avoid_if_cutting": "Double burger combos with fries and shakes",
        "estimated_calories": 470,
        "estimated_protein_g": 28,
        "estimated_satiety": "medium",
        "order_strategy_tags": ["better_swap", "portion_control", "lower_calorie"],
        "short_reason": "Simple swaps cut calories without losing all protein.",
    },
    {
        "rule_id": "fried_chicken",
        "tokens": ("fried chicken", "wings", "bucket", "crispy chicken"),
        "best_order": "Grilled chicken wrap",
        "better_swap": "Choose grilled pieces and skip creamy dips",
        "avoid_if_cutting": "Buckets, loaded fries, and sweet sauces",
        "estimated_calories": 500,
        "estimated_protein_g": 32,
        "estimated_satiety": "medium",
        "order_strategy_tags": ["better_swap", "high_protein", "lower_calorie"],
        "short_reason": "Grilled choices keep protein while reducing frying calories.",
    },
    {
        "rule_id": "cafe",
        "tokens": ("cafe", "coffee", "brunch", "bakery"),
        "best_order": "Egg and chicken protein plate",
        "better_swap": "Pick no-sugar coffee and skip pastry add-ons",
        "avoid_if_cutting": "Large pastries and sugary blended drinks",
        "estimated_calories": 430,
        "estimated_protein_g": 30,
        "estimated_satiety": "medium",
        "order_strategy_tags": ["high_protein", "lower_calorie", "better_swap"],
        "short_reason": "Protein-forward cafe picks are more filling than pastry meals.",
    },
    {
        "rule_id": "indian",
        "tokens": ("indian", "curry", "tandoori", "biryani", "paneer", "dal"),
        "best_order": "Tandoori protein with dal and roti",
        "better_swap": "Go for tandoori over creamy curry",
        "avoid_if_cutting": "Butter/cream curries with naan and fried starters",
        "estimated_calories": 580,
        "estimated_protein_g": 36,
        "estimated_satiety": "high",
        "order_strategy_tags": ["high_protein", "better_swap", "fat_loss_friendly"],
        "short_reason": "Tandoori + dal gives strong satiety with better calorie control.",
    },
    {
        "rule_id": "south_indian_temple",
        "tokens": ("south indian", "idli", "dosa", "sambar", "udupi", "temple", "canteen"),
        "best_order": "Idli or plain dosa-style option",
        "better_swap": "Choose steamed items and keep chutney portions moderate",
        "avoid_if_cutting": "Deep-fried snacks and heavy ghee-rich combos",
        "estimated_calories": 430,
        "estimated_protein_g": 15,
        "estimated_satiety": "medium",
        "order_strategy_tags": ["portion_control", "better_swap", "fat_loss_friendly"],
        "short_reason": "Usually easier to fit than fried or richer canteen options.",
    },
    {
        "rule_id": "thai_chinese",
        "tokens": ("thai", "chinese", "stir fry", "noodle", "wok"),
        "best_order": "Lean protein stir-fry with controlled rice",
        "better_swap": "Choose steamed rice and lighter sauce",
        "avoid_if_cutting": "Deep-fried mains and sugary sauce-heavy noodles",
        "estimated_calories": 560,
        "estimated_protein_g": 34,
        "estimated_satiety": "medium",
        "order_strategy_tags": ["high_protein", "portion_control", "better_swap"],
        "short_reason": "Stir-fry + lean protein is usually the best fat-loss move here.",
    },
    {
        "rule_id": "pizza",
        "tokens": ("pizza", "pizzeria", "slice"),
        "best_order": "Two thin-crust protein-topped slices",
        "better_swap": "Add side salad and skip cheesy dips",
        "avoid_if_cutting": "Large stuffed-crust combos",
        "estimated_calories": 590,
        "estimated_protein_g": 27,
        "estimated_satiety": "medium",
        "order_strategy_tags": ["portion_control", "better_swap", "lower_calorie"],
        "short_reason": "Thin crust and portion control reduce calorie overload.",
    },
]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _place_text(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    name = str(payload.get("name") or "").strip().lower()
    address = str(payload.get("address") or payload.get("vicinity") or "").strip().lower()
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    type_text = " ".join(str(t or "").strip().lower() for t in types)
    return " ".join(x for x in [name, address, type_text] if x)


def _cuisine_hint(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    primary = str(payload.get("primary_type") or payload.get("primaryType") or "").strip()
    if primary:
        return primary.replace("_", " ")
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    cleaned = []
    for token in types:
        text = str(token or "").strip().lower()
        if text and text not in {"restaurant", "food", "point_of_interest", "establishment", "meal_takeaway"}:
            cleaned.append(text.replace("_", " "))
    return ", ".join(cleaned[:3])


def _match_rule(place_text: str) -> tuple[Dict[str, Any] | None, int]:
    best_rule = None
    best_hits = 0
    for rule in CUISINE_ORDER_RULES:
        hits = sum(1 for token in rule.get("tokens", ()) if token in place_text)
        if hits > best_hits:
            best_hits = hits
            best_rule = rule
    return best_rule, best_hits


def _is_cut_friendly_order(estimated_calories: int, estimated_protein_g: int) -> bool:
    return bool(estimated_calories <= 560 and estimated_protein_g >= 30)


def _best_order_for_cut(best_order: str) -> str:
    text = str(best_order or "").strip().lower()

    if "burrito" in text:
        return "Chicken burrito bowl (half rice)"
    if "burger" in text:
        return "Grilled chicken burger, no mayo"
    if "pizza" in text or "slice" in text:
        return "Thin-crust protein slice + side salad"
    if "stir-fry" in text or "stir fry" in text:
        return "Lean stir-fry, light sauce, half rice"
    if "tandoori" in text:
        return "Tandoori protein + salad"
    if "sashimi" in text:
        return "Sashimi + small rice side"
    if "wrap" in text:
        return "Grilled wrap with no creamy sauce"
    if "salad" in text or "bowl" in text:
        return "High-protein bowl with light dressing"

    return f"{str(best_order).strip()} (light sauce)"


def _fallback_best_order_for_place(place: Dict[str, Any] | None) -> str:
    place_text = _place_text(place if isinstance(place, dict) else {})
    if any(token in place_text for token in ("south indian", "idli", "dosa", "udupi", "temple", "canteen")):
        return "Idli or plain dosa-style option"
    if "indian" in place_text:
        return "Simpler tandoori or dal + roti option"
    if any(token in place_text for token in ("cafe", "coffee", "bakery")):
        return "Lighter cafe meal option"
    if any(token in place_text for token in ("burger", "fast food", "fast_food", "fried")):
        return "Lighter grilled or single-item option"
    if "pizza" in place_text:
        return "Lighter thin-crust option"
    if any(token in place_text for token in ("sushi", "japanese")):
        return "Sashimi or simple rice-bowl option"
    return "Lighter menu option"


def _fallback_recommendation(
    place: Dict[str, Any] | None = None,
    mode: NutritionMode | str = NutritionMode.DEFAULT,
    personalization_goal: Any = None,
) -> Dict[str, Any]:
    # Safe default for sparse/ambiguous place metadata.
    resolved_mode = normalize_nutrition_mode(mode)
    resolved_goal = normalize_personalization_goal(personalization_goal)
    goal_value = personalization_goal_value(resolved_goal)
    cut_mode_active = is_cut_mode(resolved_mode)
    best_order = _fallback_best_order_for_place(place)

    macro = estimate_restaurant_macros(
        item_name=best_order,
        cuisine_hint="",
        place=None,
        input_calories=500,
        input_protein_g=26,
    )

    out = {
        "best_order": best_order,
        "better_swap": "Pick water and keep sauces on the side",
        "avoid_if_cutting": "Large fried combo meals",
        "estimated_calories": int(macro.get("estimated_calories", 500)),
        "estimated_protein_g": int(macro.get("estimated_protein_g", 26)),
        "estimated_carbs_g": int(macro.get("estimated_carbs_g", 45)),
        "estimated_fat_g": int(macro.get("estimated_fat_g", 18)),
        "estimated_satiety": str(macro.get("estimated_satiety") or "medium"),
        "macro_confidence": round(float(macro.get("macro_confidence", 0.52)), 2),
        "macro_estimation_version": str(macro.get("macro_estimation_version") or "v1"),
        "order_confidence": 0.46,
        "short_reason": "Balanced default when menu details are limited.",
        "order_strategy_tags": ["high_protein", "better_swap", "fat_loss_friendly"],
        "recommendation_version": RECOMMENDATION_VERSION,
        "cut_mode_active": cut_mode_active,
        "cut_friendly": False,
        "cut_warning": "",
        "best_order_for_cut": best_order,
        "personalization_goal": goal_value,
        "personalized_best_order": "",
        "personalized_reason": "",
    }

    if cut_mode_active:
        out["cut_friendly"] = True
        out["best_order_for_cut"] = _best_order_for_cut(best_order)
        out["short_reason"] = "Cut-focused default: protein-forward and easier calories."
        out["order_strategy_tags"] = list(dict.fromkeys([*out["order_strategy_tags"], "cut_mode"]))

    if resolved_goal:
        out["personalized_best_order"] = personalize_order_for_goal(out["best_order"], resolved_goal)
        out["personalized_reason"] = get_personalized_reason(resolved_goal)

    rewritten = maybe_rewrite_explanation_copy(
        place_name=str((place or {}).get("name") or "Nearby place").strip(),
        cuisine=_cuisine_hint(place if isinstance(place, dict) else {}),
        recommended_order=out["best_order"],
        estimated_calories=out["estimated_calories"],
        estimated_protein_g=out["estimated_protein_g"],
        goal=goal_value,
        confidence=out["order_confidence"],
        recommendation_source="heuristic",
        menu_item_confidence=out["order_confidence"],
        base_why_this_works=out["short_reason"],
        base_short_reason=out["short_reason"],
    )
    out["short_reason"] = str(rewritten.get("short_reason") or out["short_reason"])
    out["why_this_works"] = str(rewritten.get("why_this_works") or out["short_reason"])
    out["copy_method"] = str(rewritten.get("copy_method") or "deterministic")
    out["copy_confidence"] = round(_clamp(_safe_float(rewritten.get("copy_confidence"), out["order_confidence"]), 0.2, 0.95), 2)
    out["copy_version"] = str(rewritten.get("copy_version") or "v1")

    return out


def suggest_best_order_for_place(
    place: Dict[str, Any],
    health_score: float | None = None,
    mode: NutritionMode | str = NutritionMode.DEFAULT,
    personalization_goal: Any = None,
) -> Dict[str, Any]:
    resolved_mode = normalize_nutrition_mode(mode)
    resolved_goal = normalize_personalization_goal(personalization_goal)
    goal_value = personalization_goal_value(resolved_goal)
    cut_mode_active = is_cut_mode(resolved_mode)
    place_text = _place_text(place)
    if not place_text:
        return _fallback_recommendation(place=place, mode=resolved_mode, personalization_goal=resolved_goal)

    rule, hits = _match_rule(place_text)
    if not rule:
        return _fallback_recommendation(place=place, mode=resolved_mode, personalization_goal=resolved_goal)

    # Confidence rises when venue type is clear (more token hits) and healthy score is stronger.
    confidence = 0.68 if hits == 1 else 0.78 if hits >= 2 else 0.46
    hs = float(health_score or 0.0)
    if hs >= 7.5:
        confidence += 0.08
    elif hs >= 6.0:
        confidence += 0.04
    elif hs > 0 and hs < 4.5:
        confidence -= 0.07

    estimated_calories = int(rule["estimated_calories"])
    estimated_protein_g = int(rule["estimated_protein_g"])

    cut_friendly = _is_cut_friendly_order(estimated_calories, estimated_protein_g)
    cut_warning = ""
    best_order_for_cut = str(rule["best_order"])

    order_strategy_tags = list(rule.get("order_strategy_tags", []))
    short_reason = str(rule["short_reason"])
    better_swap = str(rule["better_swap"])

    if cut_mode_active:
        best_order_for_cut = _best_order_for_cut(str(rule["best_order"]))
        order_strategy_tags = list(dict.fromkeys([*order_strategy_tags, "cut_mode"]))

        # Keep copy short and app-ready for strict fat-loss context.
        better_swap = "Skip calorie-dense sides and keep sauces light"

        if cut_friendly:
            short_reason = "Cut-friendly pick: high protein with tighter calorie control."
            confidence += 0.03
        else:
            short_reason = "Use strict swaps here to stay inside your cut calories."
            confidence -= 0.05
            cut_warning = "Can run calorie-heavy on cut days."

    macro_item_name = best_order_for_cut if cut_mode_active else str(rule["best_order"])
    macro = estimate_restaurant_macros(
        item_name=macro_item_name,
        cuisine_hint=place_text,
        place=place,
        input_calories=estimated_calories,
        input_protein_g=estimated_protein_g,
    )

    estimated_calories = int(macro.get("estimated_calories", estimated_calories))
    estimated_protein_g = int(macro.get("estimated_protein_g", estimated_protein_g))
    estimated_carbs_g = int(macro.get("estimated_carbs_g", 45))
    estimated_fat_g = int(macro.get("estimated_fat_g", 18))
    estimated_satiety = str(macro.get("estimated_satiety") or str(rule["estimated_satiety"]))
    macro_confidence = round(float(macro.get("macro_confidence", 0.55)), 2)
    macro_estimation_version = str(macro.get("macro_estimation_version") or "v1")

    personalized_best_order = ""
    personalized_reason = ""
    if resolved_goal:
        personalized_best_order = personalize_order_for_goal(
            best_order_for_cut if cut_mode_active else str(rule["best_order"]),
            resolved_goal,
        )
        personalized_reason = get_personalized_reason(resolved_goal)

    confidence = round(_clamp(confidence, 0.35, 0.93), 2)

    result = {
        "best_order": str(rule["best_order"]),
        "better_swap": better_swap,
        "avoid_if_cutting": str(rule["avoid_if_cutting"]),
        "estimated_calories": estimated_calories,
        "estimated_protein_g": estimated_protein_g,
        "estimated_carbs_g": estimated_carbs_g,
        "estimated_fat_g": estimated_fat_g,
        "estimated_satiety": estimated_satiety,
        "macro_confidence": macro_confidence,
        "macro_estimation_version": macro_estimation_version,
        "order_confidence": confidence,
        "short_reason": short_reason,
        "order_strategy_tags": order_strategy_tags,
        "recommendation_version": RECOMMENDATION_VERSION,
        "cut_mode_active": cut_mode_active,
        "cut_friendly": cut_friendly if cut_mode_active else False,
        "cut_warning": cut_warning,
        "best_order_for_cut": best_order_for_cut if cut_mode_active else str(rule["best_order"]),
        "personalization_goal": goal_value,
        "personalized_best_order": personalized_best_order,
        "personalized_reason": personalized_reason,
    }
    rewritten = maybe_rewrite_explanation_copy(
        place_name=str((place or {}).get("name") or "").strip(),
        cuisine=_cuisine_hint(place),
        recommended_order=result["best_order_for_cut"] if cut_mode_active else result["best_order"],
        estimated_calories=result["estimated_calories"],
        estimated_protein_g=result["estimated_protein_g"],
        goal=goal_value,
        confidence=result["order_confidence"],
        recommendation_source="heuristic",
        menu_item_confidence=result["order_confidence"],
        base_why_this_works=result["short_reason"],
        base_short_reason=result["short_reason"],
    )
    result["short_reason"] = str(rewritten.get("short_reason") or result["short_reason"])
    result["why_this_works"] = str(rewritten.get("why_this_works") or result["short_reason"])
    result["copy_method"] = str(rewritten.get("copy_method") or "deterministic")
    result["copy_confidence"] = round(_clamp(_safe_float(rewritten.get("copy_confidence"), result["order_confidence"]), 0.2, 0.95), 2)
    result["copy_version"] = str(rewritten.get("copy_version") or "v1")
    return result

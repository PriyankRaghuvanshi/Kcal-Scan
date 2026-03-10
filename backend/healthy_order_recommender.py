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
from recommendation_safety import sanitize_recommended_item
from restaurant_macro_estimator import estimate_restaurant_macros
from cuisine_candidate_rules import get_best_order_for_place_heuristic


RECOMMENDATION_VERSION = "v1"

# Central place to tune cuisine/category recommendation logic.
# v1 keeps this deterministic and metadata-based (name/type/cuisine keywords only).
CUISINE_ORDER_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "grill_bbq",
        "tokens": ("grill", "grilled", "bbq", "kebab", "rotisserie"),
        "best_order": "Grilled chicken + salad",
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
        "rule_id": "sandwich_sub",
        "tokens": ("subway", "sub", "footlong", "deli", "sub sandwich", "sandwich bar"),
        "best_order": "6-inch chicken or turkey sub, extra salad, light sauce",
        "better_swap": "Ask for extra salad, skip cheese and mayo, choose 6-inch over footlong",
        "avoid_if_cutting": "Footlong with meatball, extra cheese and regular sauces",
        "estimated_calories": 390,
        "estimated_protein_g": 30,
        "estimated_carbs_g": 44,
        "estimated_fat_g": 8,
        "estimated_satiety": "high",
        "order_strategy_tags": ["high_protein", "portion_control", "better_swap"],
        "short_reason": "6-inch chicken or turkey sub hits strong protein with controlled calories — better than burger combos.",
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
        "best_order": "Eggs on toast",
        "better_swap": "Pick no-sugar coffee and skip pastry add-ons",
        "avoid_if_cutting": "Large pastries and sugary blended drinks",
        "estimated_calories": 410,
        "estimated_protein_g": 22,
        "estimated_satiety": "medium",
        "order_strategy_tags": ["high_protein", "lower_calorie", "better_swap"],
        "short_reason": "Eggs on toast or grilled wrap are solid cafe picks.",
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
        "tokens": ("south indian", "idli", "dosa", "sambar", "udupi", "temple", "canteen", "filter coffee", "chennai", "cfc"),
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

RULE_PRIORITY: Dict[str, int] = {
    "south_indian_temple": 10,
    "indian": 9,
    "cafe": 8,
    "sushi_japanese": 7,
    "mexican": 7,
    "thai_chinese": 7,
    "sandwich_sub": 7,  # beats burger_fast_food for Subway-type places
    "pizza": 6,
    "burger_fast_food": 6,
    "fried_chicken": 6,
    "grill_bbq": 5,
    "salad_bowl_poke": 4,
}


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
    best_priority = -1
    for rule in CUISINE_ORDER_RULES:
        hits = sum(1 for token in rule.get("tokens", ()) if token in place_text)
        if hits <= 0:
            continue
        priority = int(RULE_PRIORITY.get(str(rule.get("rule_id") or ""), 0))
        if hits > best_hits or (hits == best_hits and priority > best_priority):
            best_hits = hits
            best_rule = rule
            best_priority = priority
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
        return "High-protein salad with light dressing"

    return f"{str(best_order).strip()} (light sauce)"


def _order_type_from_confidence(confidence: float) -> str:
    conf = _clamp(_safe_float(confidence, 0.46), 0.0, 1.0)
    if conf >= 0.62:
        return "likely"
    return "estimated"


def _swap_details(best_order: str, better_swap: str, place_text: str) -> Dict[str, Any]:
    text = str(best_order or "").strip().lower()
    place = str(place_text or "").strip().lower()
    skip_items: List[str] = []
    add_items: List[str] = []

    if any(token in text for token in ("fried", "crispy", "combo", "fries", "bucket")) or "skip fries" in better_swap.lower():
        skip_items.append("fried sides")
    if any(token in text for token in ("shake", "soda", "cola", "dessert", "pastry")):
        skip_items.append("sugary drinks or desserts")
    if any(token in place for token in ("indian", "south indian", "temple", "canteen")):
        skip_items.append("creamy or fried extras")
        add_items.append("salad or dal-based side")
    if any(token in place for token in ("burger", "fast food", "fast_food")):
        skip_items.append("fries and sugary drinks")
        add_items.append("extra salad")
    if "pizza" in place:
        skip_items.append("cheesy dips")
        add_items.append("side salad")

    if "sauce" in better_swap.lower() and "heavy sauces" not in skip_items:
        skip_items.append("heavy sauces")
    if "water" in better_swap.lower():
        add_items.append("water or zero-sugar drink")
    if not add_items:
        add_items.append("extra vegetables")
    if not skip_items:
        skip_items.append("calorie-dense extras")

    dedup_skip: List[str] = []
    seen_skip = set()
    for row in skip_items:
        token = str(row or "").strip().lower()
        if not token or token in seen_skip:
            continue
        seen_skip.add(token)
        dedup_skip.append(str(row).strip())

    dedup_add: List[str] = []
    seen_add = set()
    for row in add_items:
        token = str(row or "").strip().lower()
        if not token or token in seen_add:
            continue
        seen_add.add(token)
        dedup_add.append(str(row).strip())

    swap_suggestion = f"Skip {dedup_skip[0]}, add {dedup_add[0]}."
    return {
        "swap_suggestion": swap_suggestion,
        "skip_items": dedup_skip[:3],
        "add_items": dedup_add[:3],
    }


def _sanitize_order_name(
    *,
    best_order: str,
    place_text: str,
    confidence: float,
) -> tuple[str, str]:
    safety = sanitize_recommended_item(
        item_name=best_order,
        context_text=place_text,
        menu_item_source="heuristic",
        menu_item_confidence=confidence,
        strong_menu_evidence=False,
    )
    return (
        str(safety.get("item_name") or best_order).strip() or "Suggested lighter option",
        str(safety.get("display_label") or "").strip(),
    )


def _fallback_best_order_for_place(
    place: Dict[str, Any] | None,
    *,
    cut_mode: bool = False,
    remaining_calories: float | None = None,
    remaining_protein_g: float | None = None,
) -> str:
    if place:
        name, _cal, _pro, _conf, _src, _ = get_best_order_for_place_heuristic(
            place, cut_mode=cut_mode, remaining_calories=remaining_calories, remaining_protein_g=remaining_protein_g
        )
        if name and name.strip() and "lighter menu option" not in name.lower():
            return name.strip()
    place_text = _place_text(place if isinstance(place, dict) else {})
    if any(token in place_text for token in ("south indian", "idli", "dosa", "udupi", "temple", "canteen")):
        return "Idli or plain dosa-style option"
    if "indian" in place_text:
        return "Tandoori chicken + dal or paneer tikka + dal"
    if any(token in place_text for token in ("cafe", "coffee", "bakery")):
        return "Eggs on toast or grilled chicken wrap"
    if any(token in place_text for token in ("burger", "fast food", "fast_food", "fried")):
        return "Lighter grilled or single-item option"
    if "pizza" in place_text:
        return "2 thin-crust slices, no sides"
    if any(token in place_text for token in ("sushi", "japanese")):
        return "Sashimi or simple rice option"
    return "Lighter menu option"


def _fallback_recommendation(
    place: Dict[str, Any] | None = None,
    mode: NutritionMode | str = NutritionMode.DEFAULT,
    personalization_goal: Any = None,
    use_llm_copy: bool = True,
    allow_llm_macro: bool = True,
) -> Dict[str, Any]:
    # Safe default for sparse/ambiguous place metadata.
    resolved_mode = normalize_nutrition_mode(mode)
    resolved_goal = normalize_personalization_goal(personalization_goal)
    goal_value = personalization_goal_value(resolved_goal)
    cut_mode_active = is_cut_mode(resolved_mode)
    best_order = _fallback_best_order_for_place(place, cut_mode=cut_mode_active)
    place_text = _place_text(place if isinstance(place, dict) else {})
    best_order, order_display_label = _sanitize_order_name(
        best_order=best_order,
        place_text=place_text,
        confidence=0.46,
    )

    macro = estimate_restaurant_macros(
        item_name=best_order,
        cuisine_hint="",
        place=None,
        input_calories=500,
        input_protein_g=26,
        allow_llm=allow_llm_macro,
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
        "order_display_label": order_display_label,
    }
    out["order_type"] = "estimated"

    if cut_mode_active:
        out["cut_friendly"] = True
        out["best_order_for_cut"] = _best_order_for_cut(best_order)
        out["short_reason"] = "Cut-focused default: protein-forward and easier calories."
        out["order_strategy_tags"] = list(dict.fromkeys([*out["order_strategy_tags"], "cut_mode"]))

    if resolved_goal:
        out["personalized_best_order"] = personalize_order_for_goal(out["best_order"], resolved_goal)
        out["personalized_reason"] = get_personalized_reason(resolved_goal)

    swap_details = _swap_details(out["best_order"], out["better_swap"], place_text)
    out["swap_suggestion"] = swap_details["swap_suggestion"]
    out["skip_items"] = swap_details["skip_items"]
    out["add_items"] = swap_details["add_items"]

    if use_llm_copy:
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
    else:
        rewritten = {}
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
    use_llm_copy: bool = True,
    allow_llm_macro: bool = True,
) -> Dict[str, Any]:
    resolved_mode = normalize_nutrition_mode(mode)
    resolved_goal = normalize_personalization_goal(personalization_goal)
    goal_value = personalization_goal_value(resolved_goal)
    cut_mode_active = is_cut_mode(resolved_mode)
    place_text = _place_text(place)
    if not place_text:
        return _fallback_recommendation(
            place=place,
            mode=resolved_mode,
            personalization_goal=resolved_goal,
            use_llm_copy=use_llm_copy,
            allow_llm_macro=allow_llm_macro,
        )

    rule, hits = _match_rule(place_text)
    if not rule:
        return _fallback_recommendation(
            place=place,
            mode=resolved_mode,
            personalization_goal=resolved_goal,
            use_llm_copy=use_llm_copy,
            allow_llm_macro=allow_llm_macro,
        )

    # Prefer cuisine_candidate_rules for candidate name and macros when available.
    heuristic_name, heuristic_cal, heuristic_pro, heuristic_conf, _src_label, _ = get_best_order_for_place_heuristic(
        place, cut_mode=cut_mode_active
    )
    use_heuristic_candidate = bool(
        heuristic_name and heuristic_name.strip()
        and "lighter menu option" not in (heuristic_name or "").strip().lower()
    )
    if use_heuristic_candidate:
        estimated_calories = int(heuristic_cal)
        estimated_protein_g = int(heuristic_pro)
        confidence = float(heuristic_conf)
        best_order_from_rule = heuristic_name.strip()
    else:
        estimated_calories = int(rule["estimated_calories"])
        estimated_protein_g = int(rule["estimated_protein_g"])
        confidence = 0.68 if hits == 1 else 0.78 if hits >= 2 else 0.46
        best_order_from_rule = str(rule["best_order"])

    hs = float(health_score or 0.0)
    if not use_heuristic_candidate:
        if hs >= 7.5:
            confidence += 0.08
        elif hs >= 6.0:
            confidence += 0.04
        elif hs > 0 and hs < 4.5:
            confidence -= 0.07

    cut_friendly = _is_cut_friendly_order(estimated_calories, estimated_protein_g)
    cut_warning = ""
    best_order_for_cut = best_order_from_rule

    order_strategy_tags = list(rule.get("order_strategy_tags", []))
    short_reason = str(rule["short_reason"])
    better_swap = str(rule["better_swap"])

    if cut_mode_active:
        best_order_for_cut = _best_order_for_cut(best_order_from_rule)
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

    confidence = round(_clamp(confidence, 0.35, 0.93), 2)
    safe_best_order, order_display_label = _sanitize_order_name(
        best_order=best_order_from_rule,
        place_text=place_text,
        confidence=confidence,
    )
    if cut_mode_active:
        best_order_for_cut = _best_order_for_cut(safe_best_order)

    macro_item_name = best_order_for_cut if cut_mode_active else safe_best_order
    macro = estimate_restaurant_macros(
        item_name=macro_item_name,
        cuisine_hint=place_text,
        place=place,
        input_calories=estimated_calories,
        input_protein_g=estimated_protein_g,
        allow_llm=allow_llm_macro,
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
            _best_order_for_cut(safe_best_order) if cut_mode_active else safe_best_order,
            resolved_goal,
        )
        personalized_reason = get_personalized_reason(resolved_goal)

    order_type = _order_type_from_confidence(confidence)
    swap_details = _swap_details(safe_best_order, better_swap, place_text)

    result = {
        "best_order": safe_best_order,
        "better_swap": better_swap,
        "swap_suggestion": swap_details["swap_suggestion"],
        "skip_items": swap_details["skip_items"],
        "add_items": swap_details["add_items"],
        "order_type": order_type,
        "order_display_label": order_display_label,
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
        "best_order_for_cut": _best_order_for_cut(safe_best_order) if cut_mode_active else safe_best_order,
        "personalization_goal": goal_value,
        "personalized_best_order": personalized_best_order,
        "personalized_reason": personalized_reason,
    }
    if use_llm_copy:
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
    else:
        rewritten = {}
    result["short_reason"] = str(rewritten.get("short_reason") or result["short_reason"])
    result["why_this_works"] = str(rewritten.get("why_this_works") or result["short_reason"])
    result["copy_method"] = str(rewritten.get("copy_method") or "deterministic")
    result["copy_confidence"] = round(_clamp(_safe_float(rewritten.get("copy_confidence"), result["order_confidence"]), 0.2, 0.95), 2)
    result["copy_version"] = str(rewritten.get("copy_version") or "v1")
    return result

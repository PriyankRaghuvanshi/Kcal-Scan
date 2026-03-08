from __future__ import annotations

from typing import Any, Dict, List, Tuple

from nutrition_mode import (
    NutritionMode,
    get_place_score_weights,
    is_cut_mode,
    normalize_nutrition_mode,
)
from personalization_profiles import (
    get_goal_adjusted_place_weights,
    normalize_personalization_goal,
    personalization_goal_value,
)


HEALTHY_PLACE_SCORING_VERSION = "v1_keyword_component"

# Backward-compatible default weight export.
HEALTHY_PLACE_SCORE_WEIGHTS: Dict[str, float] = get_place_score_weights(NutritionMode.DEFAULT)

# Component keyword maps are metadata-based heuristics (not menu-level nutrition facts).
_COMPONENT_KEYWORDS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    # Protein density proxy: cuisines and venue tags that commonly offer lean protein choices.
    "protein_density": {
        "positive": (
            "protein",
            "grill",
            "grilled",
            "bbq",
            "kebab",
            "chicken",
            "fish",
            "seafood",
            "sushi",
            "poke",
            "tofu",
            "paneer",
            "lentil",
            "dal",
            "egg",
        ),
        "negative": (
            "dessert",
            "donut",
            "pastry",
            "bakery",
            "ice_cream",
        ),
    },
    # Calorie control proxy: preparation style and venue type likely to support lower-calorie picks.
    "calorie_control": {
        "positive": (
            "salad",
            "healthy",
            "grill",
            "grilled",
            "steamed",
            "baked",
            "soup",
            "mediterranean",
            "japanese",
            "thai",
            "vegetarian",
            "vegan",
        ),
        "negative": (
            "fried",
            "deep fry",
            "fries",
            "burger",
            "pizza",
            "buffet",
            "dessert",
            "pastry",
            "fast_food",
        ),
    },
    # Satiety proxy: higher protein/fiber and whole-food style cues vs hyper-palatable fast-food cues.
    "satiety": {
        "positive": (
            "protein",
            "salad",
            "bowl",
            "grill",
            "grilled",
            "lentil",
            "bean",
            "dal",
            "tofu",
            "paneer",
            "soup",
        ),
        "negative": (
            "dessert",
            "donut",
            "pizza",
            "burger",
            "pastry",
            "sweet",
            "fried",
            "fries",
        ),
    },
    # Fat-loss friendliness proxy: combined cue for lean-protein + calorie control + low ultra-processed bias.
    "fat_loss_friendliness": {
        "positive": (
            "healthy",
            "protein",
            "salad",
            "grill",
            "grilled",
            "mediterranean",
            "sushi",
            "poke",
            "thai",
            "vegetarian",
            "vegan",
        ),
        "negative": (
            "fried",
            "deep fry",
            "fries",
            "burger",
            "pizza",
            "dessert",
            "donut",
            "milkshake",
            "ice_cream",
        ),
    },
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    total = float(sum(max(0.0, float(v or 0.0)) for v in weights.values()) or 0.0)
    if total <= 0:
        return dict(HEALTHY_PLACE_SCORE_WEIGHTS)
    return {k: max(0.0, float(v or 0.0)) / total for k, v in weights.items()}


def _place_text(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    name = str(payload.get("name") or "").strip().lower()
    address = str(payload.get("address") or payload.get("vicinity") or "").strip().lower()
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    type_text = " ".join(str(t or "").strip().lower() for t in types)
    return " ".join(x for x in [name, address, type_text] if x)


def _component_score(
    place_text: str,
    component: str,
) -> Dict[str, Any]:
    keywords = _COMPONENT_KEYWORDS.get(component, {})
    positive = keywords.get("positive", ())
    negative = keywords.get("negative", ())

    pos_hits = [token for token in positive if token in place_text]
    neg_hits = [token for token in negative if token in place_text]

    # Neutral prior because Google Places usually lacks menu-level nutrition values.
    score_0_to_1 = 0.5
    score_0_to_1 += min(0.35, 0.10 * len(pos_hits))
    score_0_to_1 -= min(0.35, 0.10 * len(neg_hits))
    score_0_to_1 = _clamp(score_0_to_1, 0.05, 0.95)

    note: str
    if pos_hits and not neg_hits:
        note = "Positive venue metadata cues for this component."
    elif neg_hits and not pos_hits:
        note = "Negative venue metadata cues for this component."
    elif pos_hits and neg_hits:
        note = "Mixed cues; score is intentionally conservative."
    else:
        note = "No strong cues in venue metadata; neutral fallback used."

    return {
        "score": round(score_0_to_1 * 10.0, 1),
        "positive_signals": pos_hits[:4],
        "negative_signals": neg_hits[:4],
        "note": note,
        "estimated": True,
    }


def _default_breakdown(weights: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    return {
        component: {
            "score": 5.0,
            "weight": round(float(weights.get(component, 0.0)), 3),
            "positive_signals": [],
            "negative_signals": [],
            "note": "No venue metadata available; neutral fallback used.",
            "estimated": True,
        }
        for component in HEALTHY_PLACE_SCORE_WEIGHTS.keys()
    }


def best_options_for_place(place: Dict[str, Any]) -> List[str]:
    text = _place_text(place)
    if any(token in text for token in ("salad", "healthy", "vegan", "vegetarian")):
        return ["Protein salad", "Veggie + protein bowl"]
    if any(token in text for token in ("sushi", "japanese")):
        return ["Sashimi + miso soup", "Rice portion-controlled poke"]
    if any(token in text for token in ("grill", "bbq", "kebab")):
        return ["Grilled lean protein plate", "Protein + greens combo"]
    if any(token in text for token in ("indian", "curry")):
        return ["Tandoori protein option", "Dal + salad + controlled roti"]
    return ["Protein-forward meal", "Lower-oil whole-food option"]


def score_healthy_place(
    place: Dict[str, Any],
    weights: Dict[str, float] | None = None,
    mode: NutritionMode | str = NutritionMode.DEFAULT,
    personalization_goal: Any = None,
) -> Dict[str, Any]:
    payload = place if isinstance(place, dict) else {}
    resolved_mode = normalize_nutrition_mode(mode)
    resolved_goal = normalize_personalization_goal(personalization_goal)
    goal_value = personalization_goal_value(resolved_goal)
    cut_mode_active = is_cut_mode(resolved_mode)
    base_weights = get_place_score_weights(resolved_mode)
    if resolved_goal:
        base_weights = get_goal_adjusted_place_weights(base_weights, resolved_goal)
    applied_weights = _normalize_weights(weights or base_weights)
    place_text = _place_text(payload)

    if not place_text:
        breakdown = _default_breakdown(applied_weights)
        badges = ["Needs menu check"]
        if cut_mode_active:
            badges.append("Cut review needed")
        return {
            "health_score": 5.0,
            "score_breakdown": breakdown,
            "fat_loss_friendly": False,
            "recommended_badges": badges,
            "best_options": best_options_for_place(payload),
            "nutrition_data_available": False,
            "scoring_version": HEALTHY_PLACE_SCORING_VERSION,
            "cut_mode_active": cut_mode_active,
            "cut_friendly": False,
            "cut_warning": "Needs menu-level review before cut-day choice." if cut_mode_active else "",
            "personalization_goal": goal_value,
        }

    breakdown: Dict[str, Dict[str, Any]] = {}
    weighted_sum = 0.0
    for component in HEALTHY_PLACE_SCORE_WEIGHTS.keys():
        comp = _component_score(place_text, component)
        comp_weight = float(applied_weights.get(component, 0.0) or 0.0)
        comp["weight"] = round(comp_weight, 3)
        breakdown[component] = comp
        weighted_sum += (float(comp["score"]) / 10.0) * comp_weight

    health_score = round(_clamp(weighted_sum * 10.0, 1.0, 10.0), 1)

    badges: List[str] = []
    if breakdown["protein_density"]["score"] >= 7.0:
        badges.append("High-protein options likely")
    if breakdown["calorie_control"]["score"] >= 7.0:
        badges.append("Calorie-control friendly")
    if breakdown["satiety"]["score"] >= 7.0:
        badges.append("Satiety-friendly picks")
    if breakdown["fat_loss_friendliness"]["score"] >= 7.0:
        badges.append("Fat-loss friendly")
    if not badges:
        badges.append("Needs menu check")

    fat_loss_friendly = bool(
        health_score >= 6.5 and float(breakdown["fat_loss_friendliness"]["score"]) >= 6.0
    )

    cut_friendly = bool(
        cut_mode_active
        and health_score >= 6.7
        and float(breakdown["calorie_control"]["score"]) >= 6.8
        and float(breakdown["protein_density"]["score"]) >= 6.8
    )

    if cut_mode_active:
        if cut_friendly:
            badges.insert(0, "Cut-friendly short list")
        elif float(breakdown["calorie_control"]["score"]) < 6.0:
            badges.append("Calorie-heavy for cut days")

    cut_warning = ""
    if cut_mode_active and not cut_friendly:
        if float(breakdown["calorie_control"]["score"]) < 6.0:
            cut_warning = "Watch calories here on cut days."
        elif float(breakdown["protein_density"]["score"]) < 6.0:
            cut_warning = "Protein options may be limited for cut goals."
        else:
            cut_warning = "Moderate fit; portion control still needed."

    return {
        "health_score": health_score,
        "score_breakdown": breakdown,
        "fat_loss_friendly": fat_loss_friendly,
        "recommended_badges": badges,
        "best_options": best_options_for_place(payload),
        "nutrition_data_available": False,
        "scoring_version": HEALTHY_PLACE_SCORING_VERSION,
        "cut_mode_active": cut_mode_active,
        "cut_friendly": cut_friendly,
        "cut_warning": cut_warning,
        "personalization_goal": goal_value,
    }

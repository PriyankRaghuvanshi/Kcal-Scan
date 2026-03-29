"""
Meal-first ranking for Healthy Nearby.

Primary score: meal_fitness_score_100 (not venue health_score).
Eligibility bands prevent generic/heuristic fallbacks from becoming #1.
LLM is not used in this module; ranking is deterministic and fast.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

MEAL_RANKING_VERSION = "v1"

# CUT / fat_loss weights (sum = 100)
CUT_WEIGHTS = {
    "macro_fit": 28.0,
    "protein_density": 22.0,
    "food_quality": 16.0,
    "satiety": 12.0,
    "confidence": 10.0,
    "distance": 6.0,
    "price_value": 3.0,
    "personal_history": 3.0,
}

# Max penalties (subtracted from raw score). General food-quality logic; no pizza-specific caps.
PENALTY_CAPS = {
    "ultra_processed_penalty": 10.0,
    "combo_meal_penalty": 8.0,
    "deep_fried_penalty": 8.0,
    "sugary_drink_penalty": 6.0,
    "hyper_palatable_penalty": 6.0,
    "low_protein_density_penalty": 8.0,
    "generic_fallback_penalty": 12.0,
    "overshoot_penalty": 20.0,
}
# Backward compat alias
PENALTY_CAPS["upf_penalty"] = PENALTY_CAPS["ultra_processed_penalty"]
PENALTY_CAPS["fried_penalty"] = PENALTY_CAPS["deep_fried_penalty"]

# Food quality: positive/negative item name signals (stronger in CUT)
FOOD_QUALITY_POSITIVE = (
    "grilled", "tandoori", "roasted", "steamed", "salad", "dal", "egg", "fish",
    "chicken", "paneer tikka", "sashimi", "kebab", "wrap", "bowl", "idli", "dosa",
    "sambar", "sub", "turkey", "tofu",
)
FOOD_QUALITY_NEGATIVE = (
    "pizza combo", "pizza", "fries", "deep fried", "burger combo", "sugary drink", "dessert",
    "pastry", "creamy curry", "loaded sides", "combo", "bucket", "double",
    "stuffed", "cheesy dip", "mayo", "meal deal", "fried chicken combo",
)

# Generic fallback item name tokens → cannot be band 3 / hero
GENERIC_FALLBACK_TOKENS = (
    "egg + chicken plate", "egg and chicken plate", "lighter menu option",
    "lighter option", "healthy option", "balanced meal", "smart choice",
    "recommended item", "best menu item", "protein plate", "protein bowl",
    "grilled protein bowl", "lean wrap", "protein wrap", "needs menu check",
    # Honest heuristic copy from recommendation_safety (no real menu)
    "no menu on file",
)

# Recommendation labels by band/source
LABEL_BEST_PICK = "Best pick"
LABEL_STRONG_OPTION = "Strong option"
LABEL_LIKELY_HEALTHY = "Likely healthy option"
LABEL_NEEDS_MENU_CHECK = "Needs menu check"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _food_quality_score_100(item_name: str, place_text: str, cut_mode: bool) -> float:
    """Item-level food quality 0..100. Stronger negative bias in CUT."""
    text = f"{str(item_name or '').strip().lower()} {str(place_text or '').strip().lower()}"
    pos = sum(4.0 if t in text else 0.0 for t in FOOD_QUALITY_POSITIVE)
    neg = sum(6.0 if t in text else 0.0 for t in FOOD_QUALITY_NEGATIVE)  # 6 in CUT
    if not cut_mode:
        neg *= 0.7
    raw = _clamp(50.0 + min(25.0, pos) - min(40.0, neg), 0.0, 100.0)
    return round(raw, 1)


def _is_generic_fallback(item_name: str) -> bool:
    lower = str(item_name or "").strip().lower()
    return any(t in lower for t in GENERIC_FALLBACK_TOKENS)


def _penalties(
    place_profile: Dict[str, Any],
    user_context: Dict[str, Any],
    item_name: str,
) -> Dict[str, float]:
    """Compute penalty components (to subtract from score). General food-quality logic only."""
    text = f"{str(item_name or '').strip().lower()} {str(place_profile.get('name') or '').strip().lower()}"
    place_text = text
    cut_mode = bool(user_context.get("cut_mode") or str(user_context.get("goal") or "").strip().lower() in ("fat_loss", "cut"))
    penalties: Dict[str, float] = {
        "ultra_processed_penalty": 0.0,
        "combo_meal_penalty": 0.0,
        "deep_fried_penalty": 0.0,
        "sugary_drink_penalty": 0.0,
        "hyper_palatable_penalty": 0.0,
        "low_protein_density_penalty": 0.0,
        "generic_fallback_penalty": 0.0,
        "overshoot_penalty": 0.0,
    }
    # Ultra-processed / combo / meal deal (general; no pizza-specific token)
    if any(t in place_text for t in ("combo", "bucket", "loaded", "double", "meal deal")):
        penalties["ultra_processed_penalty"] = min(PENALTY_CAPS["ultra_processed_penalty"], 7.0)
        penalties["combo_meal_penalty"] = min(PENALTY_CAPS["combo_meal_penalty"], 6.0)
    # Deep fried
    if any(t in place_text for t in ("fried", "crispy", "fries", "deep fry")):
        penalties["deep_fried_penalty"] = min(PENALTY_CAPS["deep_fried_penalty"], 5.0)
    # Sugary drink
    if any(t in place_text for t in ("soda", "shake", "smoothie", "sugary drink")):
        penalties["sugary_drink_penalty"] = min(PENALTY_CAPS["sugary_drink_penalty"], 4.0)
    # Hyper-palatable: dessert, pastry, creamy heavy, stuffed
    if any(t in place_text for t in ("dessert", "pastry", "creamy curry", "stuffed", "cheesy dip")):
        penalties["hyper_palatable_penalty"] = min(PENALTY_CAPS["hyper_palatable_penalty"], 4.0)
    # Low protein density in CUT: weak protein for calories (e.g. pizza/sides-heavy meals)
    if cut_mode:
        est_cal = _safe_float(place_profile.get("estimated_calories"), 520.0)
        est_protein = _safe_float(place_profile.get("estimated_protein_g"), 32.0)
        density = (est_protein / max(1.0, est_cal)) * 1400.0 if est_cal else 0
        if density < 60.0 and est_cal > 400:
            # Scale penalty: worse density => higher penalty
            penalties["low_protein_density_penalty"] = min(PENALTY_CAPS["low_protein_density_penalty"], max(2.0, 8.0 - density / 10.0))
    # Generic fallback
    if _is_generic_fallback(item_name):
        penalties["generic_fallback_penalty"] = PENALTY_CAPS["generic_fallback_penalty"]
    # Overshoot from place_today_decision
    overshoot_100 = _safe_float(user_context.get("overshoot_penalty_100"), 0.0)
    penalties["overshoot_penalty"] = min(PENALTY_CAPS["overshoot_penalty"], overshoot_100 / 5.0)
    return penalties


def compute_meal_fitness_score(
    place_profile: Dict[str, Any],
    user_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Meal-first score 0..100. Used as primary ranking and display_rank_score_100.
    Weights for CUT: macro_fit 28, protein_density 22, food_quality 16, satiety 12,
    confidence 10, distance 6, price_value 3, personal_history 3.
    """
    cut_mode = bool(user_context.get("cut_mode") or user_context.get("goal") in ("fat_loss", "cut"))
    weights = CUT_WEIGHTS

    # Component scores 0..100
    fit_today_100 = _safe_float(user_context.get("fit_today_score_100"), 50.0)
    calorie_fit_100 = _safe_float(user_context.get("calorie_fit_score_100"), 50.0)
    protein_fit_100 = _safe_float(user_context.get("protein_fit_score_100"), 50.0)
    macro_fit = (calorie_fit_100 * 0.5 + protein_fit_100 * 0.5) if cut_mode else fit_today_100

    est_cal = _safe_float(place_profile.get("estimated_calories"), 520.0)
    est_protein = _safe_float(place_profile.get("estimated_protein_g"), 32.0)
    protein_density = _clamp((est_protein / max(1.0, est_cal)) * 1400.0, 0.0, 100.0)

    item_name = str(place_profile.get("recommended_order") or place_profile.get("best_order") or "").strip() or "Lighter menu option"
    place_text = str(place_profile.get("name") or "") + " " + str(place_profile.get("cuisine_hint") or "")
    food_quality = _food_quality_score_100(item_name, place_text, cut_mode)

    # Satiety proxy: protein + moderate cal
    satiety = _clamp(40.0 + (est_protein * 1.2) - (est_cal / 25.0), 0.0, 100.0)

    confidence = _clamp(_safe_float(place_profile.get("menu_item_confidence") or place_profile.get("order_confidence"), 0.5) * 100.0, 0.0, 100.0)

    distance_m = _safe_float(place_profile.get("distance_meters"), 2000.0)
    distance = _clamp(100.0 - min(100.0, distance_m / 30.0), 0.0, 100.0)

    price_value = 50.0  # neutral when unknown
    personal_history = 50.0  # neutral when unknown

    raw = (
        (macro_fit * weights["macro_fit"] / 100.0)
        + (protein_density * weights["protein_density"] / 100.0)
        + (food_quality * weights["food_quality"] / 100.0)
        + (satiety * weights["satiety"] / 100.0)
        + (confidence * weights["confidence"] / 100.0)
        + (distance * weights["distance"] / 100.0)
        + (price_value * weights["price_value"] / 100.0)
        + (personal_history * weights["personal_history"] / 100.0)
    )

    penalty_dict = _penalties(place_profile, user_context, item_name)
    total_penalty = sum(penalty_dict.values())
    score_100 = _clamp(raw - total_penalty, 0.0, 100.0)
    score_10 = round(score_100 / 10.0, 1)

    return {
        "meal_fitness_score_100": round(score_100, 1),
        "meal_fitness_score": score_10,
        "score_breakdown": {
            "macro_fit": round(macro_fit, 1),
            "protein_density": round(protein_density, 1),
            "food_quality": round(food_quality, 1),
            "satiety": round(satiety, 1),
            "confidence": round(confidence, 1),
            "distance": round(distance, 1),
            "price_value": round(price_value, 1),
            "personal_history": round(personal_history, 1),
            "penalties": {k: round(v, 1) for k, v in penalty_dict.items()},
        },
        "version": MEAL_RANKING_VERSION,
    }


def compute_eligibility_band(place_profile: Dict[str, Any], user_context: Dict[str, Any]) -> int:
    """
    Band 3 = verified/high-confidence, non-generic, fit not NO.
    Band 2 = strong candidate.
    Band 1 = plausible fallback / needs menu check.
    Band 0 = hide from top / cannot be hero.
    """
    item_name = str(place_profile.get("recommended_order") or place_profile.get("best_order") or "").strip()
    source = str(place_profile.get("menu_item_source") or "heuristic").strip().lower()
    confidence = _safe_float(place_profile.get("menu_item_confidence"), 0.5)
    decision_today = str(place_profile.get("decision_today") or "").strip().upper()
    fit_for_today = place_profile.get("fit_for_today")
    remaining_protein = _safe_float(user_context.get("remaining_protein_g"), 0.0)
    est_protein = _safe_float(place_profile.get("estimated_protein_g"), 0.0)

    # Hero constraints: generic fallback cannot be band 3
    if _is_generic_fallback(item_name):
        return 1
    if "needs menu check" in item_name.lower() or (source == "heuristic" and confidence < 0.62):
        return 1
    if decision_today == "NO" or fit_for_today is False:
        return min(1, 2)  # max band 1

    # Protein too low for context → max band 1
    if remaining_protein > 30 and est_protein < 20:
        return 1

    # No pizza-specific cap; general food-quality penalties in compute_meal_fitness_score handle processed/combo meals.
    if source in ("real_menu", "user_scan") and confidence >= 0.72:
        return 3
    if source == "llm_inferred" and confidence >= 0.65:
        return 2
    if source == "heuristic" and confidence >= 0.62:
        return 2
    return 1


# Suggested healthier pick: generic fallbacks must use this or Needs menu check, never Best pick
LABEL_SUGGESTED_HEALTHIER = "Suggested healthier pick"


def recommendation_label_and_section(
    eligibility_band: int,
    menu_item_source: str,
    menu_item_confidence: float,
    is_generic_fallback: bool,
) -> Tuple[str, str]:
    """Return (recommendation_label, section). Generic fallbacks never Best pick."""
    source = str(menu_item_source or "heuristic").strip().lower()
    if is_generic_fallback:
        if menu_item_confidence < 0.55:
            return LABEL_NEEDS_MENU_CHECK, "Needs menu check"
        return LABEL_SUGGESTED_HEALTHIER, "Decent nearby options"
    if eligibility_band <= 1:
        if menu_item_confidence < 0.55:
            return LABEL_NEEDS_MENU_CHECK, "Needs menu check"
        return LABEL_LIKELY_HEALTHY, "Decent nearby options"
    if eligibility_band == 3 and source in ("real_menu", "user_scan") and menu_item_confidence >= 0.72:
        return LABEL_BEST_PICK, "Best fit for your goal"
    if eligibility_band >= 2:
        return LABEL_STRONG_OPTION, "Best fit for your goal"
    return LABEL_LIKELY_HEALTHY, "Decent nearby options"


def why_this_ranked_here_short(
    meal_fitness_score_100: float,
    eligibility_band: int,
    recommendation_label: str,
    protein_g: float,
    calories: int,
) -> str:
    """Short deterministic reason for ranking (no LLM)."""
    if eligibility_band >= 2 and recommendation_label == LABEL_BEST_PICK:
        return f"Strong meal fit (score {int(meal_fitness_score_100)}): good protein and calorie fit for your goal."
    if meal_fitness_score_100 >= 65:
        return f"Good balance of protein ({int(protein_g)}g) and calories ({calories} kcal) for your remaining budget."
    return "Nearby option; check menu for best pick."

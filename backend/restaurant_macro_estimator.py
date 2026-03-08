from __future__ import annotations

from typing import Any, Dict, List, Tuple

from llm_macro_estimator import maybe_estimate_unknown_meal_macros


MACRO_ESTIMATION_VERSION = "v1_template_heuristic"


# Dish-level templates tuned for practical restaurant estimation (not exact nutrition truth).
_DISH_PROFILES: List[Dict[str, Any]] = [
    {
        "profile": "grilled_chicken_bowl",
        "tokens": ("grilled chicken bowl", "chicken bowl", "protein bowl", "grain bowl"),
        "kcal": 520,
        "protein": 40,
        "carbs": 38,
        "fat": 15,
        "satiety": "high",
        "confidence": 0.76,
    },
    {
        "profile": "burger_meal",
        "tokens": ("burger meal", "burger combo", "double burger", "cheeseburger"),
        "kcal": 820,
        "protein": 34,
        "carbs": 72,
        "fat": 38,
        "satiety": "medium",
        "confidence": 0.73,
    },
    {
        "profile": "sushi_bowl",
        "tokens": ("sushi bowl", "poke bowl", "salmon bowl", "teriyaki bowl", "rice bowl"),
        "kcal": 560,
        "protein": 33,
        "carbs": 62,
        "fat": 16,
        "satiety": "high",
        "confidence": 0.74,
    },
    {
        "profile": "curry_rice",
        "tokens": ("curry rice", "chicken curry", "butter chicken", "curry + rice", "biryani"),
        "kcal": 720,
        "protein": 29,
        "carbs": 74,
        "fat": 30,
        "satiety": "medium",
        "confidence": 0.71,
    },
    {
        "profile": "salad_protein",
        "tokens": ("salad", "caesar", "quinoa salad", "protein salad"),
        "kcal": 460,
        "protein": 31,
        "carbs": 30,
        "fat": 18,
        "satiety": "high",
        "confidence": 0.72,
    },
    {
        "profile": "wrap_sandwich",
        "tokens": ("wrap", "sandwich", "sub", "roll"),
        "kcal": 540,
        "protein": 30,
        "carbs": 50,
        "fat": 20,
        "satiety": "medium",
        "confidence": 0.67,
    },
    {
        "profile": "pizza",
        "tokens": ("pizza", "slice"),
        "kcal": 670,
        "protein": 28,
        "carbs": 66,
        "fat": 30,
        "satiety": "medium",
        "confidence": 0.68,
    },
    {
        "profile": "fried_combo",
        "tokens": ("fried", "crispy", "loaded fries", "bucket", "nuggets"),
        "kcal": 780,
        "protein": 25,
        "carbs": 68,
        "fat": 36,
        "satiety": "low",
        "confidence": 0.66,
    },
]

# Cuisine and place-type adjustment knobs for v1 tuning.
_CUISINE_ADJUSTMENTS: Dict[str, Dict[str, int]] = {
    "japanese": {"kcal": -20, "protein": 2, "carbs": 4, "fat": -1},
    "sushi": {"kcal": -20, "protein": 3, "carbs": 5, "fat": -1},
    "poke": {"kcal": -15, "protein": 4, "carbs": 4, "fat": -1},
    "indian": {"kcal": 80, "protein": 1, "carbs": 10, "fat": 5},
    "curry": {"kcal": 75, "protein": 1, "carbs": 8, "fat": 6},
    "thai": {"kcal": 40, "protein": 0, "carbs": 5, "fat": 2},
    "chinese": {"kcal": 45, "protein": 0, "carbs": 7, "fat": 2},
    "mexican": {"kcal": 55, "protein": 2, "carbs": 8, "fat": 2},
    "mediterranean": {"kcal": -10, "protein": 2, "carbs": 2, "fat": 0},
    "fast_food": {"kcal": 90, "protein": 0, "carbs": 8, "fat": 6},
    "burger": {"kcal": 85, "protein": 0, "carbs": 6, "fat": 6},
    "pizza": {"kcal": 80, "protein": 0, "carbs": 9, "fat": 5},
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _place_text(place: Dict[str, Any] | None) -> str:
    payload = place if isinstance(place, dict) else {}
    name = str(payload.get("name") or "").strip().lower()
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    type_text = " ".join(str(t or "").strip().lower() for t in types)
    vicinity = str(payload.get("vicinity") or payload.get("address") or "").strip().lower()
    return " ".join(x for x in [name, type_text, vicinity] if x)


def _match_profile(item_text: str) -> Tuple[Dict[str, Any], int]:
    best = None
    best_hits = 0
    for profile in _DISH_PROFILES:
        hits = sum(1 for token in profile.get("tokens", ()) if token in item_text)
        if hits > best_hits:
            best_hits = hits
            best = profile

    if best:
        return best, best_hits

    return {
        "profile": "balanced_default",
        "tokens": (),
        "kcal": 520,
        "protein": 30,
        "carbs": 46,
        "fat": 18,
        "satiety": "medium",
        "confidence": 0.52,
    }, 0


def _collect_adjustments(item_text: str, cuisine_hint: str, place_text: str) -> Dict[str, int]:
    combined = f"{item_text} {cuisine_hint} {place_text}".strip().lower()
    delta = {"kcal": 0, "protein": 0, "carbs": 0, "fat": 0}

    for token, adj in _CUISINE_ADJUSTMENTS.items():
        if token in combined:
            delta["kcal"] += int(adj.get("kcal", 0))
            delta["protein"] += int(adj.get("protein", 0))
            delta["carbs"] += int(adj.get("carbs", 0))
            delta["fat"] += int(adj.get("fat", 0))

    return delta


def _satiety_from_macros(calories: int, protein_g: int, carbs_g: int, fat_g: int) -> str:
    if protein_g >= 35 and calories <= 650 and fat_g <= 24:
        return "high"
    if protein_g >= 22 and calories <= 850 and carbs_g <= 95:
        return "medium"
    return "low"


def _reconcile_energy(calories: int, protein_g: int, carbs_g: int, fat_g: int) -> Tuple[int, int, int, int]:
    calories = int(_clamp(calories, 280, 1300))
    protein_g = int(_clamp(protein_g, 8, 85))
    fat_g = int(_clamp(fat_g, 6, 75))

    # Use calories as anchor and solve carbs from remaining energy.
    remaining = calories - ((4 * protein_g) + (9 * fat_g))
    carbs_g = int(round(remaining / 4.0))

    if carbs_g < 8:
        # If carbs goes too low, reduce fat first to keep macros plausible.
        fat_cap = int((calories - (4 * protein_g) - (4 * 8)) / 9.0)
        fat_g = int(_clamp(fat_cap, 6, 75))
        remaining = calories - ((4 * protein_g) + (9 * fat_g))
        carbs_g = int(round(remaining / 4.0))

    carbs_g = int(_clamp(carbs_g, 8, 150))

    # Final calorie reconciliation to keep output internally consistent.
    calories = int(_clamp((4 * protein_g) + (4 * carbs_g) + (9 * fat_g), 280, 1300))
    return calories, protein_g, carbs_g, fat_g


def estimate_restaurant_macros(
    item_name: str,
    cuisine_hint: str | None = None,
    place: Dict[str, Any] | None = None,
    input_calories: int | None = None,
    input_protein_g: int | None = None,
) -> Dict[str, Any]:
    item_text = str(item_name or "").strip().lower()
    cuisine_text = str(cuisine_hint or "").strip().lower()
    place_text = _place_text(place)

    profile, hit_count = _match_profile(item_text)

    calories = int(profile.get("kcal", 520))
    protein_g = int(profile.get("protein", 30))
    carbs_g = int(profile.get("carbs", 46))
    fat_g = int(profile.get("fat", 18))

    confidence = float(profile.get("confidence", 0.52))

    # Blend known input values if provided (e.g., from prior heuristics/menu metadata).
    if input_calories is not None and int(input_calories) > 0:
        calories = int(round((0.65 * int(input_calories)) + (0.35 * calories)))
        confidence += 0.10

    if input_protein_g is not None and int(input_protein_g) > 0:
        protein_g = int(round((0.65 * int(input_protein_g)) + (0.35 * protein_g)))
        confidence += 0.08

    has_known_nutrition = bool((input_calories is not None and int(input_calories) > 0) or (input_protein_g is not None and int(input_protein_g) > 0))

    deltas = _collect_adjustments(item_text, cuisine_text, place_text)
    calories += int(deltas["kcal"])
    protein_g += int(deltas["protein"])
    carbs_g += int(deltas["carbs"])
    fat_g += int(deltas["fat"])

    calories, protein_g, carbs_g, fat_g = _reconcile_energy(calories, protein_g, carbs_g, fat_g)
    satiety = _satiety_from_macros(calories, protein_g, carbs_g, fat_g)

    if hit_count >= 2:
        confidence += 0.05
    elif hit_count == 1:
        confidence += 0.02
    else:
        confidence -= 0.06

    if cuisine_text:
        confidence += 0.03
    if place_text:
        confidence += 0.02

    confidence = round(_clamp(confidence, 0.35, 0.92), 2)

    deterministic = {
        "estimated_calories": int(calories),
        "estimated_protein_g": int(protein_g),
        "estimated_carbs_g": int(carbs_g),
        "estimated_fat_g": int(fat_g),
        "estimated_satiety": satiety,
        "macro_confidence": confidence,
    }

    llm_out = maybe_estimate_unknown_meal_macros(
        item_name=str(item_name or ""),
        cuisine_hint=cuisine_text,
        place=place,
        known_components=[],
        deterministic_estimate=deterministic,
        has_known_nutrition=has_known_nutrition,
        profile_hit_count=int(hit_count or 0),
    )

    if bool(llm_out.get("used")) and isinstance(llm_out.get("estimate"), dict):
        llm_est = llm_out["estimate"]
        calories, protein_g, carbs_g, fat_g = _reconcile_energy(
            int(_safe_int(llm_est.get("estimated_calories"), deterministic["estimated_calories"])),
            int(_safe_int(llm_est.get("estimated_protein_g"), deterministic["estimated_protein_g"])),
            int(_safe_int(llm_est.get("estimated_carbs_g"), deterministic["estimated_carbs_g"])),
            int(_safe_int(llm_est.get("estimated_fat_g"), deterministic["estimated_fat_g"])),
        )
        satiety = str(llm_est.get("estimated_satiety") or _satiety_from_macros(calories, protein_g, carbs_g, fat_g))
        satiety = satiety if satiety in {"low", "medium", "high"} else _satiety_from_macros(calories, protein_g, carbs_g, fat_g)
        confidence = round(
            _clamp(
                _safe_float(llm_est.get("macro_confidence"), float(deterministic["macro_confidence"])),
                0.35,
                0.92,
            ),
            2,
        )

        return {
            "estimated_calories": int(calories),
            "estimated_protein_g": int(protein_g),
            "estimated_carbs_g": int(carbs_g),
            "estimated_fat_g": int(fat_g),
            "estimated_satiety": satiety,
            "macro_confidence": confidence,
            "macro_estimation_version": "v1_llm_optional",
            "estimation_method": "llm",
            "estimation_version": "v1",
            "llm_estimation_attempted": bool(llm_out.get("attempted")),
        }

    return {
        "estimated_calories": int(calories),
        "estimated_protein_g": int(protein_g),
        "estimated_carbs_g": int(carbs_g),
        "estimated_fat_g": int(fat_g),
        "estimated_satiety": satiety,
        "macro_confidence": confidence,
        "macro_estimation_version": MACRO_ESTIMATION_VERSION,
        "estimation_method": "deterministic",
        "estimation_version": "v1",
        "llm_estimation_attempted": bool(llm_out.get("attempted")),
        "llm_fallback_reason": str(llm_out.get("error") or "")[:120] if bool(llm_out.get("attempted")) and not bool(llm_out.get("used")) else "",
    }

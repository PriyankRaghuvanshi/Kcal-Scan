from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class PersonalizationGoal(str, Enum):
    FAT_LOSS = "fat_loss"
    MUSCLE_GAIN = "muscle_gain"
    KETO = "keto"
    HIGH_PROTEIN = "high_protein"
    MAINTENANCE = "maintenance"


_GOAL_ALIASES: Dict[str, PersonalizationGoal] = {
    "fat_loss": PersonalizationGoal.FAT_LOSS,
    "fat-loss": PersonalizationGoal.FAT_LOSS,
    "fat loss": PersonalizationGoal.FAT_LOSS,
    "cut": PersonalizationGoal.FAT_LOSS,
    "cutting": PersonalizationGoal.FAT_LOSS,
    "muscle_gain": PersonalizationGoal.MUSCLE_GAIN,
    "muscle-gain": PersonalizationGoal.MUSCLE_GAIN,
    "muscle gain": PersonalizationGoal.MUSCLE_GAIN,
    "muscle": PersonalizationGoal.MUSCLE_GAIN,
    "bulk": PersonalizationGoal.MUSCLE_GAIN,
    "bulking": PersonalizationGoal.MUSCLE_GAIN,
    "keto": PersonalizationGoal.KETO,
    "ketogenic": PersonalizationGoal.KETO,
    "high_protein": PersonalizationGoal.HIGH_PROTEIN,
    "high-protein": PersonalizationGoal.HIGH_PROTEIN,
    "high protein": PersonalizationGoal.HIGH_PROTEIN,
    "protein": PersonalizationGoal.HIGH_PROTEIN,
    "maintenance": PersonalizationGoal.MAINTENANCE,
    "maintain": PersonalizationGoal.MAINTENANCE,
    "balanced": PersonalizationGoal.MAINTENANCE,
}


_PLACE_WEIGHT_FACTORS_BY_GOAL: Dict[PersonalizationGoal, Dict[str, float]] = {
    PersonalizationGoal.FAT_LOSS: {
        "protein_density": 1.20,
        "calorie_control": 1.35,
        "satiety": 1.05,
        "fat_loss_friendliness": 1.35,
    },
    PersonalizationGoal.MUSCLE_GAIN: {
        "protein_density": 1.55,
        "calorie_control": 0.85,
        "satiety": 1.25,
        "fat_loss_friendliness": 0.75,
    },
    PersonalizationGoal.KETO: {
        "protein_density": 1.28,
        "calorie_control": 0.95,
        "satiety": 1.10,
        "fat_loss_friendliness": 0.90,
    },
    PersonalizationGoal.HIGH_PROTEIN: {
        "protein_density": 1.70,
        "calorie_control": 0.90,
        "satiety": 1.12,
        "fat_loss_friendliness": 0.78,
    },
    PersonalizationGoal.MAINTENANCE: {
        "protein_density": 1.00,
        "calorie_control": 1.00,
        "satiety": 1.15,
        "fat_loss_friendliness": 0.95,
    },
}


_MENU_WEIGHT_FACTORS_BY_GOAL: Dict[PersonalizationGoal, Dict[str, float]] = {
    PersonalizationGoal.FAT_LOSS: {
        "protein_density": 1.18,
        "calorie_control": 1.30,
        "satiety": 1.05,
        "fat_loss_friendliness": 1.30,
    },
    PersonalizationGoal.MUSCLE_GAIN: {
        "protein_density": 1.48,
        "calorie_control": 0.82,
        "satiety": 1.20,
        "fat_loss_friendliness": 0.74,
    },
    PersonalizationGoal.KETO: {
        "protein_density": 1.25,
        "calorie_control": 0.95,
        "satiety": 1.10,
        "fat_loss_friendliness": 0.85,
    },
    PersonalizationGoal.HIGH_PROTEIN: {
        "protein_density": 1.72,
        "calorie_control": 0.90,
        "satiety": 1.08,
        "fat_loss_friendliness": 0.72,
    },
    PersonalizationGoal.MAINTENANCE: {
        "protein_density": 1.00,
        "calorie_control": 1.00,
        "satiety": 1.15,
        "fat_loss_friendliness": 0.95,
    },
}


_GOAL_REASON: Dict[PersonalizationGoal, str] = {
    PersonalizationGoal.FAT_LOSS: "Prioritizes calorie control and protein to support fat loss.",
    PersonalizationGoal.MUSCLE_GAIN: "Prioritizes protein and recovery-friendly meal volume.",
    PersonalizationGoal.KETO: "Prioritizes lower-carb picks with better protein-fat balance.",
    PersonalizationGoal.HIGH_PROTEIN: "Prioritizes maximum protein density per meal.",
    PersonalizationGoal.MAINTENANCE: "Balances calories, satiety, and sustainable nutrition quality.",
}


_ORDER_HINT_BY_GOAL: Dict[PersonalizationGoal, str] = {
    PersonalizationGoal.FAT_LOSS: "light sauce, skip fries",
    PersonalizationGoal.MUSCLE_GAIN: "add extra lean protein",
    PersonalizationGoal.KETO: "swap rice or bread for greens",
    PersonalizationGoal.HIGH_PROTEIN: "double lean protein",
    PersonalizationGoal.MAINTENANCE: "keep a balanced plate",
}


def normalize_personalization_goal(goal: Any) -> PersonalizationGoal | None:
    if isinstance(goal, PersonalizationGoal):
        return goal

    text = str(goal or "").strip().lower()
    if not text:
        return None
    return _GOAL_ALIASES.get(text)


def personalization_goal_value(goal: Any) -> str:
    resolved = normalize_personalization_goal(goal)
    return resolved.value if resolved else ""


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    positive = {k: max(0.0, float(v or 0.0)) for k, v in (weights or {}).items()}
    total = float(sum(positive.values()) or 0.0)
    if total <= 0:
        return dict(weights or {})
    return {k: v / total for k, v in positive.items()}


def _apply_weight_factors(base_weights: Dict[str, float], factors: Dict[str, float]) -> Dict[str, float]:
    adjusted: Dict[str, float] = {}
    for key, value in (base_weights or {}).items():
        adjusted[key] = float(value or 0.0) * float(factors.get(key, 1.0) or 1.0)
    return _normalize_weights(adjusted)


def get_goal_adjusted_place_weights(base_weights: Dict[str, float], goal: Any) -> Dict[str, float]:
    resolved = normalize_personalization_goal(goal)
    if not resolved:
        return dict(base_weights or {})
    factors = _PLACE_WEIGHT_FACTORS_BY_GOAL.get(resolved, {})
    return _apply_weight_factors(base_weights, factors)


def get_goal_adjusted_menu_weights(base_weights: Dict[str, float], goal: Any) -> Dict[str, float]:
    resolved = normalize_personalization_goal(goal)
    if not resolved:
        return dict(base_weights or {})
    factors = _MENU_WEIGHT_FACTORS_BY_GOAL.get(resolved, {})
    return _apply_weight_factors(base_weights, factors)


def get_personalized_reason(goal: Any) -> str:
    resolved = normalize_personalization_goal(goal)
    if not resolved:
        return ""
    return str(_GOAL_REASON.get(resolved, ""))


def personalize_order_for_goal(best_order: str, goal: Any) -> str:
    resolved = normalize_personalization_goal(goal)
    base = str(best_order or "").strip()
    if not resolved or not base:
        return base

    hint = str(_ORDER_HINT_BY_GOAL.get(resolved, "")).strip()
    if not hint:
        return base

    lower = base.lower()
    if hint.lower() in lower:
        return base
    return f"{base} ({hint})"


def goal_menu_macro_adjustment(
    goal: Any,
    *,
    calories: int,
    protein_g: int,
    carbs_g: int,
    fat_g: int,
) -> float:
    resolved = normalize_personalization_goal(goal)
    if not resolved:
        return 0.0

    cals = float(calories)
    protein = float(protein_g)
    carbs = float(carbs_g)
    fat = float(fat_g)

    if resolved == PersonalizationGoal.FAT_LOSS:
        delta = 0.0
        if cals <= 600 and protein >= 35:
            delta += 5.0
        if cals > 650:
            delta -= 5.0
        if cals > 780:
            delta -= 4.0
        if carbs <= 55:
            delta += 1.5
        return delta

    if resolved == PersonalizationGoal.MUSCLE_GAIN:
        delta = 0.0
        if protein >= 40:
            delta += 4.0
        if 520 <= cals <= 900:
            delta += 3.0
        if carbs >= 45:
            delta += 2.0
        if cals < 340:
            delta -= 5.0
        return delta

    if resolved == PersonalizationGoal.KETO:
        delta = 0.0
        if carbs <= 25 and fat >= 18:
            delta += 7.0
        elif carbs <= 40 and fat >= 15:
            delta += 3.0
        if carbs >= 60:
            delta -= 10.0
        if protein >= 30:
            delta += 2.0
        return delta

    if resolved == PersonalizationGoal.HIGH_PROTEIN:
        delta = 0.0
        if protein >= 45:
            delta += 8.0
        elif protein >= 35:
            delta += 4.0
        if protein < 25:
            delta -= 6.0
        return delta

    if resolved == PersonalizationGoal.MAINTENANCE:
        delta = 0.0
        if 450 <= cals <= 800 and protein >= 25:
            delta += 4.0
        if cals > 950 or cals < 280:
            delta -= 4.0
        return delta

    return 0.0

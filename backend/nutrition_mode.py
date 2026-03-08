from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class NutritionMode(str, Enum):
    DEFAULT = "default"
    CUT = "cut"


# Centralized place scoring weights by mode.
PLACE_SCORE_WEIGHTS_BY_MODE: Dict[NutritionMode, Dict[str, float]] = {
    NutritionMode.DEFAULT: {
        "protein_density": 0.30,
        "calorie_control": 0.25,
        "satiety": 0.20,
        "fat_loss_friendliness": 0.25,
    },
    # Cut mode increases emphasis on protein density + calorie control.
    NutritionMode.CUT: {
        "protein_density": 0.38,
        "calorie_control": 0.34,
        "satiety": 0.12,
        "fat_loss_friendliness": 0.16,
    },
}


# Centralized menu-item scoring weights by mode.
MENU_ITEM_SCORE_WEIGHTS_BY_MODE: Dict[NutritionMode, Dict[str, float]] = {
    NutritionMode.DEFAULT: {
        "protein_density": 0.32,
        "calorie_control": 0.28,
        "satiety": 0.20,
        "fat_loss_friendliness": 0.20,
    },
    NutritionMode.CUT: {
        "protein_density": 0.40,
        "calorie_control": 0.35,
        "satiety": 0.10,
        "fat_loss_friendliness": 0.15,
    },
}


def normalize_nutrition_mode(mode: Any) -> NutritionMode:
    if isinstance(mode, NutritionMode):
        return mode

    text = str(mode or "").strip().lower()
    if text in {"cut", "fat_loss", "fat-loss", "cut_mode", "1", "true", "yes", "on"}:
        return NutritionMode.CUT
    return NutritionMode.DEFAULT


def is_cut_mode(mode: Any) -> bool:
    return normalize_nutrition_mode(mode) == NutritionMode.CUT


def get_place_score_weights(mode: Any) -> Dict[str, float]:
    return dict(PLACE_SCORE_WEIGHTS_BY_MODE[normalize_nutrition_mode(mode)])


def get_menu_item_score_weights(mode: Any) -> Dict[str, float]:
    return dict(MENU_ITEM_SCORE_WEIGHTS_BY_MODE[normalize_nutrition_mode(mode)])

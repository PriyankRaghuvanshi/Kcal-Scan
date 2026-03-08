from __future__ import annotations

from typing import Optional

from app.models.meal_scan import MealScanInput, UserNutritionProfile
from app.models.supplement_scan import (
    NutritionInsightsOutput,
    RecommendationItem,
    SupplementScanInput,
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _build_recommendations(
    meal: MealScanInput,
    supplement: Optional[SupplementScanInput],
    profile: UserNutritionProfile,
    satiety_score: float,
    fat_loss_score: float,
    macro_balance_score: float,
) -> tuple[list[RecommendationItem], list[str]]:
    recommendations: list[RecommendationItem] = []
    warnings: list[str] = []

    protein_density = (meal.protein_g / max(meal.calories, 1.0)) * 100.0

    if profile.goal == "fat_loss" and meal.calories > (profile.target_calories or 2000) * 0.45:
        recommendations.append(
            RecommendationItem(
                title="Reduce meal energy load",
                reason="This meal occupies a large share of your daily calorie budget.",
                action="Trim calorie-dense extras and increase low-calorie vegetables.",
                priority="high",
            )
        )

    if protein_density < 8:
        recommendations.append(
            RecommendationItem(
                title="Increase protein density",
                reason="Higher protein density improves satiety and supports fat-loss goals.",
                action="Add lean protein (chicken, fish, egg whites, Greek yogurt, tofu).",
                priority="high",
            )
        )

    if meal.fiber_g < 8:
        recommendations.append(
            RecommendationItem(
                title="Improve fiber intake",
                reason="Fiber is low for this meal, reducing fullness and glucose stability.",
                action="Add salad, vegetables, legumes, or whole grains.",
                priority="medium",
            )
        )

    if meal.sugar_g > 25:
        recommendations.append(
            RecommendationItem(
                title="Lower added sugar",
                reason="Higher sugar load can reduce satiety and increase cravings.",
                action="Swap sugary sauces/drinks for low-sugar options.",
                priority="medium",
            )
        )

    if meal.sodium_mg > 1500:
        warnings.append("Meal sodium is high and may impact water retention.")

    if supplement is not None:
        daily_caffeine = supplement.caffeine_mg * supplement.servings_per_day

        if daily_caffeine > 300:
            warnings.append("Supplement caffeine is high for a fat-loss cut day.")
            recommendations.append(
                RecommendationItem(
                    title="Re-time or reduce stimulant load",
                    reason="Higher stimulant intake may hurt recovery and sleep quality.",
                    action="Cap caffeine earlier in the day and consider lower-stim formulas.",
                    priority="high",
                )
            )

        if supplement.authenticity_score is not None and supplement.authenticity_score < 60:
            warnings.append("Supplement authenticity confidence is low.")
            recommendations.append(
                RecommendationItem(
                    title="Verify supplement source",
                    reason="Low authenticity confidence increases product risk.",
                    action="Use trusted distributors and confirm batch/licensing details.",
                    priority="high",
                )
            )

        if supplement.risk_flags:
            warnings.append("Supplement risk flags were detected in scan output.")

    if satiety_score >= 75 and fat_loss_score >= 75 and macro_balance_score >= 70:
        recommendations.append(
            RecommendationItem(
                title="Meal is fat-loss friendly",
                reason="Current meal composition supports satiety and calorie control.",
                action="Keep this structure for consistency across the week.",
                priority="low",
            )
        )

    return recommendations, warnings


def generate_nutrition_insights(
    meal_scan: MealScanInput,
    supplement_scan: Optional[SupplementScanInput] = None,
    user_profile: Optional[UserNutritionProfile] = None,
) -> NutritionInsightsOutput:
    if meal_scan is None:
        raise ValueError("meal_scan is required")

    profile = user_profile or UserNutritionProfile()

    supplement_calories = 0.0
    supplement_protein = 0.0
    supplement_carbs = 0.0
    supplement_fat = 0.0
    supplement_safety_score = 85.0
    supplement_confidence = 0.75

    if supplement_scan is not None:
        supplement_calories = supplement_scan.calories * supplement_scan.servings_per_day
        supplement_protein = supplement_scan.protein_g * supplement_scan.servings_per_day
        supplement_carbs = supplement_scan.carbs_g * supplement_scan.servings_per_day
        supplement_fat = supplement_scan.fat_g * supplement_scan.servings_per_day

        caffeine_penalty = _clamp((supplement_scan.caffeine_mg * supplement_scan.servings_per_day - 200) * 0.12, 0, 25)
        risk_penalty = min(len(supplement_scan.risk_flags) * 8.0, 24.0)
        authenticity_bonus = 0.0
        if supplement_scan.authenticity_score is not None:
            authenticity_bonus = _clamp((supplement_scan.authenticity_score - 70.0) * 0.25, -15.0, 8.0)
            supplement_confidence = _clamp(supplement_scan.authenticity_score / 100.0, 0.2, 1.0)

        supplement_safety_score = _clamp(82.0 - caffeine_penalty - risk_penalty + authenticity_bonus, 0, 100)

    combined_calories = meal_scan.calories + supplement_calories
    combined_protein = meal_scan.protein_g + supplement_protein
    combined_carbs = meal_scan.carbs_g + supplement_carbs
    combined_fat = meal_scan.fat_g + supplement_fat

    target_calories = profile.target_calories or 2000
    per_meal_budget = target_calories / (4.0 if profile.workout_day else 4.5)
    calorie_penalty = _clamp((combined_calories - per_meal_budget) / max(per_meal_budget, 1.0) * 35.0, 0, 40)

    protein_density = (combined_protein / max(combined_calories, 1.0)) * 100.0
    fiber_density = (meal_scan.fiber_g / max(meal_scan.calories, 1.0)) * 100.0
    sugar_density = (meal_scan.sugar_g / max(meal_scan.calories, 1.0)) * 100.0

    satiety_score = _clamp(45.0 + protein_density * 3.0 + fiber_density * 4.0 - sugar_density * 2.5, 0, 100)

    target_protein = profile.target_protein_g or 140
    meal_protein_target = target_protein / 4.0
    protein_gap_penalty = _clamp((meal_protein_target - combined_protein) * 1.2, 0, 35)
    sodium_penalty = _clamp((meal_scan.sodium_mg - 1200) / 50.0, 0, 20)

    fat_loss_score = _clamp(88.0 - calorie_penalty - protein_gap_penalty - sodium_penalty, 0, 100)

    protein_ratio = (combined_protein * 4.0) / max(combined_calories, 1.0)
    fat_ratio = (combined_fat * 9.0) / max(combined_calories, 1.0)
    carbs_ratio = (combined_carbs * 4.0) / max(combined_calories, 1.0)

    macro_balance_score = _clamp(
        100.0
        - abs(protein_ratio - 0.30) * 140
        - abs(fat_ratio - 0.30) * 110
        - abs(carbs_ratio - 0.40) * 80,
        0,
        100,
    )

    recommendations, warnings = _build_recommendations(
        meal=meal_scan,
        supplement=supplement_scan,
        profile=profile,
        satiety_score=satiety_score,
        fat_loss_score=fat_loss_score,
        macro_balance_score=macro_balance_score,
    )

    recommendation_summary = (
        "Strong fat-loss meal pattern. Keep consistency and hydration high."
        if fat_loss_score >= 75 and satiety_score >= 70
        else "Meal + supplement pattern needs small adjustments for better fat-loss outcomes."
    )

    combined_confidence = _clamp((meal_scan.confidence + supplement_confidence) / 2.0, 0.0, 1.0)

    return NutritionInsightsOutput(
        recommendation_summary=recommendation_summary,
        fat_loss_score=round(fat_loss_score, 1),
        satiety_score=round(satiety_score, 1),
        macro_balance_score=round(macro_balance_score, 1),
        supplement_safety_score=round(supplement_safety_score, 1),
        estimated_daily_calories=round(combined_calories, 1),
        combined_confidence=round(combined_confidence, 3),
        recommendations=recommendations,
        warnings=warnings,
        signals={
            "protein_density": round(protein_density, 2),
            "fiber_density": round(fiber_density, 2),
            "sugar_density": round(sugar_density, 2),
            "meal_budget_kcal": round(per_meal_budget, 1),
        },
    )

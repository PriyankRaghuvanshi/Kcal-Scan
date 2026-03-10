"""
Tests for context-aware ranking: inference and scoring.
"""
from __future__ import annotations

import unittest

from context_modes import infer_context_mode
from context_scoring import compute_context_modifier


def _place_profile(
    recommended_order: str = "Tandoori chicken",
    estimated_calories: float = 520,
    estimated_protein_g: float = 35,
    meal_fitness_score_100: float = 72,
    food_quality_score_100: float = 75,
    protein_density_score_100: float = 70,
    satiety: float = 65,
    name: str = "Indian Grill",
) -> dict:
    return {
        "recommended_order": recommended_order,
        "best_order": recommended_order,
        "name": name,
        "estimated_calories": estimated_calories,
        "estimated_protein_g": estimated_protein_g,
        "meal_fitness_score_100": meal_fitness_score_100,
        "food_quality_score_100": food_quality_score_100,
        "protein_density_score_100": protein_density_score_100,
        "score_breakdown": {"satiety": satiety},
    }


class TestContextInference(unittest.TestCase):
    def test_no_flags_default_mode(self):
        out = infer_context_mode({"local_hour": 4})
        self.assertEqual(out["context_mode"], "default")
        self.assertFalse(out["context_flags"].get("post_workout_recovery"))
        self.assertFalse(out["context_flags"].get("late_night_damage_control"))
        self.assertIn("context_reason", out)

    def test_post_workout_flag(self):
        out = infer_context_mode({"post_workout": True})
        self.assertEqual(out["context_mode"], "post_workout_recovery")
        self.assertTrue(out["context_flags"]["post_workout_recovery"])

    def test_late_night_by_hour(self):
        out = infer_context_mode({"local_hour": 22})
        self.assertEqual(out["context_mode"], "late_night_damage_control")
        self.assertTrue(out["context_flags"]["late_night_damage_control"])

    def test_breakfast_mode_by_hour(self):
        out = infer_context_mode({"local_hour": 8})
        self.assertEqual(out["context_mode"], "breakfast_mode")
        self.assertTrue(out["context_flags"]["breakfast_mode"])

    def test_low_calorie_remaining(self):
        out = infer_context_mode({"remaining_calories": 200})
        self.assertTrue(out["context_flags"]["low_calorie_remaining"])

    def test_high_protein_recovery_needed(self):
        out = infer_context_mode({"remaining_protein_g": 50})
        self.assertTrue(out["context_flags"]["high_protein_recovery_needed"])

    def test_explicit_override_wins(self):
        out = infer_context_mode({
            "post_workout": True,
            "context_mode_override": "breakfast_mode",
        })
        self.assertEqual(out["context_mode"], "breakfast_mode")


class TestNoContextApplied(unittest.TestCase):
    """A. No context applied: no flags => context_net_100 == 0, context_applied == False."""

    def test_no_context_flags_zero_net(self):
        profile = _place_profile()
        context_info = {"context_flags": {}, "context_mode": "default", "remaining_calories": 500, "remaining_protein_g": 20}
        out = compute_context_modifier(profile, context_info, {})
        self.assertEqual(out["context_net_100"], 0)
        self.assertFalse(out["context_applied"])
        self.assertEqual(out["context_bonus_100"], 0)
        self.assertEqual(out["context_penalty_100"], 0)


class TestPostWorkoutBoost(unittest.TestCase):
    """B. Post-workout: high-protein meal boosted, weak-protein meal penalized."""

    def test_high_protein_meal_gets_boost(self):
        profile = _place_profile("Grilled chicken + dal", estimated_protein_g=42)
        context_info = {
            "context_flags": {"post_workout_recovery": True},
            "context_mode": "post_workout_recovery",
            "remaining_calories": 600,
            "remaining_protein_g": 30,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertGreater(out["context_net_100"], 0)
        self.assertTrue(out["context_applied"])

    def test_weak_protein_meal_gets_penalty_or_neutral(self):
        profile = _place_profile("Juice and smoothie", estimated_protein_g=8, food_quality_score_100=55, protein_density_score_100=25)
        context_info = {
            "context_flags": {"post_workout_recovery": True},
            "context_mode": "post_workout_recovery",
            "remaining_calories": 600,
            "remaining_protein_g": 30,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertLessEqual(out["context_net_100"], 0)


class TestLateNightPenalty(unittest.TestCase):
    """C. Late-night: combo/processed penalized, lighter option favored."""

    def test_combo_meal_penalized(self):
        profile = _place_profile(
            "Burger combo with fries and drink",
            estimated_calories=750,
            estimated_protein_g=25,
            food_quality_score_100=45,
            satiety=35,
        )
        context_info = {
            "context_flags": {"late_night_damage_control": True},
            "context_mode": "late_night_damage_control",
            "remaining_calories": 800,
            "remaining_protein_g": 20,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertLess(out["context_net_100"], 0)

    def test_light_meal_favored(self):
        profile = _place_profile(
            "Grilled chicken wrap",
            estimated_calories=380,
            estimated_protein_g=32,
            satiety=65,
            food_quality_score_100=70,
        )
        context_info = {
            "context_flags": {"late_night_damage_control": True},
            "context_mode": "late_night_damage_control",
            "remaining_calories": 500,
            "remaining_protein_g": 25,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertGreater(out["context_net_100"], 0)


class TestLowCaloriesRemaining(unittest.TestCase):
    """D. Low calories remaining: 200 left; 190 kcal meal positive, 400 kcal meal penalized."""

    def test_low_cal_meal_boosted(self):
        profile = _place_profile(estimated_calories=190)
        context_info = {
            "context_flags": {"low_calorie_remaining": True},
            "context_mode": "default",
            "remaining_calories": 200,
            "remaining_protein_g": 20,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertGreater(out["context_net_100"], 0)

    def test_high_cal_meal_penalized(self):
        profile = _place_profile(estimated_calories=400)
        context_info = {
            "context_flags": {"low_calorie_remaining": True},
            "context_mode": "default",
            "remaining_calories": 200,
            "remaining_protein_g": 20,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertLess(out["context_net_100"], 0)


class TestHighProteinRemaining(unittest.TestCase):
    """E. High protein remaining: 50g left; 40g meal boosted, 15g meal penalized."""

    def test_high_protein_meal_boosted(self):
        profile = _place_profile(estimated_protein_g=40)
        context_info = {
            "context_flags": {"high_protein_recovery_needed": True},
            "context_mode": "default",
            "remaining_calories": 600,
            "remaining_protein_g": 50,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertGreater(out["context_net_100"], 0)

    def test_low_protein_meal_penalized(self):
        profile = _place_profile(estimated_protein_g=15, protein_density_score_100=40)
        context_info = {
            "context_flags": {"high_protein_recovery_needed": True},
            "context_mode": "default",
            "remaining_calories": 600,
            "remaining_protein_g": 50,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertLess(out["context_net_100"], 0)


class TestBreakfastMode(unittest.TestCase):
    """F. Breakfast mode: eggs/omelette boosted, pastry penalized."""

    def test_breakfast_friendly_boosted(self):
        profile = _place_profile("Eggs and idli with sambar", estimated_protein_g=25)
        context_info = {
            "context_flags": {"breakfast_mode": True},
            "context_mode": "breakfast_mode",
            "remaining_calories": 500,
            "remaining_protein_g": 25,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertGreater(out["context_net_100"], 0)

    def test_pastry_penalized(self):
        profile = _place_profile("Pastry and muffin", estimated_protein_g=8)
        context_info = {
            "context_flags": {"breakfast_mode": True},
            "context_mode": "breakfast_mode",
            "remaining_calories": 500,
            "remaining_protein_g": 25,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertLess(out["context_net_100"], 0)


class TestCombinationAndCap(unittest.TestCase):
    """G. Many positive flags => context_net_100 <= 8."""

    def test_net_capped_at_8(self):
        profile = _place_profile(
            "Grilled chicken + dal",
            estimated_calories=450,
            estimated_protein_g=45,
            satiety=70,
            food_quality_score_100=80,
            protein_density_score_100=85,
        )
        context_info = {
            "context_flags": {
                "post_workout_recovery": True,
                "late_night_damage_control": True,
                "low_calorie_remaining": True,
                "high_protein_recovery_needed": True,
                "breakfast_mode": False,
                "lunch_mode": False,
                "dinner_mode": False,
                "poor_sleep_flag": True,
                "high_craving_risk_flag": True,
            },
            "context_mode": "post_workout_recovery",
            "remaining_calories": 200,
            "remaining_protein_g": 50,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertLessEqual(out["context_net_100"], 8)
        self.assertGreaterEqual(out["context_net_100"], -8)


class TestWeakMealSafeguard(unittest.TestCase):
    """H. Weak processed meal with favorable context => positive dampened, cannot leapfrog."""

    def test_weak_meal_context_dampened(self):
        profile = _place_profile(
            "Burger combo with fries",
            estimated_calories=200,
            estimated_protein_g=40,
            meal_fitness_score_100=45,
            food_quality_score_100=35,
            protein_density_score_100=70,
        )
        context_info = {
            "context_flags": {
                "post_workout_recovery": True,
                "low_calorie_remaining": True,
                "high_protein_recovery_needed": True,
            },
            "context_mode": "post_workout_recovery",
            "remaining_calories": 250,
            "remaining_protein_g": 45,
        }
        out = compute_context_modifier(profile, context_info, {})
        self.assertLessEqual(out["context_net_100"], 2, "meal_fitness < 50 => max +2 bonus")


if __name__ == "__main__":
    unittest.main()

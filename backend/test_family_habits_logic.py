import unittest

from family_habits_logic import (
    build_exposure_summary,
    build_family_memory_snapshot,
    build_rescue_response,
    build_weekly_reset,
    recommend_one_meal_tonight,
)


class FamilyHabitsLogicTests(unittest.TestCase):
    def test_meal_recommendation_prefers_safe_coverage_and_low_friction(self):
        out = recommend_one_meal_tonight(
            household={"goal": "one family meal"},
            children=[{"child_id": "c1", "display_name": "Mia"}],
            safe_foods=[{"child_id": "c1", "food_name": "rice"}],
            target_foods=[{"child_id": "c1", "food_name": "beans"}],
            recent_exposures=[{"child_id": "c1", "food_name": "broccoli", "response_stage": "offered"}],
            family_memory={"successful_meals": [{"meal_name": "Build-your-own taco bowls"}]},
            time_available_min=20,
            parent_energy_level="low",
            available_items=["rice", "beans", "cheese"],
            dinner_goal="one meal",
        )
        self.assertEqual(out["meal_name"], "Build-your-own taco bowls")
        self.assertEqual(out["safe_component"], "rice")
        self.assertEqual(out["exposure_component"], "beans")
        self.assertIn("safe_food_coverage", out["reasoning_tags"])

    def test_exposure_summary_derives_progress_state(self):
        summary = build_exposure_summary(
            [
                {"child_id": "c1", "food_name": "carrot", "food_format": "sticks", "paired_safe_food": "crackers", "response_stage": "offered", "created_at": "2026-03-20T10:00:00Z"},
                {"child_id": "c1", "food_name": "carrot", "food_format": "sticks", "paired_safe_food": "crackers", "response_stage": "tasted", "created_at": "2026-03-21T10:00:00Z"},
                {"child_id": "c1", "food_name": "carrot", "food_format": "coins", "paired_safe_food": "crackers", "response_stage": "accepted", "created_at": "2026-03-22T10:00:00Z"},
            ]
        )
        row = summary["summaries"][0]
        self.assertEqual(row["times_offered"], 3)
        self.assertEqual(row["times_tasted"], 2)
        self.assertEqual(row["times_accepted"], 1)
        self.assertEqual(row["progress_state"], "accepted_in_some_formats")
        self.assertEqual(row["best_pairing"], "crackers")

    def test_rescue_response_is_guardrailed(self):
        out = build_rescue_response("making_separate_meals", {"child_name": "Ava"})
        self.assertIn("one family meal", out["what_to_say"].lower())
        self.assertTrue(any("No calorie" in rule for rule in out["guardrails"]))

    def test_weekly_reset_detects_drift_and_repeat_meal(self):
        out = build_weekly_reset(
            meals_served=[
                {"meal_name": "Build-your-own taco bowls", "date_served": "2026-03-25T18:00:00Z", "separate_meals_needed": False},
                {"meal_name": "Build-your-own taco bowls", "date_served": "2026-03-24T18:00:00Z", "separate_meals_needed": False},
                {"meal_name": "Snack plate dinner", "date_served": "2026-03-23T18:00:00Z", "separate_meals_needed": True, "is_takeaway": False},
            ],
            child_outcomes=[],
            exposures=[
                {"child_id": "c1", "food_name": "cucumber", "response_stage": "offered", "created_at": "2026-03-23T18:00:00Z"},
                {"child_id": "c1", "food_name": "cucumber", "response_stage": "offered", "created_at": "2026-03-24T18:00:00Z"},
                {"child_id": "c1", "food_name": "cucumber", "response_stage": "offered", "created_at": "2026-03-25T18:00:00Z"},
            ],
            rescue_sessions=[{"issue_type": "making_separate_meals", "created_at": "2026-03-24T18:30:00Z"}],
            routine_signals=[{"signal_type": "late_decision", "created_at": "2026-03-25T17:00:00Z"}],
        )
        self.assertEqual(out["meal_to_repeat"], "Build-your-own taco bowls")
        self.assertEqual(out["exposure_to_retry"], "cucumber")
        self.assertIn("strongest_drift", out)

    def test_family_memory_snapshot_collects_pairings(self):
        out = build_family_memory_snapshot(
            meals_served=[{"meal_name": "Breakfast-for-dinner"}, {"meal_name": "Breakfast-for-dinner"}],
            exposures=[{"food_name": "egg", "paired_safe_food": "toast"}],
            rescue_sessions=[{"issue_type": "refusing_dinner"}],
        )
        self.assertEqual(out["successful_meals"][0]["meal_name"], "Breakfast-for-dinner")
        self.assertEqual(out["successful_pairings"][0]["paired_safe_food"], "toast")
        self.assertIn("refusing_dinner", out["risk_contexts"])


if __name__ == "__main__":
    unittest.main()

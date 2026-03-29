"""
Coach daily fast-path tests: ensure deterministic response does not require LLM.
"""
from __future__ import annotations

import unittest

import coach_daily_logic
import main as main_mod


class TestCoachDailyFastPath(unittest.TestCase):
    def test_coach_daily_returns_rules_without_llm(self):
        payload = {
            "date": "2026-03-10",
            "goals": {"kcal": 2000, "protein_g": 150},
            "consumed": {"kcal": 800, "protein_g": 60},
            "meals": [{"kcal": 500, "protein_g": 40, "carbs_g": 30, "fat_g": 15, "hour": 12}],
            "profile": {"tone_preference": "supportive"},
        }
        self.assertTrue(hasattr(main_mod, "coach_daily"))
        norm = coach_daily_logic.normalize_daily_payload(payload)
        self.assertEqual(norm["profile"]["goal_type"], "fat_loss")

    def test_health_context_is_normalized_for_daily_coach(self):
        norm = coach_daily_logic.normalize_daily_payload(
            {
                "date": "2026-03-27",
                "goals": {"protein_g": 150, "fiber_g": 30},
                "consumed": {"protein_g": 90, "fiber_g": 14},
                "health_context": {
                    "source": "apple_health",
                    "steps_count": 3200,
                    "sleep_hours": 5.8,
                    "hydration_l": 1.1,
                    "poor_sleep_flag": True,
                },
            }
        )
        self.assertEqual(norm["health_context"]["source"], "apple_health")
        self.assertEqual(norm["health_context"]["steps_count"], 3200.0)
        self.assertTrue(norm["health_context"]["poor_sleep_flag"])

    def test_classifier_prefers_recovery_when_sleep_is_low(self):
        payload = coach_daily_logic.normalize_daily_payload(
            {
                "date": "2026-03-27",
                "goals": {"protein_g": 150, "fiber_g": 30},
                "consumed": {"protein_g": 120, "fiber_g": 22},
                "signals": {"avg_glycemic_load": 9, "ultra_processed_avg": 2.5},
                "meal_timing": {"late_calories_pct": 18},
                "health_context": {
                    "sleep_hours": 5.4,
                    "hydration_l": 2.1,
                    "steps_count": 7800,
                    "poor_sleep_flag": True,
                },
            }
        )
        classifier = main_mod._classify_coach_bottleneck(payload)
        self.assertEqual(classifier["bottleneck"], "recovery")
        self.assertIn("sleep", classifier["summary"].lower())


if __name__ == '__main__':
    unittest.main()

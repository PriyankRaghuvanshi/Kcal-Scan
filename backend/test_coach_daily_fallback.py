import unittest

import coach_daily_logic as cd


class CoachDailyFallbackTests(unittest.TestCase):
    def _minimal_norm(self, **extra):
        base = {
            "date": "2026-03-28",
            "goals": {"kcal": 2000, "protein_g": 150, "carbs_g": 200, "fat_g": 70, "fiber_g": 30},
            "consumed": {"kcal": 1200, "protein_g": 40, "carbs_g": 120, "fat_g": 40, "fiber_g": 5},
            "signals": {
                "leucine_triggers": {"target": 3, "hit": 1},
                "avg_satiety": 50,
                "avg_glycemic_load": 18,
                "ultra_processed_avg": 5,
            },
            "meal_timing": {"late_calories_pct": 30, "biggest_meal": "dinner"},
            "constraints": {"diet": "non-veg", "allergies": [], "region": "US"},
            "profile": {"goal_type": "fat_loss", "diet_style": "non-veg", "training_days_per_week": 3, "training_time": "evening"},
            "health_context": {
                "source": "apple_health",
                "steps_count": 0,
                "sleep_hours": 0,
                "hydration_l": 0,
                "poor_sleep_flag": False,
                "low_hydration_flag": False,
                "low_steps_flag": False,
            },
        }
        base.update(extra)
        return base

    def test_health_context_adds_recovery_action(self):
        norm = self._minimal_norm()
        norm["health_context"] = {
            "source": "apple_health",
            "sleep_hours": 5.5,
            "poor_sleep_flag": True,
            "steps_count": 8000,
            "hydration_l": 2.0,
            "low_hydration_flag": False,
            "low_steps_flag": False,
        }
        out = cd.build_fallback_coach_response(norm, 55, [], recent_advice_keys=[], client_memory=None)
        titles = " ".join((a.get("title") or "") for a in (out.get("actions") or []))
        self.assertIn("recovery", titles.lower())

    def test_fiber_fatigue_rotates_primary(self):
        norm = self._minimal_norm()
        tired_fiber = ["add_fiber_veg", "flatten_glycemic_spike", "add_fiber_veg"]
        out_tired = cd.build_fallback_coach_response(norm, 55, [], recent_advice_keys=tired_fiber, client_memory=None)
        out_fresh = cd.build_fallback_coach_response(norm, 55, [], recent_advice_keys=[], client_memory=None)
        self.assertNotEqual(
            (out_fresh.get("biggest_risk_lever") or {}).get("title"),
            (out_tired.get("biggest_risk_lever") or {}).get("title"),
        )

    def test_client_memory_in_diagnosis(self):
        norm = self._minimal_norm()
        out = cd.build_fallback_coach_response(
            norm,
            55,
            [],
            client_memory={"food_preferences": ["oatmeal mornings"], "goal_reminders": ["sleep by 11"]},
        )
        blob = " ".join(out.get("diagnosis") or [])
        self.assertIn("oatmeal", blob.lower())
        self.assertIn("sleep", blob.lower())


if __name__ == "__main__":
    unittest.main()

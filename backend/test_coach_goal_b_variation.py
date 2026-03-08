import unittest

try:
    import main as appmod
    _IMPORT_ERR = ""
except ModuleNotFoundError as e:
    appmod = None
    _IMPORT_ERR = str(e)


@unittest.skipIf(appmod is None, f"main dependencies unavailable: {_IMPORT_ERR}")
class CoachGoalBVariationTests(unittest.TestCase):
    def test_theme_rotation_avoids_recent_theme_when_possible(self):
        payload = {
            "date": "2026-03-01",
            "goals": {"kcal": 2200, "protein_g": 180, "carbs_g": 200, "fat_g": 70, "fiber_g": 30},
            "consumed": {"kcal": 1700, "protein_g": 95, "carbs_g": 170, "fat_g": 55, "fiber_g": 12},
            "signals": {"avg_glycemic_load": 24, "ultra_processed_avg": 5.2, "avg_satiety": 45},
            "meal_timing": {"late_calories_pct": 62},
            "profile": {"diet_style": "non-veg", "training_time": "evening"},
        }
        coach_resp = {
            "tone_requested": "supportive",
            "predictive_signals": {
                "projection_confidence_band": "medium",
                "days_with_data_7d": 5,
            },
        }
        out = appmod._apply_dynamic_coach_copy(
            coach_resp,
            payload,
            user_id="user-1",
            day_iso="2026-03-01",
            scan_id="scan-abc123",
            scan_count=3,
            recent_messages=["Protein timing is still behind by about 85g."],
            recent_themes=["protein_push"],
        )
        self.assertIn(out.get("coach_theme"), appmod._COACH_THEME_IDS)
        self.assertNotEqual(out.get("coach_theme"), "protein_push")
        self.assertTrue(str(out.get("one_sentence_summary") or "").strip())

    def test_classifier_prefers_protein_when_gl_only_moderate(self):
        payload = {
            "goals": {"protein_g": 160, "fiber_g": 30},
            "consumed": {"protein_g": 105, "fiber_g": 22},
            "signals": {"avg_glycemic_load": 20, "ultra_processed_avg": 2.0},
            "meal_timing": {"late_calories_pct": 10},
        }
        c = appmod._classify_coach_bottleneck(payload)
        self.assertEqual(c.get("bottleneck"), "protein")


if __name__ == "__main__":
    unittest.main()

import unittest

from day_coach import build_day_coach_payload


class DayCoachPayloadTests(unittest.TestCase):
    def test_strong_start_summary_and_progress(self):
        out = build_day_coach_payload(
            lunch_cards=[
                {
                    "card_type": "best_right_now",
                    "place_name": "Nando's",
                    "recommended_order": "Quarter chicken + salad",
                    "estimated_calories": 540,
                    "estimated_protein_g": 44,
                    "fit_for_today": True,
                }
            ],
            target_calories=2000,
            consumed_calories=700,
            remaining_calories=1300,
            target_protein_g=150,
            consumed_protein_g=60,
            remaining_protein_g=90,
            goal="fat_loss",
            cut_mode=True,
            current_hour=12,
        )

        self.assertIsInstance(out.get("day_summary"), dict)
        self.assertIn("good start", str(out["day_summary"].get("headline") or "").lower())
        progress = out["day_summary"].get("progress") or {}
        self.assertEqual(progress.get("remaining_calories"), 1300.0)
        self.assertEqual(progress.get("remaining_protein_g"), 90.0)
        self.assertIsInstance(out.get("next_meal_guidance"), dict)
        self.assertIn(out["day_summary"].get("phrasing_method"), {"deterministic", "llm"})
        self.assertEqual(out["day_summary"].get("phrasing_version"), "v1")

    def test_low_protein_guidance_uses_next_meal(self):
        out = build_day_coach_payload(
            lunch_cards=[
                {
                    "card_type": "best_right_now",
                    "place_name": "Protein Bowl Lab",
                    "recommended_order": "Chicken bowl",
                    "estimated_calories": 520,
                    "estimated_protein_g": 40,
                    "fit_for_today": True,
                }
            ],
            remaining_calories=1100,
            remaining_protein_g=95,
            goal="fat_loss",
            cut_mode=True,
            current_hour=13,
        )

        next_meal = out.get("next_meal_guidance") or {}
        self.assertEqual(next_meal.get("recommended_place_name"), "Protein Bowl Lab")
        self.assertIn("protein", str(next_meal.get("supporting_text") or "").lower())

    def test_tight_calories_generates_evening_guidance(self):
        out = build_day_coach_payload(
            lunch_cards=[],
            remaining_calories=280,
            remaining_protein_g=35,
            current_hour=16,
            goal="fat_loss",
            cut_mode=True,
        )

        self.assertIn("tight", str(out["day_summary"].get("headline") or "").lower())
        self.assertIsInstance(out.get("evening_guidance"), dict)
        self.assertIn("lighter", str(out["evening_guidance"].get("headline") or "").lower())

    def test_end_of_day_feedback_generated(self):
        out = build_day_coach_payload(
            lunch_cards=[],
            target_calories=2000,
            consumed_calories=1980,
            target_protein_g=150,
            consumed_protein_g=140,
            current_hour=20,
        )

        self.assertIsInstance(out.get("end_of_day_feedback"), dict)
        self.assertEqual(out["end_of_day_feedback"].get("score_label"), "On Track")

    def test_sparse_data_fallback(self):
        out = build_day_coach_payload()
        self.assertIsInstance(out.get("day_summary"), dict)
        self.assertTrue(str(out["day_summary"].get("headline") or "").strip())
        self.assertNotIn("next_meal_guidance", out)


if __name__ == "__main__":
    unittest.main()

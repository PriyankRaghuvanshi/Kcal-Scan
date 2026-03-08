import unittest

from place_today_decision import evaluate_place_for_today


class PlaceTodayDecisionTests(unittest.TestCase):
    def test_high_calorie_place_is_no(self):
        out = evaluate_place_for_today(
            estimated_calories=980,
            estimated_protein_g=24,
            remaining_calories=520,
            remaining_protein_g=60,
            health_score=4.1,
        )

        self.assertEqual(out["decision_today"], "NO")
        self.assertFalse(out["fits_remaining_calories"])
        self.assertIn("calorie", str(out["decision_reason"]).lower())

    def test_moderate_place_is_maybe(self):
        out = evaluate_place_for_today(
            estimated_calories=760,
            estimated_protein_g=33,
            remaining_calories=700,
            remaining_protein_g=45,
            health_score=6.3,
        )

        self.assertEqual(out["decision_today"], "MAYBE")
        self.assertFalse(out["fits_remaining_calories"])
        self.assertGreaterEqual(float(out["decision_confidence"]), 0.4)

    def test_high_protein_balanced_place_is_yes(self):
        out = evaluate_place_for_today(
            estimated_calories=540,
            estimated_protein_g=44,
            remaining_calories=1300,
            remaining_protein_g=90,
            health_score=8.2,
        )

        self.assertEqual(out["decision_today"], "YES")
        self.assertTrue(out["fits_remaining_calories"])
        self.assertTrue(out["fits_remaining_protein"])
        self.assertIn("protein", str(out["decision_reason"]).lower())

    def test_missing_context_skips_safely(self):
        out = evaluate_place_for_today(
            estimated_calories=540,
            estimated_protein_g=44,
        )

        self.assertIsNone(out["decision_today"])
        self.assertIsNone(out["decision_confidence"])


if __name__ == "__main__":
    unittest.main()

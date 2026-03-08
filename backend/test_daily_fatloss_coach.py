import unittest

from daily_fatloss_coach import build_daily_fatloss_coach_response, build_daily_context


class DailyFatLossCoachTests(unittest.TestCase):
    def test_high_remaining_calories_and_protein(self):
        nearby_places = [
            {
                "name": "Protein Grill House",
                "types": ["restaurant", "meal_takeaway"],
                "vicinity": "Main Road",
            },
            {
                "name": "Fast Burger Corner",
                "types": ["restaurant", "fast_food", "burger"],
                "vicinity": "Main Road",
            },
        ]

        out = build_daily_fatloss_coach_response(
            nearby_places=nearby_places,
            target_calories=2200,
            consumed_calories=700,
            target_protein_g=160,
            consumed_protein_g=60,
            limit=5,
        )

        ctx = out["daily_context"]
        self.assertEqual(ctx["remaining_calories"], 1500.0)
        self.assertEqual(ctx["remaining_protein_g"], 100.0)
        self.assertGreater(len(out["best_next_meals_nearby"]), 0)

        top = out["best_next_meals_nearby"][0]
        self.assertIn("fit_for_today", top)
        self.assertIn("best_order", top)
        self.assertIn("estimated_calories", top)
        self.assertIn("estimated_protein_g", top)

    def test_low_remaining_calories_marks_non_fit_options(self):
        nearby_places = [
            {
                "name": "Loaded Pizza Hub",
                "types": ["restaurant", "pizza"],
                "vicinity": "Center",
            },
            {
                "name": "Fried Burger Point",
                "types": ["restaurant", "fast_food", "burger"],
                "vicinity": "Center",
            },
        ]

        out = build_daily_fatloss_coach_response(
            nearby_places=nearby_places,
            target_calories=2000,
            consumed_calories=1900,
            target_protein_g=150,
            consumed_protein_g=120,
            limit=5,
        )

        self.assertEqual(out["daily_context"]["remaining_calories"], 100.0)
        self.assertTrue(all(not row["fit_for_today"] for row in out["best_next_meals_nearby"]))
        self.assertGreaterEqual(len(out["calorie_dense_warnings"]), 1)

    def test_place_fit_vs_not_fit(self):
        nearby_places = [
            {
                "name": "Meal Fit Kitchen",
                "types": ["restaurant"],
                "menu_items": [
                    {
                        "item_name": "Chicken salad bowl",
                        "estimated_calories": 420,
                        "estimated_protein_g": 38,
                        "estimated_satiety": "high",
                    }
                ],
            },
            {
                "name": "Heavy Combo Spot",
                "types": ["restaurant"],
                "menu_items": [
                    {
                        "item_name": "Loaded fried combo",
                        "estimated_calories": 980,
                        "estimated_protein_g": 22,
                        "estimated_satiety": "low",
                    }
                ],
            },
        ]

        out = build_daily_fatloss_coach_response(
            nearby_places=nearby_places,
            target_calories=2000,
            consumed_calories=1300,
            target_protein_g=150,
            consumed_protein_g=80,
            limit=5,
        )

        rows = {row["name"]: row for row in out["best_next_meals_nearby"]}
        self.assertTrue(rows["Meal Fit Kitchen"]["fit_for_today"])
        self.assertFalse(rows["Heavy Combo Spot"]["fit_for_today"])


class DailyFatLossCoachContextTests(unittest.TestCase):
    def test_context_never_goes_negative(self):
        ctx = build_daily_context(
            target_calories=1800,
            consumed_calories=2200,
            target_protein_g=130,
            consumed_protein_g=160,
        )
        self.assertEqual(ctx["remaining_calories"], 0.0)
        self.assertEqual(ctx["remaining_protein_g"], 0.0)


if __name__ == "__main__":
    unittest.main()

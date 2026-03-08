import unittest

from daily_food_decision import build_daily_decision_response


class DailyFoodDecisionTests(unittest.TestCase):
    def _sample_places(self):
        return [
            {
                "name": "Subway",
                "place_id": "subway-1",
                "lat": -33.8048,
                "lng": 150.9659,
                "types": ["restaurant", "sandwich_shop"],
                "menu_items": [
                    {
                        "item_name": "6\" Chicken Breast Sub, extra salad, no mayo",
                        "estimated_calories": 430,
                        "estimated_protein_g": 38,
                    }
                ],
            },
            {
                "name": "Nando's",
                "place_id": "nandos-1",
                "lat": -33.8089,
                "lng": 150.9693,
                "types": ["restaurant", "grill"],
                "menu_items": [
                    {
                        "item_name": "Quarter chicken + salad",
                        "estimated_calories": 540,
                        "estimated_protein_g": 44,
                    }
                ],
            },
            {
                "name": "Pizza Place",
                "place_id": "pizza-1",
                "lat": -33.8121,
                "lng": 150.9734,
                "types": ["restaurant", "pizza"],
                "menu_items": [
                    {
                        "item_name": "Large pizza combo",
                        "estimated_calories": 1040,
                        "estimated_protein_g": 30,
                    }
                ],
            },
        ]

    def test_lunch_context_returns_lunch_window(self):
        out = build_daily_decision_response(
            nearby_places=self._sample_places(),
            origin_lat=-33.8070,
            origin_lng=150.9670,
            current_hour=12,
            remaining_calories=1300,
            remaining_protein_g=18,
            goal="fat_loss",
            cut_mode=True,
        )
        self.assertEqual(out.get("meal_window"), "lunch")
        self.assertIsInstance(out.get("primary_recommendation"), dict)
        self.assertIn("lunch", str(out["primary_recommendation"].get("headline") or "").lower())

    def test_dinner_context_returns_dinner_headline(self):
        out = build_daily_decision_response(
            nearby_places=self._sample_places(),
            origin_lat=-33.8070,
            origin_lng=150.9670,
            current_hour=19,
            remaining_calories=800,
            remaining_protein_g=16,
            goal="fat_loss",
            cut_mode=True,
        )
        self.assertEqual(out.get("meal_window"), "dinner")
        self.assertIn("dinner", str(out["primary_recommendation"].get("headline") or "").lower())

    def test_breakfast_context_returns_breakfast_headline(self):
        out = build_daily_decision_response(
            nearby_places=self._sample_places(),
            origin_lat=-33.8070,
            origin_lng=150.9670,
            current_hour=8,
            remaining_calories=1500,
            remaining_protein_g=18,
            goal="fat_loss",
            cut_mode=True,
        )
        self.assertEqual(out.get("meal_window"), "breakfast")
        self.assertIn("breakfast", str(out["primary_recommendation"].get("headline") or "").lower())

    def test_snack_context_sets_next_best_snack(self):
        out = build_daily_decision_response(
            nearby_places=self._sample_places(),
            origin_lat=-33.8070,
            origin_lng=150.9670,
            current_hour=16,
            remaining_calories=900,
            remaining_protein_g=18,
            goal="fat_loss",
            cut_mode=True,
        )
        self.assertEqual(out.get("meal_window"), "snack")
        self.assertIsInstance(out.get("next_best_snack"), dict)
        self.assertIn("snack", str((out.get("next_best_snack") or {}).get("headline") or "").lower())

    def test_low_calorie_context_includes_lighter_recovery(self):
        out = build_daily_decision_response(
            nearby_places=self._sample_places(),
            origin_lat=-33.8070,
            origin_lng=150.9670,
            current_hour=18,
            remaining_calories=320,
            remaining_protein_g=40,
            goal="fat_loss",
            cut_mode=True,
        )
        self.assertIsInstance(out.get("lighter_recovery_option"), dict)
        self.assertIn("lighter", str(out["lighter_recovery_option"].get("headline") or "").lower())

    def test_low_protein_context_includes_protein_catchup(self):
        out = build_daily_decision_response(
            nearby_places=self._sample_places(),
            origin_lat=-33.8070,
            origin_lng=150.9670,
            current_hour=16,
            remaining_calories=1100,
            remaining_protein_g=85,
            goal="fat_loss",
            cut_mode=True,
        )
        self.assertIsInstance(out.get("protein_catchup_option"), dict)
        protein = int(float((out.get("protein_catchup_option") or {}).get("estimated_protein_g") or 0))
        self.assertGreaterEqual(protein, 35)

    def test_sparse_fallback_is_safe(self):
        out = build_daily_decision_response(
            nearby_places=[],
            origin_lat=-33.8070,
            origin_lng=150.9670,
            current_hour=9,
            remaining_calories=None,
            remaining_protein_g=None,
        )
        self.assertIn("meal_window", out)
        self.assertIn("primary_recommendation", out)
        self.assertTrue(str((out.get("primary_recommendation") or {}).get("recommended_order") or "").strip())


if __name__ == "__main__":
    unittest.main()

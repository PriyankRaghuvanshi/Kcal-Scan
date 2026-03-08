import unittest

from restaurant_reality_check import (
    build_restaurant_reality_check,
    build_reality_check_share_card,
)


class RestaurantRealityCheckTests(unittest.TestCase):
    def test_fast_food_place_with_known_recommendation(self):
        place = {
            "name": "McDonald's",
            "place_id": "mc-1",
            "types": ["restaurant", "fast_food", "burger"],
        }

        out = build_restaurant_reality_check(
            place,
            recommended_order={
                "best_order": "Grilled wrap + water",
                "estimated_calories": 560,
                "estimated_protein_g": 38,
                "order_confidence": 0.82,
            },
        )

        self.assertEqual(out["title"], "Restaurant Reality Check")
        self.assertEqual(out["place_name"], "McDonald's")
        self.assertGreaterEqual(int(out["calories_saved"]), 300)
        self.assertEqual(out["smarter_order"]["name"], "Grilled wrap + water")
        self.assertIn(out.get("copy_method"), {"deterministic", "llm"})
        self.assertGreaterEqual(float(out.get("copy_confidence", 0.0)), 0.0)
        self.assertIsInstance(out.get("share_card"), dict)

    def test_fried_chicken_rule_fallback(self):
        place = {
            "name": "Crispy Chicken House",
            "types": ["restaurant", "fried_chicken", "fast_food"],
        }

        out = build_restaurant_reality_check(place)
        self.assertIn("fried", out["typical_order"]["name"].lower())
        self.assertGreater(int(out["typical_order"]["estimated_calories"]), int(out["smarter_order"]["estimated_calories"]))

    def test_pizza_menu_items_choose_heavier_typical(self):
        place = {
            "name": "Pizza Place",
            "types": ["restaurant", "pizza"],
            "menu_items": [
                {"item_name": "2 thin crust slices", "estimated_calories": 620, "estimated_protein_g": 28},
                {"item_name": "Large stuffed crust combo", "estimated_calories": 1120, "estimated_protein_g": 34},
                {"item_name": "Chicken salad side", "estimated_calories": 320, "estimated_protein_g": 20},
            ],
        }

        out = build_restaurant_reality_check(
            place,
            recommended_order={
                "item_name": "2 thin crust slices",
                "estimated_calories": 620,
                "estimated_protein_g": 28,
            },
        )

        self.assertIn("large", out["typical_order"]["name"].lower())
        self.assertGreaterEqual(int(out["calories_saved"]), 300)

    def test_healthy_grill_still_generates_savings(self):
        place = {
            "name": "Nando's",
            "types": ["restaurant", "grill", "healthy"],
        }

        out = build_restaurant_reality_check(
            place,
            recommended_order={
                "best_order": "Quarter chicken + salad",
                "estimated_calories": 540,
                "estimated_protein_g": 44,
            },
        )

        self.assertIn("chicken", out["smarter_order"]["name"].lower())
        self.assertGreaterEqual(int(out["calories_saved"]), 200)
        self.assertGreaterEqual(int(out["protein_difference_g"]), 0)

    def test_sparse_generic_venue_fallback(self):
        place = {
            "name": "Local Eatery",
            "types": ["restaurant"],
        }
        out = build_restaurant_reality_check(place)

        self.assertIn("typical_order", out)
        self.assertIn("smarter_order", out)
        self.assertNotIn("grilled protein bowl", str(out["smarter_order"].get("name") or "").lower())
        self.assertIsInstance(out["confidence"], float)
        self.assertGreaterEqual(float(out["confidence"]), 0.35)
        self.assertLessEqual(float(out["confidence"]), 0.94)

    def test_uses_top_menu_item_when_no_explicit_recommendation(self):
        place = {"name": "Bowl Spot", "types": ["restaurant", "bowl", "healthy"]}
        out = build_restaurant_reality_check(
            place,
            recommended_order=None,
            context={
                "top_menu_item": {
                    "item_name": "Chicken pesto bowl",
                    "estimated_calories": 520,
                    "estimated_protein_g": 42,
                    "confidence": 0.8,
                }
            },
        )

        self.assertEqual(out["smarter_order"]["name"], "Chicken pesto bowl")
        self.assertGreaterEqual(int(out["calories_saved"]), 100)

    def test_share_card_generation(self):
        share = build_reality_check_share_card(
            place_name="Nando's",
            typical_calories=900,
            smarter_calories=540,
            calories_saved=360,
            smarter_order="Quarter chicken + salad",
            protein_difference_g=12,
        )

        required = {
            "title",
            "place_name",
            "typical_calories",
            "smarter_calories",
            "calories_saved",
            "smarter_order",
            "subtitle",
            "badges",
            "share_card_version",
        }
        self.assertTrue(required.issubset(share.keys()))
        self.assertEqual(share["title"], "Restaurant Reality Check")
        self.assertIn("360", share["subtitle"])


if __name__ == "__main__":
    unittest.main()

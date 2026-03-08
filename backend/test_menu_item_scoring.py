import unittest

from menu_item_scoring import recommend_menu_items_for_place, rank_menu_items_for_place
from nutrition_mode import NutritionMode


class MenuItemScoringTests(unittest.TestCase):
    def test_healthier_menu_item_ranks_above_worse_item(self):
        place = {"name": "Metro Grill House", "types": ["restaurant", "meal_takeaway"]}
        menu_items = [
            {
                "item_name": "Fried chicken loaded combo",
                "estimated_calories": 980,
                "estimated_protein_g": 20,
                "estimated_satiety": "low",
            },
            {
                "item_name": "Grilled chicken bowl",
                "estimated_calories": 520,
                "estimated_protein_g": 42,
                "estimated_satiety": "high",
            },
            {
                "item_name": "Chicken wrap",
                "estimated_calories": 600,
                "estimated_protein_g": 31,
                "estimated_satiety": "medium",
            },
        ]

        ranked = rank_menu_items_for_place(place, menu_items)
        self.assertGreaterEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["item_name"], "Grilled chicken bowl")
        self.assertGreater(ranked[0]["item_score"], ranked[1]["item_score"])

    def test_missing_menu_data_uses_safe_fallback(self):
        place = {
            "name": "Downtown Sushi Point",
            "types": ["restaurant", "meal_takeaway"],
            "vicinity": "Main street",
        }

        out = recommend_menu_items_for_place(place)

        self.assertTrue(out["menu_item_scoring_available"])
        self.assertEqual(out["menu_items_source"], "heuristic")
        self.assertEqual(len(out["top_menu_items"]), 3)
        self.assertIsInstance(out["top_menu_item"], dict)

    def test_response_fields_are_card_ready(self):
        place = {
            "name": "Protein Cafe",
            "types": ["restaurant", "cafe"],
            "menu_items": [
                {
                    "name": "Egg and chicken plate",
                    "calories": 430,
                    "protein_g": 30,
                }
            ],
        }

        out = recommend_menu_items_for_place(place, health_score=7.8)
        top = out["top_menu_item"]

        required_fields = {
            "item_name",
            "item_score",
            "item_score_breakdown",
            "estimated_calories",
            "estimated_protein_g",
            "estimated_carbs_g",
            "estimated_fat_g",
            "estimated_satiety",
            "macro_confidence",
            "macro_estimation_version",
            "fat_loss_friendly",
            "short_reason",
            "confidence",
            "recommendation_tags",
            "recommendation_version",
        }

        self.assertTrue(required_fields.issubset(top.keys()))
        self.assertIn(top["estimated_satiety"], {"high", "medium", "low"})
        self.assertGreaterEqual(float(top["confidence"]), 0.0)
        self.assertLessEqual(float(top["confidence"]), 1.0)
        self.assertLessEqual(len(str(top["short_reason"])), 90)

    def test_rankings_differ_under_cut_mode(self):
        place = {"name": "Urban Fast Food Hub", "types": ["restaurant", "fast_food"]}
        menu_items = [
            {
                "item_name": "Mega protein combo",
                "estimated_calories": 760,
                "estimated_protein_g": 65,
                "estimated_satiety": "high",
            },
            {
                "item_name": "Light chicken salad",
                "estimated_calories": 430,
                "estimated_protein_g": 24,
                "estimated_satiety": "medium",
            },
            {
                "item_name": "Chicken wrap",
                "estimated_calories": 560,
                "estimated_protein_g": 34,
                "estimated_satiety": "medium",
            },
        ]

        default_ranked = rank_menu_items_for_place(place, menu_items, mode=NutritionMode.DEFAULT)
        cut_ranked = rank_menu_items_for_place(place, menu_items, mode=NutritionMode.CUT)

        self.assertGreaterEqual(len(default_ranked), 1)
        self.assertGreaterEqual(len(cut_ranked), 1)
        self.assertNotEqual(
            [item["item_name"] for item in default_ranked],
            [item["item_name"] for item in cut_ranked],
        )
        self.assertTrue(cut_ranked[0].get("cut_mode_active"))

    def test_cut_mode_exposes_cut_flags(self):
        place = {
            "name": "Lean Grill Point",
            "types": ["restaurant", "meal_takeaway"],
            "menu_items": [
                {
                    "name": "Grilled chicken bowl",
                    "calories": 520,
                    "protein_g": 42,
                }
            ],
        }

        out = recommend_menu_items_for_place(place, mode=NutritionMode.CUT)
        top = out["top_menu_item"]

        self.assertTrue(out.get("cut_mode_active"))
        self.assertTrue(top.get("cut_mode_active"))
        self.assertIn("cut_friendly", top)
        self.assertIn("cut_warning", top)


if __name__ == "__main__":
    unittest.main()

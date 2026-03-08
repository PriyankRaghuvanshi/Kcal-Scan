import unittest

from healthy_order_recommender import suggest_best_order_for_place
from nutrition_mode import NutritionMode


class HealthyOrderRecommenderTests(unittest.TestCase):
    def test_healthy_grill_place_gets_high_protein_reco(self):
        place = {
            "name": "Protein Grill Bowl House",
            "types": ["restaurant", "meal_takeaway"],
            "vicinity": "Main Road",
        }
        out = suggest_best_order_for_place(place, health_score=8.1)

        self.assertIn("Grilled", out["best_order"])
        self.assertGreaterEqual(float(out["estimated_protein_g"]), 30)
        self.assertIn("high_protein", out["order_strategy_tags"])
        self.assertGreaterEqual(float(out["order_confidence"]), 0.75)

    def test_fast_food_place_gets_swap_guidance(self):
        place = {
            "name": "Burger Fast Food Corner",
            "types": ["restaurant", "fast_food"],
            "vicinity": "Downtown",
        }
        out = suggest_best_order_for_place(place, health_score=4.2)

        self.assertTrue("skip fries" in out["better_swap"].lower() or "water" in out["better_swap"].lower())
        self.assertIn("combo", out["avoid_if_cutting"].lower())
        self.assertLessEqual(float(out["order_confidence"]), 0.8)
        self.assertEqual(out.get("order_type"), "likely")
        self.assertTrue(str(out.get("swap_suggestion") or "").strip())
        self.assertIsInstance(out.get("skip_items"), list)
        self.assertIsInstance(out.get("add_items"), list)

    def test_ambiguous_place_fallback_does_not_fail(self):
        out = suggest_best_order_for_place({})

        required_fields = {
            "best_order",
            "better_swap",
            "avoid_if_cutting",
            "estimated_calories",
            "estimated_protein_g",
            "estimated_carbs_g",
            "estimated_fat_g",
            "estimated_satiety",
            "macro_confidence",
            "macro_estimation_version",
            "order_confidence",
            "short_reason",
            "why_this_works",
            "order_strategy_tags",
            "recommendation_version",
            "copy_method",
            "copy_confidence",
            "copy_version",
        }
        self.assertTrue(required_fields.issubset(out.keys()))
        self.assertIn(out["estimated_satiety"], {"high", "medium", "low"})
        self.assertGreaterEqual(float(out["order_confidence"]), 0.0)
        self.assertLessEqual(float(out["order_confidence"]), 1.0)
        self.assertEqual(out.get("order_type"), "estimated")
        self.assertTrue(str(out.get("swap_suggestion") or "").strip())
        self.assertIsInstance(out.get("skip_items"), list)
        self.assertIsInstance(out.get("add_items"), list)

    def test_cut_mode_adds_cut_specific_wording_and_flags(self):
        place = {
            "name": "Burger Fast Food Corner",
            "types": ["restaurant", "fast_food"],
            "vicinity": "Downtown",
        }

        default_out = suggest_best_order_for_place(place, health_score=4.2, mode=NutritionMode.DEFAULT)
        cut_out = suggest_best_order_for_place(place, health_score=4.2, mode=NutritionMode.CUT)

        self.assertFalse(default_out.get("cut_mode_active"))
        self.assertTrue(cut_out.get("cut_mode_active"))
        self.assertIn("best_order_for_cut", cut_out)
        self.assertIn("cut_friendly", cut_out)
        self.assertIn("cut_warning", cut_out)
        self.assertIn("cut_mode", cut_out.get("order_strategy_tags", []))
        self.assertNotEqual(default_out.get("short_reason"), cut_out.get("short_reason"))

    def test_temple_context_avoids_generic_grilled_bowl_fallback(self):
        place = {
            "name": "Sri Temple Canteen",
            "types": ["restaurant", "canteen"],
            "vicinity": "South Indian temple street",
        }
        out = suggest_best_order_for_place(place, health_score=5.0)
        self.assertNotIn("grilled protein bowl", str(out.get("best_order") or "").lower())
        self.assertTrue(str(out.get("best_order") or "").strip())


if __name__ == "__main__":
    unittest.main()

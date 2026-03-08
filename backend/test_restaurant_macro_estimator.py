import unittest
from unittest.mock import patch

from restaurant_macro_estimator import estimate_restaurant_macros


class RestaurantMacroEstimatorTests(unittest.TestCase):
    def test_grilled_chicken_bowl_estimate(self):
        out = estimate_restaurant_macros(
            item_name="Grilled chicken bowl",
            cuisine_hint="healthy bowl",
            place={"name": "Protein Grill", "types": ["restaurant", "meal_takeaway"]},
        )

        self.assertGreaterEqual(out["estimated_protein_g"], 30)
        self.assertLessEqual(out["estimated_calories"], 700)
        self.assertIn(out["estimated_satiety"], {"high", "medium", "low"})
        self.assertGreaterEqual(float(out["macro_confidence"]), 0.35)

    def test_burger_meal_estimate(self):
        out = estimate_restaurant_macros(
            item_name="Double burger meal",
            cuisine_hint="fast food",
            place={"name": "Burger Stop", "types": ["restaurant", "fast_food"]},
        )

        self.assertGreaterEqual(out["estimated_calories"], 650)
        self.assertGreaterEqual(out["estimated_fat_g"], 20)
        self.assertGreaterEqual(out["estimated_carbs_g"], 30)
        self.assertIn(out["estimated_satiety"], {"low", "medium", "high"})

    def test_sushi_bowl_estimate(self):
        out = estimate_restaurant_macros(
            item_name="Salmon sushi bowl",
            cuisine_hint="japanese sushi",
            place={"name": "Sushi Hub", "types": ["restaurant"]},
        )

        self.assertGreaterEqual(out["estimated_protein_g"], 22)
        self.assertGreaterEqual(out["estimated_carbs_g"], 20)
        self.assertLessEqual(out["estimated_fat_g"], 35)

    def test_curry_rice_estimate(self):
        out = estimate_restaurant_macros(
            item_name="Chicken curry + rice",
            cuisine_hint="indian curry",
            place={"name": "Curry House", "types": ["restaurant"]},
        )

        self.assertGreaterEqual(out["estimated_calories"], 550)
        self.assertGreaterEqual(out["estimated_carbs_g"], 40)
        self.assertGreaterEqual(out["estimated_fat_g"], 12)

    def test_output_fields_stable(self):
        out = estimate_restaurant_macros(item_name="Menu item")
        required = {
            "estimated_calories",
            "estimated_protein_g",
            "estimated_carbs_g",
            "estimated_fat_g",
            "estimated_satiety",
            "macro_confidence",
            "macro_estimation_version",
            "estimation_method",
            "estimation_version",
        }
        self.assertTrue(required.issubset(out.keys()))

    def test_known_meal_keeps_deterministic_method(self):
        out = estimate_restaurant_macros(
            item_name="Grilled chicken bowl",
            cuisine_hint="healthy bowl",
        )
        self.assertEqual(out.get("estimation_method"), "deterministic")

    def test_unknown_meal_can_use_llm_path(self):
        fake_llm = {
            "attempted": True,
            "used": True,
            "error": "",
            "estimate": {
                "estimated_calories": 610,
                "estimated_protein_g": 37,
                "estimated_carbs_g": 54,
                "estimated_fat_g": 19,
                "estimated_satiety": "medium",
                "macro_confidence": 0.77,
            },
        }
        with patch("restaurant_macro_estimator.maybe_estimate_unknown_meal_macros", return_value=fake_llm):
            out = estimate_restaurant_macros(item_name="Volcano dragon crunch stack")
        self.assertEqual(out.get("estimation_method"), "llm")
        self.assertEqual(out.get("estimation_version"), "v1")
        self.assertGreaterEqual(float(out.get("macro_confidence") or 0.0), 0.35)

    def test_llm_failure_falls_back_to_deterministic(self):
        fake_llm = {
            "attempted": True,
            "used": False,
            "error": "timeout",
            "estimate": None,
        }
        with patch("restaurant_macro_estimator.maybe_estimate_unknown_meal_macros", return_value=fake_llm):
            out = estimate_restaurant_macros(item_name="Volcano dragon crunch stack")
        self.assertEqual(out.get("estimation_method"), "deterministic")
        self.assertIn("timeout", str(out.get("llm_fallback_reason") or ""))


if __name__ == "__main__":
    unittest.main()

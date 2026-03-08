import unittest

from healthy_place_scoring import HEALTHY_PLACE_SCORE_WEIGHTS, score_healthy_place
from nutrition_mode import NutritionMode


class HealthyPlaceScoringTests(unittest.TestCase):
    def test_component_breakdown_present(self):
        scored = score_healthy_place(
            {
                "name": "Protein Grill House",
                "types": ["restaurant", "meal_takeaway"],
                "vicinity": "Downtown",
            }
        )
        self.assertIn("score_breakdown", scored)
        breakdown = scored["score_breakdown"]
        for component in HEALTHY_PLACE_SCORE_WEIGHTS.keys():
            self.assertIn(component, breakdown)
            self.assertIn("score", breakdown[component])
            self.assertIn("weight", breakdown[component])

    def test_positive_venue_outscores_negative_venue(self):
        positive = score_healthy_place(
            {
                "name": "Healthy Protein Grill",
                "types": ["restaurant", "meal_takeaway"],
                "vicinity": "City Center",
            }
        )
        negative = score_healthy_place(
            {
                "name": "Fried Burger Donut Point",
                "types": ["restaurant", "fast_food"],
                "vicinity": "Main Road",
            }
        )
        self.assertGreater(float(positive["health_score"]), float(negative["health_score"]))

    def test_missing_metadata_uses_neutral_fallback(self):
        scored = score_healthy_place({})
        self.assertAlmostEqual(float(scored["health_score"]), 5.0, places=1)
        self.assertIn("Needs menu check", scored.get("recommended_badges", []))

    def test_cut_mode_adds_cut_fields_and_changes_score(self):
        place = {
            "name": "Healthy Salad Vegan Grill",
            "types": ["restaurant", "meal_takeaway"],
            "vicinity": "City Center",
        }

        default_scored = score_healthy_place(place, mode=NutritionMode.DEFAULT)
        cut_scored = score_healthy_place(place, mode=NutritionMode.CUT)

        self.assertFalse(default_scored.get("cut_mode_active"))
        self.assertTrue(cut_scored.get("cut_mode_active"))
        self.assertIn("cut_friendly", cut_scored)
        self.assertIn("cut_warning", cut_scored)
        self.assertNotEqual(float(default_scored["health_score"]), float(cut_scored["health_score"]))


if __name__ == "__main__":
    unittest.main()

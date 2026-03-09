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
        self.assertIn("base_score", scored)
        self.assertIn("modifier_score", scored)
        self.assertIn("final_score", scored)
        self.assertIn("modifier_breakdown", scored)

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
        self.assertIn("Needs Menu Check", scored.get("recommended_badges", []))

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

    def test_subway_like_menu_ranks_above_heavier_venue(self):
        subway_menu = {
            "menu_source": "real_menu",
            "menu_confidence": 0.88,
            "top_menu_items": [
                {"item_name": "Turkey salad sub", "item_score": 86, "estimated_calories": 430, "estimated_protein_g": 34, "cut_friendly": True},
                {"item_name": "Chicken wrap", "item_score": 82, "estimated_calories": 510, "estimated_protein_g": 33, "cut_friendly": True},
                {"item_name": "Tuna protein bowl", "item_score": 79, "estimated_calories": 560, "estimated_protein_g": 36, "fat_loss_friendly": True},
                {"item_name": "Veggie + chicken sub", "item_score": 78, "estimated_calories": 540, "estimated_protein_g": 31},
            ],
        }
        heavy_menu = {
            "menu_source": "real_menu",
            "menu_confidence": 0.86,
            "top_menu_items": [
                {"item_name": "Loaded fried combo", "item_score": 41, "estimated_calories": 980, "estimated_protein_g": 22},
                {"item_name": "Double cheesy burger", "item_score": 44, "estimated_calories": 920, "estimated_protein_g": 27},
                {"item_name": "Large shake combo", "item_score": 35, "estimated_calories": 1100, "estimated_protein_g": 18},
            ],
        }
        subway = score_healthy_place(
            {"name": "Subway", "types": ["restaurant", "sandwich_shop"]},
            mode=NutritionMode.CUT,
            menu_payload=subway_menu,
        )
        heavy = score_healthy_place(
            {"name": "Burger House", "types": ["restaurant", "fast_food"]},
            mode=NutritionMode.CUT,
            menu_payload=heavy_menu,
        )
        self.assertGreater(float(subway["health_score"]), float(heavy["health_score"]))
        self.assertTrue(bool(subway.get("nutrition_data_available")))
        self.assertGreaterEqual(int(subway.get("healthy_item_count", 0)), 2)
        self.assertGreater(float(subway.get("menu_fit_ratio", 0.0)), float(heavy.get("menu_fit_ratio", 0.0)))

    def test_real_menu_source_scores_above_heuristic_for_same_items(self):
        shared_items = [
            {"item_name": "Chicken breast sub", "item_score": 84, "rank_adjusted_item_score": 84, "estimated_calories": 430, "estimated_protein_g": 36, "cut_friendly": True, "source_rank_weight": 1.0},
            {"item_name": "Turkey salad sub", "item_score": 80, "rank_adjusted_item_score": 80, "estimated_calories": 460, "estimated_protein_g": 33, "fat_loss_friendly": True, "source_rank_weight": 1.0},
            {"item_name": "Veggie + chicken wrap", "item_score": 76, "rank_adjusted_item_score": 76, "estimated_calories": 510, "estimated_protein_g": 30, "source_rank_weight": 1.0},
        ]
        real_menu = score_healthy_place(
            {"name": "Nearby Subway", "types": ["restaurant", "sandwich_shop"]},
            mode=NutritionMode.CUT,
            menu_payload={"menu_source": "real_menu", "menu_confidence": 0.9, "top_menu_items": shared_items},
        )
        heuristic_menu = score_healthy_place(
            {"name": "Nearby Subway", "types": ["restaurant", "sandwich_shop"]},
            mode=NutritionMode.CUT,
            menu_payload={"menu_source": "heuristic", "menu_confidence": 0.55, "top_menu_items": shared_items},
        )
        self.assertGreater(float(real_menu["menu_dominance"]), float(heuristic_menu["menu_dominance"]))
        self.assertGreater(float(real_menu["health_score"]), float(heuristic_menu["health_score"]))

    def test_user_scan_source_scores_between_real_and_llm_inferred(self):
        shared_items = [
            {"item_name": "Chicken sub", "item_score": 82, "rank_adjusted_item_score": 82, "estimated_calories": 440, "estimated_protein_g": 34, "source_rank_weight": 0.95},
            {"item_name": "Turkey sub", "item_score": 79, "rank_adjusted_item_score": 79, "estimated_calories": 470, "estimated_protein_g": 32, "source_rank_weight": 0.95},
            {"item_name": "Veg + chicken", "item_score": 75, "rank_adjusted_item_score": 75, "estimated_calories": 500, "estimated_protein_g": 30, "source_rank_weight": 0.95},
        ]
        real_menu = score_healthy_place(
            {"name": "Subway", "types": ["restaurant", "sandwich_shop"]},
            mode=NutritionMode.CUT,
            menu_payload={"menu_source": "real_menu", "menu_confidence": 0.9, "top_menu_items": shared_items},
        )
        user_scan = score_healthy_place(
            {"name": "Subway", "types": ["restaurant", "sandwich_shop"]},
            mode=NutritionMode.CUT,
            menu_payload={"menu_source": "user_scan", "menu_confidence": 0.85, "top_menu_items": shared_items},
        )
        llm_inferred = score_healthy_place(
            {"name": "Subway", "types": ["restaurant", "sandwich_shop"]},
            mode=NutritionMode.CUT,
            menu_payload={"menu_source": "llm_inferred", "menu_confidence": 0.7, "top_menu_items": shared_items},
        )
        self.assertGreaterEqual(float(real_menu["health_score"]), float(user_scan["health_score"]))
        self.assertGreater(float(user_scan["health_score"]), float(llm_inferred["health_score"]))

    def test_indian_heavy_menu_ranks_lower_than_tandoori_lean_menu(self):
        heavy_indian = {
            "menu_source": "real_menu",
            "menu_confidence": 0.82,
            "top_menu_items": [
                {"item_name": "Butter chicken + naan", "item_score": 46, "estimated_calories": 980, "estimated_protein_g": 30},
                {"item_name": "Creamy paneer curry", "item_score": 43, "estimated_calories": 920, "estimated_protein_g": 24},
                {"item_name": "Fried pakora platter", "item_score": 34, "estimated_calories": 860, "estimated_protein_g": 14},
            ],
        }
        lean_indian = {
            "menu_source": "real_menu",
            "menu_confidence": 0.86,
            "top_menu_items": [
                {"item_name": "Tandoori chicken", "item_score": 82, "estimated_calories": 520, "estimated_protein_g": 45, "cut_friendly": True},
                {"item_name": "Dal + grilled paneer", "item_score": 76, "estimated_calories": 590, "estimated_protein_g": 34, "fat_loss_friendly": True},
                {"item_name": "Chicken tikka salad", "item_score": 84, "estimated_calories": 500, "estimated_protein_g": 42, "cut_friendly": True},
            ],
        }
        heavy = score_healthy_place(
            {"name": "Rich Curry Point", "types": ["restaurant", "indian"]},
            mode=NutritionMode.CUT,
            menu_payload=heavy_indian,
        )
        lean = score_healthy_place(
            {"name": "Tandoori Grill", "types": ["restaurant", "indian"]},
            mode=NutritionMode.CUT,
            menu_payload=lean_indian,
        )
        self.assertGreater(float(lean["health_score"]), float(heavy["health_score"]))

    def test_dessert_venue_ranks_low_with_heavy_menu_distribution(self):
        dessert_menu = {
            "menu_source": "real_menu",
            "menu_confidence": 0.9,
            "top_menu_items": [
                {"item_name": "Chocolate lava cake", "item_score": 24, "estimated_calories": 760, "estimated_protein_g": 8},
                {"item_name": "Loaded waffle", "item_score": 28, "estimated_calories": 840, "estimated_protein_g": 10},
                {"item_name": "Ice cream sundae", "item_score": 22, "estimated_calories": 690, "estimated_protein_g": 7},
            ],
        }
        dessert = score_healthy_place(
            {"name": "Sweet Factory", "types": ["restaurant", "dessert_shop"]},
            mode=NutritionMode.CUT,
            menu_payload=dessert_menu,
        )
        self.assertLessEqual(float(dessert["health_score"]), 5.0)

    def test_sparse_data_fallback_still_returns_safe_score(self):
        scored = score_healthy_place(
            {"name": "Unknown Spot", "types": ["restaurant"]},
            menu_payload={"menu_source": "heuristic", "top_menu_items": []},
        )
        self.assertGreaterEqual(float(scored["health_score"]), 1.0)
        self.assertLessEqual(float(scored["health_score"]), 10.0)
        self.assertIn("recommended_badges", scored)

    def test_modifier_layer_is_conservative_for_place_scoring(self):
        scored = score_healthy_place(
            {"name": "Near Subway", "types": ["restaurant", "sandwich_shop"]},
            mode=NutritionMode.CUT,
            menu_payload={
                "menu_source": "real_menu",
                "menu_confidence": 0.9,
                "top_menu_items": [
                    {
                        "item_name": "6\" Chicken Breast Sub",
                        "item_score": 86,
                        "rank_adjusted_item_score": 86,
                        "estimated_calories": 430,
                        "estimated_protein_g": 38,
                        "cut_friendly": True,
                        "menu_item_source": "real_menu",
                        "menu_item_confidence": 0.92,
                        "order_type": "exact",
                    }
                ],
            },
        )
        self.assertLessEqual(abs(float(scored.get("modifier_score", 0.0))), 3.5)
        self.assertLessEqual(
            abs(float(scored.get("final_score", 0.0)) - float(scored.get("base_score", 0.0))),
            3.5,
        )


if __name__ == "__main__":
    unittest.main()

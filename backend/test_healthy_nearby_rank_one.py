import unittest
from unittest.mock import patch

from healthy_nearby_rank_one import HealthyNearbyRankContext, rank_one_healthy_nearby_place
from nutrition_mode import NutritionMode


class HealthyNearbyRankOneTests(unittest.TestCase):
    @patch("healthy_nearby_rank_one.suggest_best_order_for_place")
    @patch("healthy_nearby_rank_one.recommend_menu_items_for_place")
    def test_ranker_uses_recommendation_pipeline_even_when_old_cache_exists(self, mock_recommend, mock_suggest):
        mock_recommend.return_value = {
            "menu_item_scoring_available": True,
            "menu_items_source": "chain_menu_supabase",
            "menu_source": "chain_menu_supabase",
            "menu_confidence": 0.82,
            "top_menu_items": [],
            "best_menu_items": [],
            "top_menu_item": {
                "item_name": "Fresh supabase bowl",
                "menu_item_source": "ingested_chain_item",
                "menu_item_confidence": 0.82,
                "estimated_calories": 540,
                "estimated_protein_g": 40,
            },
            "top_item": "Fresh supabase bowl",
        }
        mock_suggest.return_value = {
            "best_order": "Fresh supabase bowl",
            "estimated_calories": 540,
            "estimated_protein_g": 40,
        }
        place = {
            "place_id": "chipotle_1",
            "name": "Chipotle Mexican Grill",
            "types": ["restaurant", "food"],
            "lat": 37.77,
            "lng": -122.41,
        }
        ctx = HealthyNearbyRankContext(
            lat=37.77,
            lng=-122.41,
            cut_mode=False,
            goal="",
            nutrition_mode=NutritionMode.DEFAULT,
            personalization_goal=None,
            personalization_goal_value_str="default",
            diet_preference_val="omnivore",
            remaining_calories=None,
            remaining_protein_g=None,
            post_workout=False,
            late_night=False,
            poor_sleep_flag=False,
            high_craving_risk_flag=False,
            context_mode="",
            local_hour=12,
            user_id="",
        )

        out = rank_one_healthy_nearby_place(place, ctx)

        mock_recommend.assert_called_once()
        self.assertEqual(out.get("best_order"), "Fresh supabase bowl")

    @patch("healthy_nearby_rank_one.suggest_best_order_for_place")
    @patch("healthy_nearby_rank_one.venue_cache_get")
    def test_cache_hit_preserves_covered_chain_provenance(self, mock_cache_get, mock_suggest):
        # Covered-chain cache hit for Subway. This exercises cache_to_menu_payload AND
        # the ranking_fields merge. Guards against the bug where the payload dropped
        # item_provenance / covered_chain_key before reaching the response.
        mock_cache_get.return_value = {
            "place_id": "subway_1",
            "candidates": [
                {
                    "item_name": "6-inch Turkey Breast on Wheat",
                    "estimated_calories": 280,
                    "estimated_protein_g": 18,
                    "menu_item_source": "ingested_chain_item",
                    "menu_item_confidence": 0.82,
                }
            ],
            "specificity_tier": "chain_registry",
            "confidence": 0.9,
            "source_type": "chain_menu_supabase",
            "chain_key": "subway",
            "chain_match": True,
            "last_enriched_at": 9_999_999_999.0,
            "ttl_sec": 86_400 * 7,
            "swap_templates": [],
            "item_provenance": "exact_chain_menu",
            "covered_chain_key": "subway",
            "covered_chain_neutral": False,
            "can_show_verified_badge": True,
            "covered_chain_display_name": "Subway",
            "covered_chain_menu_url": "https://www.subway.com/en-us/menunutrition/menu",
        }
        mock_suggest.return_value = {
            "best_order": "6-inch Turkey Breast on Wheat",
            "estimated_calories": 280,
            "estimated_protein_g": 18,
        }
        place = {
            "place_id": "subway_1",
            "name": "Subway",
            "types": ["restaurant", "meal_takeaway"],
            "lat": 37.77,
            "lng": -122.41,
        }
        ctx = HealthyNearbyRankContext(
            lat=37.77,
            lng=-122.41,
            cut_mode=False,
            goal="",
            nutrition_mode=NutritionMode.DEFAULT,
            personalization_goal=None,
            personalization_goal_value_str="default",
            diet_preference_val="omnivore",
            remaining_calories=None,
            remaining_protein_g=None,
            post_workout=False,
            late_night=False,
            poor_sleep_flag=False,
            high_craving_risk_flag=False,
            context_mode="",
            local_hour=12,
            user_id="",
        )

        out = rank_one_healthy_nearby_place(place, ctx)

        self.assertEqual(out.get("item_provenance"), "exact_chain_menu")
        self.assertEqual(out.get("covered_chain_key"), "subway")
        self.assertTrue(out.get("can_show_verified_badge"))
        self.assertFalse(out.get("covered_chain_neutral"))

    def test_covered_chains_return_real_menu_items_not_fallback(self):
        # End-to-end: for a panel of US covered chains, best_order must be the
        # real chain menu item (from the chain registry), not a generic heuristic
        # string like "Lighter menu option". This locks in the provenance-first
        # use_menu_order gate plus lat/lng country inference.
        # No mocks — exercises the real recommend_menu_items_for_place path.
        FALLBACK_STRINGS = {
            "Lighter menu option",
            "Protein bowl or soft tacos; skip loaded nachos/queso (typical pattern — no menu on file)",
            "Grilled or baked protein with vegetables or salad (typical pattern — no menu on file)",
            "Savory lighter plates over desserts/pastries (typical pattern — no menu on file)",
        }
        covered_chains = [
            ("Subway", "subway"),
            ("McDonald's", "mcdonalds"),
            ("KFC", "kfc"),
            ("Chipotle Mexican Grill", "chipotle"),
            ("Taco Bell", "taco_bell"),
            ("Wendy's", "wendys"),
            ("Burger King", "burger_king"),
            ("Panera Bread", "panera"),
            ("Chick-fil-A", "chick_fil_a"),
            ("Domino's Pizza", "dominos"),
            ("Cava", "cava"),
        ]
        ctx = HealthyNearbyRankContext(
            lat=37.77, lng=-122.41, cut_mode=False, goal="",
            nutrition_mode=NutritionMode.DEFAULT, personalization_goal=None,
            personalization_goal_value_str="default", diet_preference_val="omnivore",
            remaining_calories=None, remaining_protein_g=None,
            post_workout=False, late_night=False, poor_sleep_flag=False,
            high_craving_risk_flag=False, context_mode="", local_hour=12, user_id="",
        )
        for name, expected_chain_key in covered_chains:
            with self.subTest(name=name):
                place = {
                    "place_id": f"smoke_{expected_chain_key}",
                    "name": name,
                    "types": ["restaurant"],
                    "lat": 37.77,
                    "lng": -122.41,
                }
                out = rank_one_healthy_nearby_place(place, ctx)
                self.assertEqual(
                    out.get("covered_chain_key"),
                    expected_chain_key,
                    f"{name} should resolve to chain {expected_chain_key}",
                )
                self.assertEqual(
                    out.get("item_provenance"),
                    "exact_chain_menu",
                    f"{name} should have exact_chain_menu provenance",
                )
                best_order = str(out.get("best_order") or "")
                self.assertTrue(
                    best_order,
                    f"{name} must have a best_order",
                )
                self.assertNotIn(
                    best_order,
                    FALLBACK_STRINGS,
                    f"{name} best_order={best_order!r} is a heuristic fallback, not a chain menu item",
                )


if __name__ == "__main__":
    unittest.main()

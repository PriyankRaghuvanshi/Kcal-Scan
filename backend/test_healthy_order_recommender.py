import unittest
from unittest.mock import patch

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

    def test_indian_grill_context_prefers_indian_rule_over_generic_grill(self):
        place = {
            "name": "Royal Indian Grill",
            "types": ["restaurant", "indian", "grill"],
            "vicinity": "Wentworthville",
        }
        out = suggest_best_order_for_place(place, health_score=6.2)
        best_order = str(out.get("best_order") or "").lower()
        # Cuisine rules: Indian candidates include tandoori, tikka, dal, paneer, etc.
        self.assertTrue(
            "tandoori" in best_order or "dal" in best_order or "tikka" in best_order or "paneer" in best_order or "bhurji" in best_order,
            msg=f"Expected Indian-style candidate, got: {out.get('best_order')}",
        )

    def test_cafe_recommendation_does_not_leak_protein_plate_phrase(self):
        place = {
            "name": "Corner Cafe",
            "types": ["restaurant", "cafe", "bakery"],
            "vicinity": "Main Street",
        }
        out = suggest_best_order_for_place(place, health_score=5.5)
        self.assertNotIn("protein plate", str(out.get("best_order") or "").lower())

    def test_local_profile_match_by_place_id_returns_profile_recommendation(self):
        """Local venue profile exists for place_id; recommendation comes from profile, not heuristic."""
        place = {
            "name": "Test Darbar",
            "place_id": "ChIJ123",
            "types": ["restaurant", "indian"],
            "lat": -33.815,
            "lng": 151.0,
        }
        profile = {
            "place_id": "ChIJ123",
            "place_name": "Test Darbar",
            "area_key": "parramatta",
            "specificity_tier": "enriched_local_profile",
            "profile_source": "curated_manual",
            "confidence_tier": 0.85,
            "candidate_templates": [
                {
                    "template_key": "t1",
                    "template_name": "Tandoori chicken half + dal",
                    "estimated_calories": 520,
                    "estimated_protein_g": 42,
                    "confidence": 0.88,
                }
            ],
            "swap_templates": [
                {"swap_key": "no_naan", "swap_label": "No naan", "swap_type": "side_omit"}
            ],
        }
        with patch("healthy_order_recommender.get_local_venue_profile", return_value=profile):
            out = suggest_best_order_for_place(place, health_score=7.0)
        self.assertTrue(out.get("matched_local_profile"), "Should have matched_local_profile=True")
        self.assertEqual(out.get("menu_item_source"), "local_venue_profile")
        self.assertIn("Tandoori chicken", str(out.get("best_order") or ""))
        self.assertEqual(out.get("local_profile_source"), "curated_manual")
        self.assertIn("chosen_candidate_specificity_tier", out)

    def test_local_profile_fallback_by_normalized_name_and_area_key(self):
        """No place_id match; normalized_name + area_key match; profile still used."""
        place = {
            "name": "Darbar",
            "place_id": "",  # No place_id
            "types": ["restaurant", "indian"],
            "lat": -33.815,
            "lng": 151.0,
        }
        profile = {
            "place_id": "",
            "place_name": "Darbar",
            "normalized_name": "darbar",
            "name_variants": ["Darbar", "Darbar Indian"],
            "area_key": "parramatta",
            "specificity_tier": "exact_local_profile",
            "profile_source": "curated_manual",
            "candidate_templates": [
                {"template_key": "t1", "template_name": "Paneer tikka + dal", "estimated_calories": 480, "estimated_protein_g": 30, "confidence": 0.82}
            ],
            "swap_templates": [],
        }
        with patch("healthy_order_recommender.get_local_venue_profile", return_value=profile):
            out = suggest_best_order_for_place(place, health_score=6.5)
        self.assertTrue(out.get("matched_local_profile"))
        self.assertEqual(out.get("menu_item_source"), "local_venue_profile")
        self.assertIn("Paneer tikka", str(out.get("best_order") or ""))

    def test_heuristic_path_includes_matched_local_profile_false(self):
        """When no local profile, result has matched_local_profile=False for trace/audit."""
        place = {
            "name": "Unknown Grill House",
            "types": ["restaurant", "fast_food"],
            "lat": -34.5,
            "lng": 150.5,  # Outside launch area
        }
        out = suggest_best_order_for_place(place)
        self.assertFalse(out.get("matched_local_profile"))
        self.assertIn("best_order", out)

    def test_vegetarian_indian_gets_no_chicken_meat(self):
        """D. unknown restaurant still returns diet-safe fallback for vegetarian."""
        place = {"name": "Unknown Indian Place", "types": ["restaurant", "indian"], "vicinity": "Main Rd"}
        out = suggest_best_order_for_place(place, diet_preference="vegetarian")
        best = str(out.get("best_order") or "").lower()
        self.assertNotIn("chicken", best, f"Vegetarian should not get chicken: {best}")
        self.assertNotIn("meat", best)
        self.assertTrue(
            "paneer" in best or "dal" in best or "chana" in best or "roti" in best or "vegetarian" in best or "veg" in best,
            f"Expected veg-safe candidate, got: {best}",
        )

    def test_vegan_indian_gets_dal_roti_fallback(self):
        """D. unknown Indian + vegan user gets dal/roti (needs menu check) style."""
        place = {"name": "Unknown Indian Restaurant", "types": ["restaurant", "indian"], "vicinity": "Harris Park"}
        out = suggest_best_order_for_place(place, diet_preference="vegan")
        best = str(out.get("best_order") or "").lower()
        self.assertNotIn("chicken", best)
        self.assertNotIn("paneer", best)
        self.assertNotIn("egg", best)
        self.assertTrue(
            "dal" in best or "chana" in best or "roti" in best or "vegan" in best or "needs menu check" in best,
            f"Expected vegan-safe fallback, got: {best}",
        )


if __name__ == "__main__":
    unittest.main()

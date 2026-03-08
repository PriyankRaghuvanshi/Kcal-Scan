import unittest

from healthy_food_map import (
    build_healthy_food_map_response,
    enrich_places_for_healthy_map,
)


class HealthyFoodMapTests(unittest.TestCase):
    def test_high_score_place_gets_green_pin(self):
        out = enrich_places_for_healthy_map(
            [
                {
                    "name": "Nando's",
                    "place_id": "p1",
                    "lat": 28.61395,
                    "lng": 77.20905,
                    "health_score": 8.8,
                }
            ],
            origin_lat=28.6139,
            origin_lng=77.209,
        )
        row = out[0]
        self.assertEqual(row["score_band"], "high")
        self.assertEqual(row["map_pin_color"], "green")
        self.assertEqual(row["health_score_100"], 88)

    def test_medium_score_place_gets_yellow_pin(self):
        out = enrich_places_for_healthy_map([
            {"name": "Cafe", "place_id": "p2", "lat": 1.0, "lng": 1.0, "health_score": 7.2}
        ])
        self.assertEqual(out[0]["score_band"], "medium")
        self.assertEqual(out[0]["map_pin_color"], "yellow")

    def test_low_score_place_gets_red_pin(self):
        out = enrich_places_for_healthy_map([
            {"name": "Pizza", "place_id": "p3", "lat": 1.0, "lng": 1.0, "health_score": 4.5}
        ])
        self.assertEqual(out[0]["score_band"], "low")
        self.assertEqual(out[0]["map_pin_color"], "red")

    def test_missing_optional_fields_safe_fallback(self):
        out = enrich_places_for_healthy_map([{"name": "Unknown Spot"}])
        row = out[0]
        self.assertIn("place_name", row)
        self.assertIn("map_rank", row)
        self.assertIn("why_this_works", row)
        self.assertIn("badges", row)
        self.assertIsInstance(row["badges"], list)

    def test_selected_panel_intelligence_blocks_present(self):
        out = enrich_places_for_healthy_map(
            [
                {
                    "name": "Nando's",
                    "place_id": "n1",
                    "lat": 28.61395,
                    "lng": 77.20905,
                    "health_score": 8.8,
                    "top_menu_item": {
                        "item_name": "Quarter chicken + salad",
                        "estimated_calories": 540,
                        "estimated_protein_g": 44,
                        "short_reason": "High protein and easier to fit today.",
                    },
                    "decision_today": "YES",
                    "decision_reason": "Fits today's calories and gives strong protein.",
                    "fits_remaining_calories": True,
                    "fits_remaining_protein": True,
                    "reality_check": {
                        "typical_order": {"name": "Large combo", "estimated_calories": 900},
                        "smarter_order": {"name": "Quarter chicken + salad", "estimated_calories": 540, "estimated_protein_g": 44},
                        "calories_saved": 360,
                        "short_reason": "Much easier to fit into your cut.",
                    },
                }
            ]
        )
        row = out[0]
        self.assertIsInstance(row.get("top_menu_item"), dict)
        self.assertEqual(row["top_menu_item"].get("item_name"), "Quarter chicken + salad")
        self.assertIsInstance(row.get("today_fit"), dict)
        self.assertEqual(row["today_fit"].get("decision"), "YES")
        self.assertIsInstance(row.get("reality_check"), dict)
        self.assertEqual(row["reality_check"].get("calories_saved"), 360)
        self.assertIsInstance(row.get("coach_message"), dict)
        self.assertTrue(str(row["coach_message"].get("headline") or "").strip())
        self.assertIsInstance(row.get("intelligence_panel"), dict)
        self.assertIsInstance(row["intelligence_panel"].get("coach_message"), dict)

    def test_sparse_place_still_gets_panel_blocks(self):
        out = enrich_places_for_healthy_map([{"name": "Generic Food Place", "health_score": 6.1}])
        row = out[0]
        self.assertIsInstance(row.get("top_menu_item"), dict)
        self.assertTrue(str(row["top_menu_item"].get("item_name") or "").strip())
        self.assertIn(row["top_menu_item"].get("display_label"), {"Estimated Best Fit", "Suggested Lighter Option", "Needs Menu Check"})
        self.assertIn(row["top_menu_item"].get("menu_item_source"), {"heuristic", "llm_inferred", "real_menu"})
        self.assertIsInstance(row["top_menu_item"].get("menu_item_confidence"), float)
        self.assertIsInstance(row.get("today_fit"), dict)
        self.assertIn(row["today_fit"].get("decision"), {"YES", "MAYBE", "NO"})
        self.assertIsInstance(row.get("reality_check"), dict)
        self.assertIn("typical_order", row["reality_check"])
        self.assertIn("smarter_order", row["reality_check"])
        self.assertIsInstance(row.get("coach_message"), dict)
        self.assertTrue(str(row["coach_message"].get("headline") or "").strip())

    def test_low_confidence_top_item_gets_needs_menu_check_label(self):
        out = enrich_places_for_healthy_map(
            [
                {
                    "name": "Temple Canteen",
                    "health_score": 5.9,
                    "menu_items_source": "heuristic",
                    "top_menu_item": {
                        "item_name": "Lighter menu option",
                        "menu_item_source": "heuristic",
                        "menu_item_confidence": 0.32,
                    },
                }
            ]
        )
        row = out[0]
        self.assertEqual(row["top_menu_item"].get("display_label"), "Needs Menu Check")

    def test_build_response_shape(self):
        payload = build_healthy_food_map_response(
            places=[
                {
                    "name": "Protein Place",
                    "place_id": "px",
                    "lat": 28.61395,
                    "lng": 77.20905,
                    "health_score": 8.5,
                    "best_order": "Chicken bowl",
                    "estimated_calories": 540,
                    "estimated_protein_g": 42,
                    "decision_today": "YES",
                }
            ],
            lat=28.6139,
            lng=77.209,
            radius=2000,
            goal="fat_loss",
            cut_mode=True,
        )

        self.assertEqual(payload["title"], "Healthy Food Map")
        self.assertIn("map_context", payload)
        self.assertIn("places", payload)
        self.assertEqual(len(payload["places"]), 1)
        row = payload["places"][0]
        self.assertTrue(row["fit_for_today"])
        self.assertEqual(row["cta_label"], "Navigate")
        self.assertIsInstance(row.get("top_menu_item"), dict)
        self.assertIsInstance(row.get("today_fit"), dict)
        self.assertIsInstance(row.get("reality_check"), dict)
        self.assertIsInstance(row.get("coach_message"), dict)
        self.assertIsInstance(row.get("intelligence_panel"), dict)

    def test_closer_strong_healthy_place_beats_farther_weaker_place(self):
        out = enrich_places_for_healthy_map(
            [
                {
                    "name": "Subway Wentworthville",
                    "place_id": "subway-close",
                    "lat": -33.8048,
                    "lng": 150.9659,
                    "health_score": 8.3,
                    "decision_today": "YES",
                    "top_menu_item": {
                        "item_name": "6\" Chicken Breast Sub, extra salad, no mayo",
                        "item_score": 88,
                        "menu_item_source": "real_menu",
                        "menu_item_confidence": 0.9,
                        "order_type": "exact",
                    },
                },
                {
                    "name": "Far Fried Venue",
                    "place_id": "far-weak",
                    "lat": -33.8165,
                    "lng": 150.9790,
                    "health_score": 6.1,
                    "decision_today": "MAYBE",
                    "top_menu_item": {
                        "item_name": "Loaded combo",
                        "item_score": 48,
                        "menu_item_source": "heuristic",
                        "menu_item_confidence": 0.42,
                        "order_type": "estimated",
                    },
                },
            ],
            origin_lat=-33.8070,
            origin_lng=150.9670,
            goal="fat_loss",
            cut_mode=True,
        )
        self.assertEqual(out[0]["place_name"], "Subway Wentworthville")
        self.assertGreater(float(out[0]["local_ranking_score"]), float(out[1]["local_ranking_score"]))

    def test_farther_superior_place_can_beat_very_poor_close_place(self):
        out = enrich_places_for_healthy_map(
            [
                {
                    "name": "Very Poor Nearby",
                    "place_id": "poor-close",
                    "lat": -33.8052,
                    "lng": 150.9662,
                    "health_score": 3.4,
                    "decision_today": "NO",
                    "top_menu_item": {
                        "item_name": "Fried combo meal",
                        "item_score": 28,
                        "menu_item_source": "heuristic",
                        "menu_item_confidence": 0.31,
                        "order_type": "estimated",
                    },
                },
                {
                    "name": "Strong Grill Slightly Far",
                    "place_id": "strong-far",
                    "lat": -33.8190,
                    "lng": 150.9820,
                    "health_score": 9.1,
                    "decision_today": "YES",
                    "top_menu_item": {
                        "item_name": "Quarter chicken + salad",
                        "item_score": 94,
                        "menu_item_source": "real_menu",
                        "menu_item_confidence": 0.92,
                        "order_type": "exact",
                    },
                },
            ],
            origin_lat=-33.8070,
            origin_lng=150.9670,
            goal="fat_loss",
            cut_mode=True,
        )
        self.assertEqual(out[0]["place_name"], "Strong Grill Slightly Far")
        self.assertGreater(float(out[0]["restaurant_health_score"]), float(out[1]["restaurant_health_score"]))

    def test_local_distance_tiering_prefers_tier1_then_tier2_then_tier3_for_similar_quality(self):
        out = enrich_places_for_healthy_map(
            [
                {
                    "name": "Tier 3 Place",
                    "place_id": "tier3",
                    "lat": -33.8225,
                    "lng": 150.9818,
                    "health_score": 7.6,
                    "decision_today": "YES",
                    "top_menu_item": {"item_name": "Protein meal", "item_score": 78, "menu_item_confidence": 0.72, "menu_item_source": "real_menu", "order_type": "likely"},
                },
                {
                    "name": "Tier 2 Place",
                    "place_id": "tier2",
                    "lat": -33.8140,
                    "lng": 150.9720,
                    "health_score": 7.6,
                    "decision_today": "YES",
                    "top_menu_item": {"item_name": "Protein meal", "item_score": 78, "menu_item_confidence": 0.72, "menu_item_source": "real_menu", "order_type": "likely"},
                },
                {
                    "name": "Tier 1 Place",
                    "place_id": "tier1",
                    "lat": -33.8049,
                    "lng": 150.9662,
                    "health_score": 7.6,
                    "decision_today": "YES",
                    "top_menu_item": {"item_name": "Protein meal", "item_score": 78, "menu_item_confidence": 0.72, "menu_item_source": "real_menu", "order_type": "likely"},
                },
            ],
            origin_lat=-33.8070,
            origin_lng=150.9670,
            goal="fat_loss",
            cut_mode=False,
        )
        self.assertEqual(out[0]["place_name"], "Tier 1 Place")
        self.assertEqual(out[1]["place_name"], "Tier 2 Place")
        self.assertEqual(out[2]["place_name"], "Tier 3 Place")
        self.assertEqual(out[0]["distance_tier"], "tier_1")
        self.assertEqual(out[1]["distance_tier"], "tier_2")
        self.assertEqual(out[2]["distance_tier"], "tier_3")


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from menu_item_scoring import (
    recommend_menu_items_for_place,
    rank_menu_items_for_place,
    score_menu_item,
)
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
        self.assertIn(out["top_menu_item"].get("menu_item_source"), {"heuristic", "llm_inferred", "real_menu"})
        self.assertIn(
            out["top_menu_item"].get("display_label"),
            {"Estimated Best Fit", "Needs Menu Check", "Likely Better Choice", "Best Menu Item", "Suggested Lighter Option"},
        )

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
            "why_this_works",
            "confidence",
            "menu_item_source",
            "menu_item_confidence",
            "display_label",
            "copy_method",
            "copy_confidence",
            "copy_version",
            "recommendation_tags",
            "recommendation_version",
        }

        self.assertTrue(required_fields.issubset(top.keys()))
        self.assertIn(top["estimated_satiety"], {"high", "medium", "low"})
        self.assertGreaterEqual(float(top["confidence"]), 0.0)
        self.assertLessEqual(float(top["confidence"]), 1.0)
        self.assertLessEqual(len(str(top["short_reason"])), 90)

    def test_menu_item_breakdown_includes_new_penalty_dimensions(self):
        place = {"name": "Fried Dessert Combo Spot", "types": ["restaurant", "fast_food"]}
        ranked = rank_menu_items_for_place(
            place,
            [
                {"item_name": "Crispy fried combo + shake", "estimated_calories": 980, "estimated_protein_g": 20},
                {"item_name": "Grilled chicken salad", "estimated_calories": 470, "estimated_protein_g": 38},
            ],
            mode=NutritionMode.CUT,
        )
        self.assertGreaterEqual(len(ranked), 2)
        heavy = [x for x in ranked if "fried combo" in str(x.get("raw_item_name") or "").lower()][0]
        light = [x for x in ranked if "grilled chicken salad" in str(x.get("raw_item_name") or "").lower()][0]
        breakdown = heavy.get("item_score_breakdown") or {}
        self.assertIn("protein_density_score", breakdown)
        self.assertIn("calorie_control_score", breakdown)
        self.assertIn("fiber_satiety_score", breakdown)
        self.assertIn("fat_loss_score", breakdown)
        self.assertIn("processing_penalty", breakdown)
        self.assertIn("fried_penalty", breakdown)
        self.assertIn("sugar_penalty", breakdown)
        self.assertGreater(int(breakdown.get("processing_penalty", 0)), 0)
        self.assertGreater(int(breakdown.get("fried_penalty", 0)), 0)
        self.assertGreater(int(breakdown.get("sugar_penalty", 0)), 0)
        self.assertGreater(int(light.get("item_score", 0)), int(heavy.get("item_score", 0)))

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
            [item["item_score"] for item in default_ranked],
            [item["item_score"] for item in cut_ranked],
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

    def test_temple_canteen_avoids_unrealistic_generic_western_item(self):
        place = {
            "name": "Sri Venkateswara Temple Canteen",
            "types": ["restaurant", "canteen"],
            "vicinity": "South Indian Temple Road",
        }

        out = recommend_menu_items_for_place(place)
        top = out["top_menu_item"]

        self.assertTrue(str(top.get("item_name") or "").strip())
        self.assertNotIn("grilled protein bowl", str(top.get("item_name") or "").lower())
        self.assertIn(top.get("display_label"), {"Estimated Best Fit", "Suggested Lighter Option", "Needs Menu Check"})

    def test_llm_inferred_source_is_exposed_in_output(self):
        place = {"name": "Generic Cafe & Snacks", "types": ["restaurant", "cafe"]}
        mocked_bundle = {
            "parsed_items": [
                {
                    "item_name": "Lighter cafe meal option",
                    "confidence": 0.63,
                    "menu_item_source": "llm_inferred",
                }
            ],
            "parse_method": "llm_inferred",
            "parser_confidence": 0.63,
            "llm_enabled": True,
            "llm_attempted": True,
            "llm_error": "",
        }
        with patch("menu_item_scoring.infer_place_menu_items_with_optional_llm", return_value=mocked_bundle):
            out = recommend_menu_items_for_place(place)

        top = out["top_menu_item"]
        self.assertEqual(out["menu_items_source"], "llm_inferred")
        self.assertEqual(top.get("menu_item_source"), "llm_inferred")
        self.assertGreater(float(top.get("menu_item_confidence", 0.0)), 0.0)

    def test_burger_and_pizza_places_keep_cuisine_appropriate_items(self):
        burger_out = recommend_menu_items_for_place(
            {"name": "Downtown Burger Point", "types": ["restaurant", "fast_food", "burger"]}
        )
        pizza_out = recommend_menu_items_for_place(
            {"name": "City Pizza Hub", "types": ["restaurant", "pizza"]}
        )

        burger_name = str((burger_out.get("top_menu_item") or {}).get("item_name") or "").lower()
        pizza_name = str((pizza_out.get("top_menu_item") or {}).get("item_name") or "").lower()

        self.assertTrue(any(token in burger_name for token in ("burger", "wrap", "nugget", "lighter")))
        self.assertTrue(any(token in pizza_name for token in ("pizza", "slice", "lighter")))

    def test_sparse_unknown_place_uses_honest_low_confidence_label(self):
        out = recommend_menu_items_for_place({"name": "XYZ Eatery", "types": ["restaurant"]})
        top = out["top_menu_item"]
        self.assertTrue(str(top.get("item_name") or "").strip())
        self.assertNotIn("grilled protein bowl", str(top.get("item_name") or "").lower())
        self.assertIn(top.get("display_label"), {"Estimated Best Fit", "Needs Menu Check", "Suggested Lighter Option"})
        self.assertEqual(top.get("order_type"), "estimated")
        self.assertNotEqual(top.get("order_type"), "exact")
        self.assertTrue(str(top.get("swap_suggestion") or "").strip())
        self.assertIsInstance(top.get("skip_items"), list)
        self.assertIsInstance(top.get("add_items"), list)

    def test_high_confidence_real_menu_item_uses_exact_order_type(self):
        scored = score_menu_item(
            {
                "item_name": "6\" Chicken Breast Sub, extra salad, no mayo",
                "estimated_calories": 430,
                "estimated_protein_g": 34,
                "menu_source": "website_menu",
                "menu_confidence": 0.92,
                "confidence": 0.92,
            },
            context={
                "place_text": "subway sandwich",
                "cuisine_hint": "sandwich",
                "menu_source": "website_menu",
            },
        )
        self.assertEqual(scored.get("order_type"), "exact")
        self.assertEqual(
            scored.get("item_name"),
            "6\" Chicken Breast Sub, extra salad, no mayo",
        )
        self.assertTrue(str(scored.get("swap_suggestion") or "").strip())

    def test_medium_confidence_llm_inferred_item_uses_likely_order_type(self):
        scored = score_menu_item(
            {
                "item_name": "Tandoori chicken-style plate with lighter sides",
                "estimated_calories": 560,
                "estimated_protein_g": 36,
                "menu_source": "llm_inferred",
                "menu_confidence": 0.62,
                "confidence": 0.62,
            },
            context={
                "place_text": "indian restaurant",
                "cuisine_hint": "indian",
                "menu_source": "llm_inferred",
            },
        )
        self.assertEqual(scored.get("order_type"), "likely")
        self.assertIn(
            scored.get("display_label"),
            {"Likely Better Choice", "Suggested Lighter Option"},
        )

    def test_real_menu_ingestion_is_prioritized_when_available(self):
        place = {
            "place_id": "real-menu-1",
            "name": "Temple Canteen",
            "types": ["restaurant", "canteen"],
        }
        ingested = {
            "ingested": True,
            "menu_items": [
                {
                    "item_name": "Idli + sambar",
                    "confidence": 0.82,
                    "menu_confidence": 0.82,
                    "source": "website_menu",
                    "menu_source": "website_menu",
                    "source_url": "https://example.org/menu",
                    "extraction_method": "menu_link_fetch",
                    "parse_method": "deterministic",
                    "raw_text_snippet": "Idli + sambar",
                },
                {
                    "item_name": "Plain dosa",
                    "confidence": 0.76,
                    "menu_confidence": 0.76,
                    "source": "website_menu",
                    "menu_source": "website_menu",
                    "source_url": "https://example.org/menu",
                    "extraction_method": "menu_link_fetch",
                    "parse_method": "deterministic",
                    "raw_text_snippet": "Plain dosa",
                },
            ],
            "menu_source": "website_menu",
            "menu_confidence": 0.79,
            "extraction_method": "menu_link_fetch",
            "parse_method": "deterministic",
            "source_url": "https://example.org/menu",
            "menu_ingestion_version": "v1",
        }

        with patch("menu_item_scoring.ingest_real_menu_for_place", return_value=ingested):
            out = recommend_menu_items_for_place(place)

        self.assertEqual(out["menu_items_source"], "website_menu")
        self.assertEqual(out["menu_source"], "website_menu")
        self.assertEqual(out["source_url"], "https://example.org/menu")
        self.assertTrue(str(out.get("top_item") or "").strip())
        self.assertNotIn("grilled protein bowl", str(out.get("top_item") or "").lower())
        top = out["top_menu_item"]
        self.assertEqual(top.get("order_type"), "exact")
        self.assertTrue(str(top.get("swap_suggestion") or "").strip())
        self.assertIsInstance(top.get("skip_items"), list)
        self.assertIsInstance(top.get("add_items"), list)


if __name__ == "__main__":
    unittest.main()

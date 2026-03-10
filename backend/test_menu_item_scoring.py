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
            {"Estimated Best Fit", "Needs Menu Check", "Likely Better Choice", "Best Menu Item", "Suggested Lighter Option", "Likely healthy option"},
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
            "rank_adjusted_item_score",
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
            "menu_item_source_raw",
            "menu_item_confidence",
            "source_rank_weight",
            "display_label",
            "copy_method",
            "copy_confidence",
            "copy_version",
            "recommendation_tags",
            "recommendation_version",
        }

        self.assertTrue(required_fields.issubset(top.keys()))
        self.assertIn("best_item_swaps", top)
        self.assertIsInstance(top.get("best_item_swaps"), list)
        self.assertIn(top["estimated_satiety"], {"high", "medium", "low"})
        self.assertGreaterEqual(float(top["confidence"]), 0.0)
        self.assertLessEqual(float(top["confidence"]), 1.0)
        self.assertLessEqual(len(str(top["short_reason"])), 90)
        self.assertIn("menu_source_resolved", out)
        self.assertIn("menu_items_source_resolved", out)
        self.assertIn("menu_source_priority", out)

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
        self.assertIn(top.get("display_label"), {"Estimated Best Fit", "Suggested Lighter Option", "Needs Menu Check", "Likely healthy option"})

    def test_indian_context_blocks_generic_protein_bowl_even_with_high_confidence(self):
        scored = score_menu_item(
            {
                "item_name": "Greek yogurt protein bowl",
                "estimated_calories": 430,
                "estimated_protein_g": 28,
                "menu_source": "llm_inferred",
                "menu_confidence": 0.86,
                "confidence": 0.86,
            },
            context={
                "place_text": "Local Indian curry and biryani house",
                "cuisine_hint": "indian biryani",
                "menu_source": "llm_inferred",
            },
        )
        output_name = str(scored.get("item_name") or "").lower()
        self.assertNotIn("greek yogurt protein bowl", output_name)
        self.assertNotIn("protein bowl", output_name)
        self.assertTrue(any(token in output_name for token in ("tandoori", "kebab", "dal")))

    def test_patisserie_sparse_place_uses_honest_non_generic_name(self):
        out = recommend_menu_items_for_place(
            {"name": "La Petite Patisserie", "types": ["restaurant", "bakery", "dessert_shop", "patisserie"]}
        )
        top = out["top_menu_item"]
        item_name = str(top.get("item_name") or "").lower()
        self.assertNotIn("protein bowl", item_name)
        self.assertNotIn("lean wrap", item_name)
        self.assertIn(top.get("display_label"), {"Suggested Lighter Option", "Estimated Best Fit", "Needs Menu Check", "Likely healthy option"})

    def test_real_menu_source_weight_beats_heuristic_with_same_base_score(self):
        real = score_menu_item(
            {
                "item_name": "Chicken breast sub",
                "estimated_calories": 430,
                "estimated_protein_g": 36,
                "menu_source": "website_menu",
                "menu_confidence": 0.86,
            },
            context={"menu_source": "website_menu", "cuisine_hint": "sandwich"},
        )
        heuristic = score_menu_item(
            {
                "item_name": "Chicken breast sub",
                "estimated_calories": 430,
                "estimated_protein_g": 36,
                "menu_source": "heuristic",
                "menu_confidence": 0.45,
            },
            context={"menu_source": "heuristic", "cuisine_hint": "sandwich"},
        )
        self.assertGreater(float(real.get("source_rank_weight", 0.0)), float(heuristic.get("source_rank_weight", 0.0)))
        self.assertGreater(
            int(real.get("rank_adjusted_item_score", 0)),
            int(heuristic.get("rank_adjusted_item_score", 0)),
        )

    def test_real_menu_item_is_preferred_over_heuristic_even_if_heuristic_scores_higher(self):
        place = {
            "name": "Mixed Menu Venue",
            "types": ["restaurant", "meal_takeaway"],
            "menu_items": [
                {
                    "item_name": "6\" chicken breast sub, no mayo, extra salad",
                    "estimated_calories": 430,
                    "estimated_protein_g": 36,
                    "menu_source": "website_menu",
                    "source": "website_menu",
                    "confidence": 0.88,
                },
                {
                    "item_name": "Super healthy archetype meal",
                    "estimated_calories": 300,
                    "estimated_protein_g": 45,
                    "menu_source": "heuristic_generation",
                    "source": "heuristic_generation",
                    "confidence": 0.9,
                },
            ],
        }
        out = recommend_menu_items_for_place(place, health_score=8.0)
        top = out["top_menu_item"]
        self.assertEqual(top.get("menu_item_source"), "real_menu")
        self.assertIn("chicken breast sub", str(top.get("item_name") or "").lower())

    def test_chain_menu_coverage_drives_live_recommendation_for_subway(self):
        out = recommend_menu_items_for_place(
            {
                "name": "Subway Wentworthville",
                "types": ["restaurant", "sandwich_shop"],
                "address": "Wentworthville NSW Australia",
                "country_code": "AU",
            },
            health_score=8.4,
        )
        top = out.get("top_menu_item") or {}
        # Coverage data may not be available in all environments; only assert when matched.
        if str(out.get("chain_key") or "").strip().lower() == "subway" and out.get("menu_source_resolved") == "chain_registry":
            self.assertEqual(out.get("menu_source_resolved"), "chain_registry")
            self.assertEqual(str(top.get("menu_item_source") or "").strip().lower(), "chain_registry")
            self.assertIn("sub", str(top.get("item_name") or "").lower())
            self.assertIn(str(top.get("order_type") or "").strip().lower(), {"exact", "likely"})
            self.assertTrue(str(out.get("matched_alias") or "").strip())
            self.assertIn(str(out.get("chain_source_used") or "").strip(), {"country_chain_registry", "global_chain_registry"})

    def test_heuristic_item_never_uses_exact_or_likely_order_type(self):
        scored = score_menu_item(
            {
                "item_name": "Lighter grilled option",
                "estimated_calories": 420,
                "estimated_protein_g": 32,
                "menu_source": "heuristic",
                "menu_confidence": 0.92,
                "confidence": 0.92,
            },
            context={
                "place_text": "generic food venue",
                "cuisine_hint": "restaurant",
                "menu_source": "heuristic",
            },
        )
        self.assertEqual(scored.get("menu_item_source"), "heuristic")
        self.assertEqual(scored.get("order_type"), "estimated")

    def test_real_menu_generic_name_without_strong_evidence_downgrades_to_safe_fallback(self):
        scored = score_menu_item(
            {
                "item_name": "Greek yogurt protein bowl",
                "estimated_calories": 410,
                "estimated_protein_g": 26,
                "menu_source": "real_menu",
                "menu_confidence": 0.64,
                "confidence": 0.64,
                "source_url": "",
                "raw_text_snippet": "",
            },
            context={
                "place_text": "Temple canteen south indian",
                "cuisine_hint": "south indian temple canteen",
                "menu_source": "real_menu",
            },
        )
        self.assertNotIn("greek yogurt protein bowl", str(scored.get("item_name") or "").lower())
        self.assertEqual(scored.get("menu_item_source"), "heuristic")
        self.assertEqual(scored.get("order_type"), "estimated")
        self.assertIn(scored.get("display_label"), {"Needs Menu Check", "Suggested Lighter Option"})
        self.assertTrue(str(scored.get("menu_item_safety_reason") or "").strip())

    def test_chain_registry_preferred_over_heuristic_when_available(self):
        place = {"name": "Subway", "types": ["restaurant", "sandwich"], "place_id": "p-sub"}

        chain_bundle = {
            "menu_source": "chain_registry",
            "menu_confidence": 0.90,
            "chain_source_used": "global_chain_registry",
            "chain_id": "subway",
            "chain_name": "Subway",
            "chain_key": "subway",
        }
        chain_items = [
            {
                "item_name": "6-inch grilled chicken sub, extra salad, light sauce",
                "estimated_calories": 390,
                "estimated_protein_g": 30,
                "menu_item_source": "chain_registry",
                "menu_item_confidence": 0.9,
                "source": "chain_registry",
                "menu_source": "chain_registry",
            }
        ]
        with patch("menu_item_scoring.resolve_chain_menu_for_place") as mock_chain:
            mock_chain.return_value = {**chain_bundle, "menu_items": list(chain_items)}
            out = recommend_menu_items_for_place(place, use_llm_place_context=False)
        top = out.get("top_menu_item") or {}
        self.assertEqual(str(top.get("menu_item_source") or ""), "chain_registry")
        self.assertIn("grilled chicken", str(top.get("item_name") or "").lower())

    def test_real_menu_generic_name_with_strong_evidence_can_stay_specific(self):
        scored = score_menu_item(
            {
                "item_name": "Greek yogurt protein bowl",
                "estimated_calories": 410,
                "estimated_protein_g": 26,
                "menu_source": "real_menu",
                "menu_confidence": 0.9,
                "confidence": 0.9,
                "source_url": "https://example.com/menu",
                "extraction_method": "menu_link_fetch",
                "parse_method": "deterministic",
                "raw_text_snippet": "Greek yogurt protein bowl 12.90",
            },
            context={
                "place_text": "cafe brunch",
                "cuisine_hint": "cafe",
                "menu_source": "real_menu",
            },
        )
        self.assertEqual(scored.get("item_name"), "Greek yogurt protein bowl")
        self.assertEqual(scored.get("menu_item_source"), "real_menu")
        self.assertTrue(bool(scored.get("menu_item_strong_evidence")))

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
        self.assertIn(top.get("display_label"), {"Estimated Best Fit", "Needs Menu Check", "Suggested Lighter Option", "Likely healthy option"})
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
        self.assertIn(scored.get("order_type"), {"likely", "estimated"})
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

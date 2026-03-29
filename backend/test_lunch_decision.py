import unittest

from lunch_decision import build_lunch_decision_response


class LunchDecisionTests(unittest.TestCase):
    def test_best_card_picks_strong_fit(self):
        nearby_places = [
            {
                "name": "Protein Grill House",
                "place_id": "p1",
                "lat": 28.61395,
                "lng": 77.20905,
                "types": ["restaurant", "grill", "healthy"],
                "menu_items": [
                    {
                        "item_name": "Grilled chicken bowl",
                        "estimated_calories": 520,
                        "estimated_protein_g": 44,
                    }
                ],
            },
            {
                "name": "Burger Combo Spot",
                "place_id": "p2",
                "lat": 28.61440,
                "lng": 77.20950,
                "types": ["restaurant", "fast_food", "burger"],
                "menu_items": [
                    {
                        "item_name": "Loaded fried combo",
                        "estimated_calories": 980,
                        "estimated_protein_g": 24,
                    }
                ],
            },
            {
                "name": "Healthy Bowl Co",
                "place_id": "p3",
                "lat": 28.61410,
                "lng": 77.20920,
                "types": ["restaurant", "healthy", "salad"],
                "menu_items": [
                    {
                        "item_name": "Chicken quinoa bowl",
                        "estimated_calories": 500,
                        "estimated_protein_g": 38,
                    }
                ],
            },
        ]

        out = build_lunch_decision_response(
            nearby_places=nearby_places,
            origin_lat=28.6139,
            origin_lng=77.2090,
            remaining_calories=1300,
            remaining_protein_g=90,
            goal="fat_loss",
            cut_mode=True,
        )

        self.assertEqual(out["title"], "What should I eat right now?")
        self.assertEqual(out["subtitle"], "Best lunch near you")
        self.assertEqual(out["summary_line"], "Based on your remaining calories and protein")
        self.assertIsInstance(out.get("day_coach"), dict)
        self.assertIsInstance(out["day_coach"].get("day_summary"), dict)
        self.assertIsInstance(out["day_coach"].get("next_meal_guidance"), dict)
        self.assertGreaterEqual(len(out["cards"]), 2)

        top = out["cards"][0]
        self.assertEqual(top["card_type"], "best_right_now")
        self.assertEqual(top["place_name"], "Protein Grill House")
        self.assertGreaterEqual(int(top.get("estimated_protein_g", 0)), 30)
        self.assertEqual(top.get("cta_label"), "Navigate")
        self.assertIsInstance(top.get("swap_suggestions"), list)
        self.assertGreaterEqual(len(top.get("swap_suggestions") or []), 1)
        self.assertLessEqual(len(top.get("swap_suggestions") or []), 3)
        self.assertIn(
            top.get("recommended_order_label"),
            {
                "Best Menu Item",
                "Likely Better Choice",
                "Suggested Lighter Option",
                "Estimated Best Fit",
                "Needs Menu Check",
                "No menu on file",
            },
        )
        self.assertIn("fit_for_today", top)
        self.assertIn("daily_fit_score", top)

        self.assertEqual(out.get("selected_place_id"), top.get("place_id"))
        self.assertEqual(out.get("selected_place_name"), top.get("place_name"))
        self.assertIsNotNone(out.get("selected_place_lat"))
        self.assertIsNotNone(out.get("selected_place_lng"))

    def test_better_alternative_is_not_the_top_card(self):
        nearby_places = [
            {
                "name": "Lean Grill",
                "place_id": "a1",
                "lat": 28.61395,
                "lng": 77.20905,
                "types": ["restaurant", "grill"],
                "menu_items": [
                    {
                        "item_name": "Grilled chicken wrap",
                        "estimated_calories": 490,
                        "estimated_protein_g": 36,
                    }
                ],
            },
            {
                "name": "Salad Stack",
                "place_id": "a2",
                "lat": 28.61415,
                "lng": 77.20930,
                "types": ["restaurant", "salad", "healthy"],
                "menu_items": [
                    {
                        "item_name": "Protein salad",
                        "estimated_calories": 460,
                        "estimated_protein_g": 34,
                    }
                ],
            },
            {
                "name": "Fried Box",
                "place_id": "a3",
                "lat": 28.61435,
                "lng": 77.20955,
                "types": ["restaurant", "fast_food", "fried"],
                "menu_items": [
                    {
                        "item_name": "Fried mega combo",
                        "estimated_calories": 1020,
                        "estimated_protein_g": 22,
                    }
                ],
            },
        ]

        out = build_lunch_decision_response(
            nearby_places=nearby_places,
            origin_lat=28.6139,
            origin_lng=77.2090,
            remaining_calories=1200,
            remaining_protein_g=80,
        )

        self.assertGreaterEqual(len(out["cards"]), 2)
        self.assertEqual(out["cards"][1]["card_type"], "better_alternative")
        self.assertNotEqual(out["cards"][1]["place_name"], out["cards"][0]["place_name"])

    def test_hard_to_fit_card_surfaces_calorie_dense_option(self):
        nearby_places = [
            {
                "name": "Protein Bowl Lab",
                "place_id": "h1",
                "lat": 28.61395,
                "lng": 77.20905,
                "types": ["restaurant", "healthy", "bowl"],
                "menu_items": [
                    {
                        "item_name": "Chicken bowl",
                        "estimated_calories": 520,
                        "estimated_protein_g": 40,
                    }
                ],
            },
            {
                "name": "Pizza Hut",
                "place_id": "h2",
                "lat": 28.6148,
                "lng": 77.2102,
                "types": ["restaurant", "pizza"],
                "menu_items": [
                    {
                        "item_name": "Large cheesy combo",
                        "estimated_calories": 1150,
                        "estimated_protein_g": 30,
                    }
                ],
            },
            {
                "name": "Burger King",
                "place_id": "h3",
                "lat": 28.6144,
                "lng": 77.2098,
                "types": ["restaurant", "fast_food", "burger"],
                "menu_items": [
                    {
                        "item_name": "Double burger combo",
                        "estimated_calories": 980,
                        "estimated_protein_g": 27,
                    }
                ],
            },
        ]

        out = build_lunch_decision_response(
            nearby_places=nearby_places,
            origin_lat=28.6139,
            origin_lng=77.2090,
            remaining_calories=650,
            remaining_protein_g=55,
            goal="fat_loss",
            cut_mode=True,
        )

        self.assertEqual(out["cards"][2]["card_type"], "hard_to_fit_today")
        self.assertIn("typical_calorie_range", out["cards"][2])
        self.assertEqual(out["cards"][2].get("remaining_calories"), 650)
        self.assertFalse(bool(out["cards"][2].get("fit_for_today")))

    def test_missing_daily_context_degrades_gracefully(self):
        out = build_lunch_decision_response(
            nearby_places=[
                {
                    "name": "Cafe One",
                    "place_id": "m1",
                    "lat": 28.61395,
                    "lng": 77.20905,
                    "types": ["restaurant", "cafe"],
                }
            ],
            origin_lat=28.6139,
            origin_lng=77.2090,
            remaining_calories=None,
            remaining_protein_g=None,
        )

        self.assertIn("cards", out)
        self.assertGreaterEqual(len(out["cards"]), 1)
        self.assertIsNone(out["decision_context"]["remaining_calories"])
        self.assertIsNone(out["decision_context"]["remaining_protein_g"])
        self.assertEqual(out["summary_line"], "Based on nearby menu quality and smart swaps")
        self.assertNotIn("grilled protein bowl", str(out["cards"][0].get("recommended_order") or "").lower())

    def test_share_card_present_for_top_card(self):
        out = build_lunch_decision_response(
            nearby_places=[
                {
                    "name": "Nando's",
                    "place_id": "s1",
                    "lat": 28.61395,
                    "lng": 77.20905,
                    "types": ["restaurant", "grill", "healthy"],
                    "menu_items": [
                        {
                            "item_name": "Quarter chicken + salad",
                            "estimated_calories": 540,
                            "estimated_protein_g": 44,
                        }
                    ],
                }
            ],
            origin_lat=28.6139,
            origin_lng=77.2090,
            remaining_calories=1300,
            remaining_protein_g=90,
            goal="fat_loss",
            cut_mode=True,
        )

        top = out["cards"][0]
        self.assertIsInstance(top.get("share_card"), dict)
        self.assertEqual(top["share_card"].get("title"), "Smarter Order")
        self.assertIn("calories_saved", top["share_card"])
        self.assertIsInstance(out.get("top_share_card"), dict)
        self.assertIn("tracking", top)
        self.assertIn(top.get("copy_method"), {"deterministic", "llm"})
        self.assertGreaterEqual(float(top.get("copy_confidence", 0.0)), 0.0)
        self.assertEqual(top.get("copy_version"), "v1")
        self.assertIsInstance(top.get("reality_check"), dict)
        self.assertEqual(top["reality_check"].get("title"), "Restaurant Reality Check")
        self.assertIn(top["reality_check"].get("copy_method"), {"deterministic", "llm"})
        self.assertGreaterEqual(float(top["reality_check"].get("copy_confidence", 0.0)), 0.0)
        self.assertEqual(top["reality_check"].get("copy_version"), "v1")
        self.assertIsInstance(top.get("reality_check_share_card"), dict)

    def test_cuisine_guardrails_block_generic_fallback_in_cards(self):
        out = build_lunch_decision_response(
            nearby_places=[
                {
                    "name": "Temple Canteen",
                    "place_id": "g1",
                    "lat": 28.61395,
                    "lng": 77.20905,
                    "types": ["restaurant", "south_indian", "temple", "canteen"],
                    "menu_items": [
                        {
                            "item_name": "Greek yogurt protein bowl",
                            "estimated_calories": 410,
                            "estimated_protein_g": 26,
                        }
                    ],
                }
            ],
            origin_lat=28.6139,
            origin_lng=77.2090,
            remaining_calories=1000,
            remaining_protein_g=70,
        )
        card = out["cards"][0]
        self.assertNotIn("greek yogurt protein bowl", str(card.get("recommended_order") or "").lower())
        ro = str(card.get("recommended_order") or "").lower()
        self.assertIn("no menu on file", ro)
        self.assertTrue(
            any(
                x in ro
                for x in (
                    "idli",
                    "dosa",
                    "tandoori",
                    "lentil",
                    "savory",
                )
            ),
            msg=f"expected south indian / indian pattern copy, got: {ro!r}",
        )
        self.assertIsInstance(card.get("swap_suggestions"), list)
        self.assertGreaterEqual(len(card.get("swap_suggestions") or []), 1)
        self.assertTrue(
            any(
                token in " ".join(card.get("swap_suggestions") or []).lower()
                for token in ("lighter", "fried", "creamy", "tandoori", "dal")
            )
        )

    def test_nearby_subway_real_menu_beats_farther_weaker_inferred(self):
        out = build_lunch_decision_response(
            nearby_places=[
                {
                    "name": "Subway Wentworthville",
                    "place_id": "sub-near",
                    "lat": -33.8048,
                    "lng": 150.9659,
                    "types": ["restaurant", "sandwich_shop"],
                    "menu_items": [
                        {
                            "item_name": "6\" Chicken Breast Sub, extra salad, no mayo",
                            "estimated_calories": 430,
                            "estimated_protein_g": 38,
                            "menu_source": "website_menu",
                            "menu_confidence": 0.9,
                            "source_url": "https://subway.example/menu",
                        }
                    ],
                },
                {
                    "name": "Far Generic Venue",
                    "place_id": "far-weak",
                    "lat": -33.8165,
                    "lng": 150.9790,
                    "types": ["restaurant", "indian", "biryani"],
                    "menu_items": [
                        {
                            "item_name": "Suggested lighter option",
                            "estimated_calories": 620,
                            "estimated_protein_g": 24,
                            "menu_source": "heuristic",
                            "menu_confidence": 0.42,
                        }
                    ],
                },
            ],
            origin_lat=-33.8070,
            origin_lng=150.9670,
            remaining_calories=1200,
            remaining_protein_g=80,
            cut_mode=True,
            goal="fat_loss",
        )
        self.assertEqual(out["cards"][0]["place_name"], "Subway Wentworthville")

    def test_cut_mode_changes_context_but_keeps_schema(self):
        nearby_places = [
            {
                "name": "Protein Grill House",
                "place_id": "c1",
                "lat": 28.61395,
                "lng": 77.20905,
                "types": ["restaurant", "grill", "healthy"],
            }
        ]
        out_default = build_lunch_decision_response(
            nearby_places=nearby_places,
            origin_lat=28.6139,
            origin_lng=77.2090,
            remaining_calories=1200,
            remaining_protein_g=80,
            cut_mode=False,
        )
        out_cut = build_lunch_decision_response(
            nearby_places=nearby_places,
            origin_lat=28.6139,
            origin_lng=77.2090,
            remaining_calories=1200,
            remaining_protein_g=80,
            cut_mode=True,
            goal="fat_loss",
        )

        self.assertIn("cards", out_default)
        self.assertIn("cards", out_cut)
        self.assertEqual(out_default["cards"][0]["card_type"], "best_right_now")
        self.assertEqual(out_cut["cards"][0]["card_type"], "best_right_now")
        self.assertFalse(out_default["decision_context"]["cut_mode"])
        self.assertTrue(out_cut["decision_context"]["cut_mode"])


if __name__ == "__main__":
    unittest.main()

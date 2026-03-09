import unittest

from swap_intelligence import build_swap_suggestions


class SwapIntelligenceTests(unittest.TestCase):
    def test_subway_style_swaps_are_practical(self):
        out = build_swap_suggestions(
            swap_suggestion="Skip mayo, add extra salad.",
            skip_items=["mayo"],
            add_items=["extra salad", "water or zero-sugar drink"],
            place_context="Subway Wentworthville sandwich shop",
            menu_item_source="real_menu",
            menu_item_confidence=0.9,
        )
        joined = " | ".join(out).lower()
        self.assertGreaterEqual(len(out), 2)
        self.assertIn("skip mayo", joined)
        self.assertTrue("extra salad" in joined or "zero-sugar drink" in joined)

    def test_low_confidence_indian_swaps_stay_soft(self):
        out = build_swap_suggestions(
            swap_suggestion="",
            skip_items=[],
            add_items=[],
            place_context="Local Indian temple canteen",
            menu_item_source="heuristic",
            menu_item_confidence=0.35,
        )
        self.assertGreaterEqual(len(out), 1)
        joined = " | ".join(out).lower()
        self.assertTrue("lighter" in joined or "fried" in joined or "creamy" in joined)

    def test_output_is_deduped_and_capped(self):
        out = build_swap_suggestions(
            swap_suggestion="Skip fries, add side salad.",
            skip_items=["fries", "fries"],
            add_items=["side salad", "side salad", "water or zero-sugar drink"],
            place_context="Fast food burger place",
            menu_item_source="heuristic",
            menu_item_confidence=0.5,
            max_items=3,
        )
        self.assertLessEqual(len(out), 3)
        self.assertEqual(len(out), len(set(x.lower() for x in out)))


if __name__ == "__main__":
    unittest.main()


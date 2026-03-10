"""
Tests for cuisine-specific candidate rules: Indian, South Indian, cafe, juice, pizza, Subway,
generic fallback suppression, and audit candidate debug.
"""
from __future__ import annotations

import unittest

from cuisine_candidate_rules import (
    get_candidates_for_place,
    get_best_order_for_place_heuristic,
    select_best_candidate,
    is_generic_fallback_for_label,
    BAD_FALLBACK_SUPPRESS_TOKENS,
    CUISINE_GROUPS,
)


def _place(name: str, **kwargs) -> dict:
    d = {"name": name, "vicinity": "", "types": []}
    d.update(kwargs)
    return d


class TestIndianCandidateSelection(unittest.TestCase):
    def test_indian_restaurant_gets_tandoori_dal_style_primary(self):
        place = _place("Darbar Indian Restaurant")
        candidates, cuisine_id, conf, _ = get_candidates_for_place(place)
        self.assertEqual(cuisine_id, "north_indian")
        self.assertGreater(len(candidates), 0)
        primary = candidates[0]
        name = (primary.get("candidate_name") or "").lower()
        self.assertTrue(
            "tandoori" in name or "tikka" in name or "dal" in name or "paneer" in name or "bhurji" in name,
            f"Expected tandoori/tikka/dal/paneer/bhurji in primary, got: {primary.get('candidate_name')}",
        )
        self.assertNotIn("butter chicken", name)
        self.assertNotIn("biryani", name)
        self.assertNotIn("samosa", name)
        self.assertNotIn("pakora", name)

    def test_indian_best_order_heuristic(self):
        place = _place("Generic Indian Restaurant")
        name, cal, pro, conf, _src, all_c = get_best_order_for_place_heuristic(place, cut_mode=True)
        name_lower = name.lower()
        self.assertTrue(
            "tandoori" in name_lower or "tikka" in name_lower or "dal" in name_lower or "paneer" in name_lower,
            msg=f"Expected tandoori/tikka/dal/paneer in best order, got: {name}",
        )
        self.assertGreaterEqual(pro, 26)
        self.assertLessEqual(cal, 620)


class TestSouthIndianCandidateSelection(unittest.TestCase):
    def test_south_indian_gets_idli_dosa_egg_style(self):
        place = _place("Chennai Filter Coffee", vicinity="South Indian cafe")
        candidates, cuisine_id, conf, _ = get_candidates_for_place(place)
        self.assertEqual(cuisine_id, "south_indian")
        names = [str(c.get("candidate_name") or "").lower() for c in candidates]
        self.assertTrue(
            any("idli" in n or "dosa" in n or "sambar" in n or "omelette" in n or "egg" in n for n in names),
            f"Expected idli/dosa/sambar/egg in candidates, got: {names}",
        )
        self.assertFalse(any("coffee only" in n or "sweet beverage" in n for n in names))

    def test_south_indian_best_order(self):
        place = _place("Udupi Temple Canteen")
        name, cal, pro, conf, _src, _ = get_best_order_for_place_heuristic(place)
        self.assertTrue(
            "dosa" in name.lower() or "idli" in name.lower() or "egg" in name.lower() or "uthappam" in name.lower(),
            f"Expected dosa/idli/egg/uthappam, got: {name}",
        )


class TestGeneralCafeCandidateSelection(unittest.TestCase):
    def test_cafe_gets_eggs_wrap_not_pastry(self):
        place = _place("Local Cafe", types=["cafe", "coffee_shop"])
        candidates, cuisine_id, conf, _ = get_candidates_for_place(place)
        self.assertEqual(cuisine_id, "cafe")
        primary = (candidates[0].get("candidate_name") or "").lower()
        self.assertTrue(
            "egg" in primary or "wrap" in primary or "sandwich" in primary or "omelette" in primary,
            f"Expected egg/wrap/sandwich in primary, got: {primary}",
        )
        self.assertNotIn("banana bread", primary)
        self.assertNotIn("muffin", primary)
        self.assertNotIn("pastry", primary)


class TestJuiceCenterCandidateSelection(unittest.TestCase):
    def test_juice_center_lower_confidence(self):
        place = _place("Fresh Juice Bar")
        candidates, cuisine_id, conf, source_label = get_candidates_for_place(place)
        self.assertEqual(cuisine_id, "juice_smoothie")
        self.assertLessEqual(conf, 0.55, "Juice center should have lower heuristic confidence")
        self.assertIn("weak", source_label.lower() or "heuristic")

    def test_juice_does_not_invent_high_protein_bowl(self):
        place = _place("Smoothie Place")
        name, cal, pro, conf, _src, _ = get_best_order_for_place_heuristic(place)
        self.assertLessEqual(conf, 0.55)
        self.assertFalse(
            "protein bowl" in name.lower() and pro > 35,
            "Should not invent high-protein bowl for juice place",
        )


class TestPizzaCandidateSelection(unittest.TestCase):
    def test_pizza_gets_controlled_portion(self):
        place = _place("Pizza Hut", types=["pizza", "restaurant"])
        candidates, cuisine_id, conf, _ = get_candidates_for_place(place)
        self.assertEqual(cuisine_id, "pizza")
        primary = (candidates[0].get("candidate_name") or "").lower()
        self.assertTrue("thin" in primary or "slice" in primary or "portion" in primary, f"Got: {primary}")
        self.assertNotIn("combo", primary)
        self.assertNotIn("garlic bread", primary)
        self.assertNotIn("loaded crust", primary)


class TestSubwayStyleCandidateSelection(unittest.TestCase):
    def test_subway_gets_grilled_chicken_style(self):
        place = _place("Subway", types=["sandwich", "subway"])
        candidates, cuisine_id, conf, _ = get_candidates_for_place(place)
        self.assertEqual(cuisine_id, "sandwich_sub")
        primary = (candidates[0].get("candidate_name") or "").lower()
        self.assertTrue("grilled" in primary or "chicken" in primary or "turkey" in primary or "salad" in primary)
        self.assertNotIn("meatball", primary)


class TestGenericFallbackSuppression(unittest.TestCase):
    def test_no_strong_cuisine_does_not_use_global_generic_as_primary(self):
        place = _place("Unknown Place XYZ")
        candidates, cuisine_id, conf, _ = get_candidates_for_place(place)
        if not candidates:
            return
        primary = (candidates[0].get("candidate_name") or "").strip().lower()
        for bad in ("egg + chicken plate", "lighter menu option", "salad + chicken plate"):
            self.assertNotEqual(primary, bad, f"Primary should not be generic fallback: {primary}")

    def test_is_generic_fallback_for_label(self):
        self.assertTrue(is_generic_fallback_for_label("Lighter menu option"))
        self.assertTrue(is_generic_fallback_for_label("Egg + chicken plate"))
        self.assertFalse(is_generic_fallback_for_label("Tandoori chicken + dal"))
        self.assertFalse(is_generic_fallback_for_label("Eggs on toast"))


class TestAuditCandidateDebug(unittest.TestCase):
    def test_candidate_debug_structure(self):
        from healthy_places_audit import build_candidate_debug, build_audit_result_row
        place = {
            "name": "Test",
            "top_menu_items": [
                {"item_name": "Tandoori chicken + dal", "estimated_calories": 580, "estimated_protein_g": 42,
                 "menu_item_source": "heuristic", "menu_item_confidence": 0.65},
                {"item_name": "Chicken tikka + salad", "estimated_calories": 520, "estimated_protein_g": 38,
                 "menu_item_source": "heuristic", "menu_item_confidence": 0.62},
            ],
        }
        debug = build_candidate_debug(place)
        self.assertIsInstance(debug, list)
        self.assertGreaterEqual(len(debug), 2)
        self.assertEqual(debug[0]["candidate_name"], "Tandoori chicken + dal")
        self.assertEqual(debug[0]["why_kept"], "selected_as_primary")
        self.assertEqual(debug[1]["why_kept"], "alternative")
        row = build_audit_result_row(place, 1, include_candidate_debug=True)
        self.assertIn("candidate_debug", row)
        self.assertEqual(len(row["candidate_debug"]), 2)


class TestSelectBestCandidate(unittest.TestCase):
    def test_select_best_prefers_protein_density_in_cut(self):
        candidates = [
            {"candidate_name": "Tandoori chicken + dal", "estimated_calories": 580, "estimated_protein_g": 42, "cut_friendly": True, "satiety_tags": ["high"], "negative_flags": []},
            {"candidate_name": "Butter chicken + naan", "estimated_calories": 720, "estimated_protein_g": 32, "cut_friendly": False, "satiety_tags": ["high"], "negative_flags": []},
        ]
        place = _place("Indian Restaurant")
        best, why = select_best_candidate(candidates, place, cut_mode=True)
        self.assertIsNotNone(best)
        self.assertEqual(best.get("candidate_name"), "Tandoori chicken + dal")


if __name__ == "__main__":
    unittest.main()

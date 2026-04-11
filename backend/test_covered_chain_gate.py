"""
Tests for covered-chain hard gate.
Verifies that recognized covered chains NEVER leak generic/heuristic fallback items.
Run: cd backend && python -m pytest test_covered_chain_gate.py -v
"""
import unittest

from ranked_place_builder import build_ranked_place_profile, _confidence_label


class TestCoveredChainGateRankedBuilder(unittest.TestCase):
    """Verify that build_ranked_place_profile enforces covered-chain neutral state."""

    def _base_place(self, **overrides):
        place = {
            "name": "Domino's Pizza Sydney Olympic Park",
            "recommended_order": "Grilled Chicken Salad Bowl",
            "best_order": "Grilled Chicken Salad Bowl",
            "estimated_calories": 520,
            "estimated_protein_g": 30,
            "menu_item_source": "heuristic",
            "menu_item_confidence": 0.5,
            "order_confidence": 0.5,
            "distance_meters": 500,
            "cuisine_hint": "pizza",
        }
        place.update(overrides)
        return place

    def _user_context(self, **overrides):
        ctx = {
            "remaining_protein_g": 40,
            "cut_mode": False,
            "goal": "maintain",
        }
        ctx.update(overrides)
        return ctx

    def test_covered_chain_exact_item_shows_chain_backed(self):
        """Covered chain with exact chain item => item shown, badge allowed."""
        place = self._base_place(
            recommended_order="Chicken Dominator (Medium, Thin Crust)",
            best_order="Chicken Dominator (Medium, Thin Crust)",
            menu_item_source="ingested_chain_item",
            menu_item_confidence=0.85,
            order_confidence=0.85,
            item_provenance="exact_chain_menu",
            can_show_verified_badge=True,
            covered_chain_key="dominos",
            covered_chain_neutral=False,
            chain_key="dominos",
        )
        result = build_ranked_place_profile(place, self._user_context())
        self.assertEqual(result["best_item_name"], "Chicken Dominator (Medium, Thin Crust)")
        self.assertTrue(result["can_show_verified_badge"])
        self.assertEqual(result["item_provenance"], "exact_chain_menu")
        self.assertFalse(result["covered_chain_neutral"])
        self.assertIn(result["confidence_label"], ["Verified", "Chain-backed"])

    def test_covered_chain_no_exact_item_neutral_state(self):
        """Covered chain with no exact item => empty best_item, no badge, neutral."""
        place = self._base_place(
            recommended_order="",
            best_order="",
            menu_item_source="heuristic",
            menu_item_confidence=0.4,
            item_provenance="none",
            can_show_verified_badge=False,
            covered_chain_key="dominos",
            covered_chain_neutral=True,
            chain_key="dominos",
        )
        result = build_ranked_place_profile(place, self._user_context())
        self.assertEqual(result["best_item_name"], "")
        self.assertFalse(result["can_show_verified_badge"])
        self.assertTrue(result["covered_chain_neutral"])
        self.assertEqual(result["confidence_label"], "Needs menu check")
        self.assertTrue(result["best_item_is_generic_fallback"])

    def test_uncovered_place_fallback_still_works(self):
        """Non-chain place with heuristic fallback => existing logic preserved."""
        place = self._base_place(
            name="Joe's Local Cafe",
            recommended_order="Egg + Chicken Plate",
            best_order="Egg + Chicken Plate",
            menu_item_source="heuristic",
            menu_item_confidence=0.55,
            order_confidence=0.55,
            # No covered_chain fields
        )
        result = build_ranked_place_profile(place, self._user_context())
        # Uncovered place should still show its item
        self.assertTrue(len(result["best_item_name"]) > 0)
        self.assertFalse(result.get("covered_chain_neutral", False))


class TestConfidenceLabelForChains(unittest.TestCase):
    """Ensure _confidence_label returns correct labels for chain sources."""

    def test_chain_registry_high_conf_verified(self):
        self.assertEqual(
            _confidence_label("ingested_chain_item", 0.85),
            "Verified",
        )

    def test_chain_registry_moderate_conf_chain_backed(self):
        self.assertEqual(
            _confidence_label("chain_registry", 0.65),
            "Chain-backed",
        )

    def test_heuristic_low_conf_needs_check(self):
        self.assertEqual(
            _confidence_label("heuristic", 0.42),
            "Needs menu check",
        )


if __name__ == "__main__":
    unittest.main()

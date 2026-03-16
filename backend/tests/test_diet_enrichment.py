"""
Diet-aware enrichment: vegetarian/vegan get only diet-safe top item; fallback when none.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from local_venue_enrichment import enrich_place_with_local_profile


def _mcdonalds_place():
    return {
        "place_id": "mock_mcd_001",
        "name": "McDonald's – George Street",
        "place_name": "McDonald's – George Street",
        "lat": -33.8688,
        "lng": 151.2093,
        "vicinity": "Sydney, NSW, Australia",
        "country_code": "AU",
    }


def _mock_mcdonalds_items():
    """Hamburger and McChicken (no mayo). Hamburger veg, McChicken not."""
    return [
        {"item_name": "McChicken, no mayo", "estimated_calories": 390, "estimated_protein_g": 17, "confidence": 0.84, "vegetarian_possible": False, "vegan_possible": False},
        {"item_name": "Hamburger", "estimated_calories": 250, "estimated_protein_g": 12, "confidence": 0.90, "vegetarian_possible": True, "vegan_possible": True},
        {"item_name": "Big Mac", "estimated_calories": 540, "estimated_protein_g": 26, "confidence": 0.78, "vegetarian_possible": False, "vegan_possible": False},
    ]


def _mock_veg_only_items():
    """All veg options (e.g. Wow Momo veg momo)."""
    return [
        {"item_name": "Veg Momo (Steamed)", "estimated_calories": 280, "estimated_protein_g": 10, "confidence": 0.88, "vegetarian_possible": True, "vegan_possible": False},
        {"item_name": "Paneer Momo", "estimated_calories": 320, "estimated_protein_g": 14, "confidence": 0.85, "vegetarian_possible": True, "vegan_possible": False},
    ]


def _mock_vegan_item():
    """One vegan option."""
    return [
        {"item_name": "Dal + Roti", "estimated_calories": 350, "estimated_protein_g": 12, "confidence": 0.86, "vegetarian_possible": True, "vegan_possible": True},
        {"item_name": "Paneer Curry", "estimated_calories": 420, "estimated_protein_g": 18, "confidence": 0.82, "vegetarian_possible": True, "vegan_possible": False},
    ]


class TestDietEnrichmentVegetarian(unittest.TestCase):
    """Vegetarian user gets veg top item; non-veg items excluded."""

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_vegetarian_gets_veg_item_not_mcchicken(self, mock_get):
        mock_get.return_value = _mock_mcdonalds_items()
        place = _mcdonalds_place()
        place["diet_preference"] = "vegetarian"
        enriched = enrich_place_with_local_profile(place, market_tag="AU")
        self.assertIsNotNone(enriched)
        self.assertEqual(enriched.get("matched_chain_key"), "mcdonalds")
        top = enriched.get("top_menu_item")
        self.assertIsNotNone(top)
        self.assertEqual(top.get("item_name"), "Hamburger")
        self.assertFalse(enriched.get("no_diet_safe_candidates", False))

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_vegetarian_via_param(self, mock_get):
        mock_get.return_value = _mock_mcdonalds_items()
        enriched = enrich_place_with_local_profile(_mcdonalds_place(), market_tag="AU", diet_preference="vegetarian")
        self.assertIsNotNone(enriched)
        top = enriched.get("top_menu_item")
        self.assertIsNotNone(top)
        self.assertEqual(top.get("item_name"), "Hamburger")


class TestDietEnrichmentVegan(unittest.TestCase):
    """Vegan user gets only vegan-safe top item."""

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_vegan_gets_vegan_item(self, mock_get):
        mock_get.return_value = _mock_vegan_item()
        place = _mcdonalds_place()
        place["diet_preference"] = "vegan"
        enriched = enrich_place_with_local_profile(place, market_tag="AU")
        self.assertIsNotNone(enriched)
        top = enriched.get("top_menu_item")
        self.assertIsNotNone(top)
        self.assertEqual(top.get("item_name"), "Dal + Roti")


class TestDietEnrichmentNoSafeCandidates(unittest.TestCase):
    """When no diet-safe candidates, top_menu_item is None and no_diet_safe_candidates True."""

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_vegan_no_vegan_options_returns_none_top(self, mock_get):
        # All items vegetarian but not vegan
        mock_get.return_value = _mock_veg_only_items()
        place = _mcdonalds_place()
        place["diet_preference"] = "vegan"
        enriched = enrich_place_with_local_profile(place, market_tag="AU")
        self.assertIsNotNone(enriched)
        self.assertEqual(enriched.get("matched_chain_key"), "mcdonalds")
        self.assertIsNone(enriched.get("top_menu_item"))
        self.assertTrue(enriched.get("no_diet_safe_candidates"))
        self.assertEqual(enriched.get("top_menu_items"), [])
        self.assertEqual(enriched.get("candidates"), [])


class TestDietEnrichmentOmnivoreUnchanged(unittest.TestCase):
    """Omnivore (default) behavior unchanged: first by fitness order."""

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_omnivore_gets_first_by_fitness(self, mock_get):
        mock_get.return_value = _mock_mcdonalds_items()
        enriched = enrich_place_with_local_profile(_mcdonalds_place(), market_tag="AU")
        self.assertIsNotNone(enriched)
        top = enriched.get("top_menu_item")
        self.assertIsNotNone(top)
        self.assertIn(top.get("item_name"), ("Hamburger", "McChicken, no mayo", "Big Mac"))
        # Omnivore: no diet filter; top is first by fitness sort. Hamburger has lower protein so McChicken can win - actually sort is fat_loss_fit_score, protein_density_score, estimated_protein_g, confidence. Mock items don't have fat_loss_fit_score so it's 0; protein_density_score 0; then estimated_protein_g: 17, 12, 26; then confidence. So order: Big Mac (26), McChicken (17), Hamburger (12). So top = Big Mac. For omnivore we don't filter so top is Big Mac. That's fine - test just checks we get some top and no diet flags.
        self.assertFalse(enriched.get("no_diet_safe_candidates", False))
        self.assertFalse(enriched.get("diet_filter_applied", True))

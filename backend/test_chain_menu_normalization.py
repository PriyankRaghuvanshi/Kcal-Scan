"""
Tests for chain menu normalization.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from chain_menu_normalization import (
    normalize_raw_item,
    to_registry_menu_item,
    TIER_EXACT_MENU_MATCH,
    SOURCE_INGESTED_CHAIN_ITEM,
)


class TestNormalizeRawItem(unittest.TestCase):
    def test_normalizes_basic_item(self):
        raw = {
            "item_name": "6\" Grilled Chicken Sub",
            "category": "sub",
            "estimated_calories": 370,
            "estimated_protein_g": 32,
            "menu_item_confidence": 0.93,
        }
        out = normalize_raw_item(raw, chain_key="subway", market_tag="AU")
        self.assertEqual(out.get("item_name"), "6\" Grilled Chicken Sub")
        self.assertEqual(out.get("chain_key"), "subway")
        self.assertEqual(out.get("market_tag"), "AU")
        self.assertEqual(out.get("estimated_calories"), 370)
        self.assertEqual(out.get("chosen_candidate_specificity_tier"), TIER_EXACT_MENU_MATCH)
        self.assertEqual(out.get("menu_item_source"), SOURCE_INGESTED_CHAIN_ITEM)

    def test_requires_item_name(self):
        out = normalize_raw_item({"category": "sub"}, chain_key="subway")
        self.assertEqual(out, {})

    def test_generates_item_key(self):
        raw = {"item_name": "McChicken"}
        out = normalize_raw_item(raw, chain_key="mcdonalds")
        self.assertTrue("item_key" in out)
        self.assertIn("mcdonalds", out["item_key"])


class TestToRegistryMenuItem(unittest.TestCase):
    def test_converts_to_registry_format(self):
        ingested = {
            "item_name": "6\" Turkey Sub",
            "category": "sub",
            "estimated_calories": 350,
            "estimated_protein_g": 26,
            "confidence": 0.91,
            "source_url": "https://subway.com/menu",
        }
        reg = to_registry_menu_item(ingested)
        self.assertEqual(reg["item_name"], "6\" Turkey Sub")
        self.assertEqual(reg["menu_item_source"], SOURCE_INGESTED_CHAIN_ITEM)
        self.assertEqual(reg["chosen_candidate_specificity_tier"], TIER_EXACT_MENU_MATCH)

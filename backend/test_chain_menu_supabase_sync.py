"""
Tests for chain menu Supabase sync and get_chain_menu_items / list_chain_menu_chain_keys.
Uses unittest and mocking; no real Supabase required.
"""
import unittest
from unittest.mock import patch, MagicMock

from chain_menu_supabase_sync import sync_chain_menu_to_supabase
from supabase_intelligence_store import (
    get_chain_menu_items,
    list_chain_menu_chain_keys,
    TBL_CHAIN_MENU_ITEMS,
    TBL_CHAIN_MENU_PROFILES,
)


# Minimal seed-shaped data for Chipotle US and Faasos IN (rollout chains)
CHIPOTLE_US_SEED = {
    "chain_key": "chipotle",
    "market_tag": "US",
    "brand_name": "Chipotle Mexican Grill",
    "source_type": "seed_ingestion",
    "source_url": "https://www.chipotle.com/nutrition",
    "store_name_variants": ["chipotle", "chipotle mexican grill"],
    "items": [
        {
            "item_key": "chipotle_high_protein_bowl",
            "item_name": "High Protein Bowl",
            "category": "bowl",
            "estimated_calories": 820,
            "estimated_protein_g": 60,
            "estimated_carbs_g": 55,
            "estimated_fat_g": 35,
            "vegetarian_possible": False,
            "vegan_possible": False,
            "confidence": 0.82,
            "negative_flags": [],
            "menu_item_source": "seed_estimated",
        },
        {
            "item_key": "chipotle_chicken_burrito_bowl",
            "item_name": "Chicken Burrito Bowl",
            "category": "bowl",
            "estimated_calories": 650,
            "estimated_protein_g": 42,
            "estimated_carbs_g": 60,
            "estimated_fat_g": 22,
            "vegetarian_possible": False,
            "vegan_possible": False,
            "confidence": 0.8,
            "negative_flags": [],
            "menu_item_source": "seed_estimated",
        },
    ],
}

FAASOS_IN_SEED = {
    "chain_key": "faasos",
    "market_tag": "IN",
    "brand_name": "Faasos",
    "source_type": "seed_ingestion",
    "source_url": "https://www.eatsure.com/faasos",
    "store_name_variants": ["faasos", "faasos wraps"],
    "items": [
        {
            "item_key": "faasos_high_protein_chicken_wrap",
            "item_name": "High Protein Chicken Wrap",
            "category": "wrap",
            "estimated_calories": 520,
            "estimated_protein_g": 35,
            "estimated_carbs_g": 40,
            "estimated_fat_g": 20,
            "vegetarian_possible": False,
            "vegan_possible": False,
            "confidence": 0.76,
            "negative_flags": [],
            "menu_item_source": "seed_estimated",
        },
    ],
}


class TestSyncChipotleUs(unittest.TestCase):
    """Sync creates profile and items correctly for Chipotle US."""

    @patch("supabase_intelligence_store.upsert_chain_menu_items")
    @patch("supabase_intelligence_store.upsert_chain_menu_profile")
    def test_sync_chipotle_us_creates_profile_and_items(
        self, mock_upsert_profile, mock_upsert_items
    ):
        mock_upsert_profile.return_value = {"chain_key": "chipotle", "market_tag": "US"}
        mock_upsert_items.return_value = len(CHIPOTLE_US_SEED["items"])

        result = sync_chain_menu_to_supabase(
            "chipotle", "US", load_seed=lambda k, m: CHIPOTLE_US_SEED
        )

        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("item_count"), len(CHIPOTLE_US_SEED["items"]))
        self.assertEqual(mock_upsert_profile.call_count, 1)
        self.assertEqual(mock_upsert_items.call_count, 1)
        profile_call = mock_upsert_profile.call_args[0][0]
        self.assertEqual(profile_call.get("chain_key"), "chipotle")
        self.assertEqual(profile_call.get("market_tag"), "US")
        items_call = mock_upsert_items.call_args[0]
        self.assertEqual(items_call[0], "chipotle")
        self.assertEqual(items_call[1], "US")
        self.assertEqual(len(items_call[2]), len(CHIPOTLE_US_SEED["items"]))


class TestSyncFaasosIn(unittest.TestCase):
    """Sync creates profile and items correctly for Faasos IN."""

    @patch("supabase_intelligence_store.upsert_chain_menu_items")
    @patch("supabase_intelligence_store.upsert_chain_menu_profile")
    def test_sync_faasos_in_creates_profile_and_items(
        self, mock_upsert_profile, mock_upsert_items
    ):
        mock_upsert_profile.return_value = {"chain_key": "faasos", "market_tag": "IN"}
        mock_upsert_items.return_value = len(FAASOS_IN_SEED["items"])

        result = sync_chain_menu_to_supabase(
            "faasos", "IN", load_seed=lambda k, m: FAASOS_IN_SEED
        )

        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("item_count"), len(FAASOS_IN_SEED["items"]))
        self.assertEqual(mock_upsert_profile.call_count, 1)
        self.assertEqual(mock_upsert_items.call_count, 1)
        profile_call = mock_upsert_profile.call_args[0][0]
        self.assertEqual(profile_call.get("chain_key"), "faasos")
        self.assertEqual(profile_call.get("market_tag"), "IN")


class TestSyncIdempotent(unittest.TestCase):
    """Sync rerun has consistent shape and no duplicate-intent behavior."""

    @patch("supabase_intelligence_store.upsert_chain_menu_items")
    @patch("supabase_intelligence_store.upsert_chain_menu_profile")
    def test_sync_chipotle_us_idempotent_shape(
        self, mock_upsert_profile, mock_upsert_items
    ):
        mock_upsert_profile.return_value = {}
        mock_upsert_items.return_value = len(CHIPOTLE_US_SEED["items"])

        result1 = sync_chain_menu_to_supabase(
            "chipotle", "US", load_seed=lambda k, m: CHIPOTLE_US_SEED
        )
        result2 = sync_chain_menu_to_supabase(
            "chipotle", "US", load_seed=lambda k, m: CHIPOTLE_US_SEED
        )

        self.assertIn("ok", result1)
        self.assertIn("item_count", result1)
        self.assertIn("ok", result2)
        self.assertIn("item_count", result2)
        self.assertEqual(result1["ok"], result2["ok"])
        self.assertEqual(result1["item_count"], result2["item_count"])
        self.assertEqual(mock_upsert_profile.call_count, 2)
        self.assertEqual(mock_upsert_items.call_count, 2)
        self.assertEqual(result1["item_count"], len(CHIPOTLE_US_SEED["items"]))


class TestGetChainMenuItemsExactMarket(unittest.TestCase):
    """Exact market results are returned when Supabase has them."""

    @patch("supabase_intelligence_store._sb_safe_get_many")
    @patch("supabase_intelligence_store._supabase_available")
    def test_get_chain_menu_items_exact_market_first(
        self, mock_supabase_available, mock_get_many
    ):
        mock_supabase_available.return_value = True
        us_items = [
            {"chain_key": "chipotle", "market_tag": "US", "item_key": "chipotle_bowl", "item_name": "Bowl"},
        ]
        mock_get_many.return_value = us_items

        out = get_chain_menu_items("chipotle", "US")

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].get("market_tag"), "US")
        self.assertEqual(out[0].get("item_key"), "chipotle_bowl")
        mock_get_many.assert_called()
        call_kwargs = mock_get_many.call_args[0]
        self.assertEqual(call_kwargs[0], TBL_CHAIN_MENU_ITEMS)
        self.assertIn("eq.chipotle", str(call_kwargs[1]))
        self.assertIn("eq.US", str(call_kwargs[1]))


class TestGetChainMenuItemsNoLeakage(unittest.TestCase):
    """Wrong market returns empty; no US data leaks into IN request."""

    @patch("chain_menu_ingestion.get_chain_items")
    @patch("supabase_intelligence_store._sb_safe_get_many")
    @patch("supabase_intelligence_store._supabase_available")
    def test_get_chain_menu_items_wrong_market_no_leakage(
        self, mock_supabase_available, mock_get_many, mock_get_chain_items
    ):
        mock_supabase_available.return_value = True
        mock_get_many.return_value = []
        mock_get_chain_items.return_value = []

        out = get_chain_menu_items("chipotle", "IN")

        self.assertEqual(out, [])
        calls = mock_get_many.call_args_list
        for c in calls:
            params = c[0][1]
            if "eq.IN" in str(params):
                self.assertNotIn("eq.US", str(params.get("market_tag", "")))


class TestGetChainMenuItemsFallback(unittest.TestCase):
    """Fallback to file store when Supabase returns empty."""

    @patch("chain_menu_ingestion.get_chain_items")
    @patch("supabase_intelligence_store._sb_safe_get_many")
    def test_get_chain_menu_items_falls_back_to_file_store_when_supabase_empty(
        self, mock_sb_get_many, mock_get_chain_items
    ):
        mock_sb_get_many.return_value = []
        file_items = [
            {"item_key": "chipotle_bowl", "item_name": "Bowl", "estimated_calories": 600},
        ]
        mock_get_chain_items.return_value = file_items

        out = get_chain_menu_items("chipotle", "US")

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].get("item_name"), "Bowl")
        mock_get_chain_items.assert_called_once_with("chipotle", "US")


class TestGetChainMenuItemsFailOpen(unittest.TestCase):
    """On error, get_chain_menu_items returns [] and does not raise."""

    @patch("chain_menu_ingestion.get_chain_items")
    @patch("supabase_intelligence_store._sb_safe_get_many")
    def test_get_chain_menu_items_fail_open_on_error(
        self, mock_sb_get_many, mock_get_chain_items
    ):
        mock_sb_get_many.side_effect = Exception("network error")
        mock_get_chain_items.side_effect = Exception("file store error")

        out = get_chain_menu_items("chipotle", "US")

        self.assertEqual(out, [])


class TestListChainMenuChainKeys(unittest.TestCase):
    """list_chain_menu_chain_keys returns sorted unique keys from profile rows."""

    @patch("supabase_intelligence_store._sb_safe_get_many")
    @patch("supabase_intelligence_store._supabase_available")
    def test_list_chain_menu_chain_keys_returns_sorted_unique_keys(
        self, mock_supabase_available, mock_get_many
    ):
        mock_supabase_available.return_value = True
        mock_get_many.return_value = [
            {"chain_key": "faasos"},
            {"chain_key": "chipotle"},
            {"chain_key": "chipotle"},
        ]

        out = list_chain_menu_chain_keys()

        self.assertEqual(out, ["chipotle", "faasos"])
        mock_get_many.assert_called_once()
        self.assertEqual(mock_get_many.call_args[0][0], TBL_CHAIN_MENU_PROFILES)


if __name__ == "__main__":
    unittest.main()

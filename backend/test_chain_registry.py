import json
import os
import tempfile
import unittest

from chain_registry import (
    clear_chain_registry_cache,
    merge_user_chain_records,
    merge_user_franchise_list,
    resolve_chain_identity,
)


class ChainRegistryTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._old_registry = os.environ.get("GLOBAL_CHAIN_REGISTRY_PATH")
        seed = {
            "version": "v1",
            "chains": [
                {
                    "chain_id": "mcdonalds_global",
                    "canonical_name": "McDonald's",
                    "aliases": ["McDonald's", "McDonalds", "McCafe"],
                    "country_codes": ["GLOBAL", "AU", "US"],
                    "brand_family": "mcdonalds",
                    "known_variants": ["McCafe"],
                    "official_website_domains": ["mcdonalds.com"],
                },
                {
                    "chain_id": "hungry_jacks_au",
                    "canonical_name": "Hungry Jack's",
                    "aliases": ["Hungry Jack's", "Hungry Jacks", "HJ", "Burger King"],
                    "country_codes": ["AU"],
                    "brand_family": "hungry_jacks",
                    "known_variants": ["Hungry Jacks"],
                    "official_website_domains": ["hungryjacks.com.au"],
                },
                {
                    "chain_id": "burger_king_global",
                    "canonical_name": "Burger King",
                    "aliases": ["Burger King", "BK"],
                    "country_codes": ["GLOBAL", "US"],
                    "brand_family": "burger_king",
                    "known_variants": ["BurgerKing"],
                    "official_website_domains": ["bk.com"],
                },
            ],
        }
        self._registry_path = os.path.join(self._tmp_dir.name, "global_chain_registry.json")
        with open(self._registry_path, "w", encoding="utf-8") as handle:
            json.dump(seed, handle)
        os.environ["GLOBAL_CHAIN_REGISTRY_PATH"] = self._registry_path
        clear_chain_registry_cache()

    def tearDown(self):
        if self._old_registry is None:
            os.environ.pop("GLOBAL_CHAIN_REGISTRY_PATH", None)
        else:
            os.environ["GLOBAL_CHAIN_REGISTRY_PATH"] = self._old_registry
        clear_chain_registry_cache()
        self._tmp_dir.cleanup()

    def test_mcdonalds_variants_resolve(self):
        one = resolve_chain_identity(place_name="McDonalds - Parramatta", country_code="AU")
        two = resolve_chain_identity(place_name="McCafe Parramatta", country_code="AU")
        self.assertTrue(one.get("matched"))
        self.assertTrue(two.get("matched"))
        self.assertEqual(one.get("chain_id"), "mcdonalds_global")
        self.assertEqual(two.get("chain_id"), "mcdonalds_global")

    def test_country_aware_burger_king_vs_hungry_jacks(self):
        au = resolve_chain_identity(place_name="Burger King Parramatta", country_code="AU")
        us = resolve_chain_identity(place_name="Burger King Downtown", country_code="US")
        self.assertTrue(au.get("matched"))
        self.assertTrue(us.get("matched"))
        self.assertEqual(au.get("chain_id"), "hungry_jacks_au")
        self.assertEqual(us.get("chain_id"), "burger_king_global")

    def test_non_chain_venue_does_not_match(self):
        out = resolve_chain_identity(place_name="Neighborhood Local Dhaba", country_code="AU")
        self.assertFalse(out.get("matched"))

    def test_user_franchise_merge_adds_and_dedupes(self):
        result = merge_user_franchise_list(
            ["McDonald's", "Subway", "Subway", "Nando's"],
            country_code="AU",
            persist=True,
        )
        summary = result.get("summary") or {}
        self.assertGreaterEqual(int(summary.get("added_chains", 0)), 2)
        self.assertGreaterEqual(int(summary.get("skipped", 0)), 1)

        with open(self._registry_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        chains = payload.get("chains") if isinstance(payload.get("chains"), list) else []
        ids = {str(row.get("chain_id") or "") for row in chains if isinstance(row, dict)}
        self.assertIn("subway_au", ids)
        self.assertIn("nandos_au", ids)

    def test_chain_record_merge_supports_country_aware_seed_payload(self):
        payload = [
            {
                "canonical_name": "Burger King",
                "country_codes": ["US", "GB"],
                "aliases": ["burger king", "bk"],
                "brand_family": "burger_king_family",
                "priority_tier": 1,
                "notes": "Global Burger King identity",
            },
            {
                "canonical_name": "Hungry Jack's",
                "country_codes": ["AU"],
                "aliases": ["hungry jacks", "hj", "burger king"],
                "brand_family": "burger_king_family",
                "priority_tier": 1,
                "notes": "Australian equivalent",
            },
        ]
        result = merge_user_chain_records(payload, default_country_code="GLOBAL", persist=True)
        summary = result.get("summary") or {}
        self.assertEqual(int(summary.get("input_count", 0)), 2)

        au = resolve_chain_identity(place_name="Burger King Parramatta", country_code="AU")
        us = resolve_chain_identity(place_name="Burger King Downtown", country_code="US")
        self.assertTrue(au.get("matched"))
        self.assertTrue(us.get("matched"))
        self.assertIn(au.get("chain_id"), {"hungry_jacks_au", "burger_king_global"})
        self.assertEqual(us.get("chain_id"), "burger_king_global")


if __name__ == "__main__":
    unittest.main()

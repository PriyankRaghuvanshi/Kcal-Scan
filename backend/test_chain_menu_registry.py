import unittest

from chain_menu_registry import resolve_chain_menu_for_place


class ChainMenuRegistryTests(unittest.TestCase):
    def test_resolves_subway_au_match_with_location_suffix(self):
        bundle = resolve_chain_menu_for_place(
            {
                "name": "Subway Wentworthville",
                "address": "Wentworthville NSW Australia",
                "country_code": "AU",
            },
            country_code="AU",
            max_items=5,
        )
        self.assertTrue(bundle.get("chain_match"))
        self.assertEqual(bundle.get("chain_key"), "subway")
        self.assertGreaterEqual(len(bundle.get("menu_items") or []), 2)
        self.assertIn(bundle.get("menu_source"), ("website_menu", "chain_menu_ingestion"))
        self.assertTrue(str(bundle.get("matched_alias") or "").strip())
        self.assertIn(bundle.get("chain_source_used"), ("country_chain_registry", "ingested_chain_item"))

    def test_resolves_hungry_jacks_apostrophe_variants(self):
        with_apostrophe = resolve_chain_menu_for_place(
            {
                "name": "Hungry Jack's Wentworthville",
                "address": "Wentworthville NSW Australia",
                "country_code": "AU",
            },
            country_code="AU",
            max_items=4,
        )
        without_apostrophe = resolve_chain_menu_for_place(
            {
                "name": "Hungry Jacks",
                "address": "Parramatta NSW Australia",
                "country_code": "AU",
            },
            country_code="AU",
            max_items=4,
        )
        self.assertTrue(with_apostrophe.get("chain_match"))
        self.assertTrue(without_apostrophe.get("chain_match"))
        self.assertEqual(with_apostrophe.get("chain_key"), "hungry_jacks")
        self.assertEqual(without_apostrophe.get("chain_key"), "hungry_jacks")

    def test_resolves_mcdonalds_and_mccafe_aliases(self):
        mcd = resolve_chain_menu_for_place(
            {
                "name": "McDonald's - Parramatta",
                "address": "Parramatta NSW Australia",
            },
            country_code="AU",
            max_items=4,
        )
        bundle = resolve_chain_menu_for_place(
            {
                "name": "McCafe Parramatta",
                "address": "Parramatta NSW Australia",
            },
            country_code="AU",
            max_items=4,
        )
        self.assertTrue(mcd.get("chain_match"))
        self.assertEqual(mcd.get("chain_key"), "mcdonalds")
        self.assertTrue(bundle.get("chain_match"))
        self.assertEqual(bundle.get("chain_key"), "mcdonalds")

    def test_resolves_nandos_and_grilld_variants(self):
        nandos = resolve_chain_menu_for_place(
            {
                "name": "Nando's Blacktown",
                "address": "Blacktown NSW Australia",
            },
            country_code="AU",
            max_items=4,
        )
        grilld = resolve_chain_menu_for_place(
            {
                "name": "Grilld Parramatta",
                "address": "Parramatta NSW Australia",
            },
            country_code="AU",
            max_items=4,
        )
        self.assertTrue(nandos.get("chain_match"))
        self.assertEqual(nandos.get("chain_key"), "nandos")
        self.assertTrue(grilld.get("chain_match"))
        self.assertEqual(grilld.get("chain_key"), "grilld")

    def test_burger_king_maps_country_aware(self):
        au = resolve_chain_menu_for_place(
            {
                "name": "Burger King Parramatta",
                "address": "Parramatta NSW Australia",
                "country_code": "AU",
            },
            country_code="AU",
            max_items=4,
        )
        us = resolve_chain_menu_for_place(
            {
                "name": "Burger King Downtown",
                "address": "New York, United States",
                "country_code": "US",
            },
            country_code="US",
            max_items=4,
        )
        self.assertTrue(au.get("chain_match"))
        self.assertEqual(au.get("chain_key"), "hungry_jacks")
        self.assertIn(au.get("chain_source_used"), ("country_chain_registry", "ingested_chain_item"))
        self.assertTrue(us.get("chain_match"))
        self.assertEqual(us.get("chain_key"), "burger_king")
        self.assertIn(us.get("chain_source_used"), {"country_chain_registry", "global_chain_registry", "ingested_chain_item"})

    def test_global_fallback_when_country_variant_missing(self):
        bundle = resolve_chain_menu_for_place(
            {
                "name": "Subway Downtown",
                "address": "New York, United States",
            },
            country_code="US",
            max_items=4,
        )
        self.assertTrue(bundle.get("chain_match"))
        self.assertIn(bundle.get("country_code"), {"GLOBAL", "US"})
        self.assertGreaterEqual(len(bundle.get("menu_items") or []), 1)

    def test_non_chain_venues_are_not_falsely_matched(self):
        indian = resolve_chain_menu_for_place(
            {
                "name": "Neighborhood Local Dhaba",
                "address": "Wentworthville NSW Australia",
            },
            country_code="AU",
            max_items=4,
        )
        cafe = resolve_chain_menu_for_place(
            {
                "name": "Blue Bean Cafe - Parramatta",
                "address": "Parramatta NSW Australia",
            },
            country_code="AU",
            max_items=4,
        )
        unknown = resolve_chain_menu_for_place(
            {
                "name": "Sunset Family Restaurant",
                "address": "Sydney NSW Australia",
            },
            country_code="AU",
            max_items=4,
        )
        self.assertEqual(indian, {})
        self.assertEqual(cafe, {})
        self.assertEqual(unknown, {})


if __name__ == "__main__":
    unittest.main()

import unittest

from chain_menu_registry import (
    _infer_country_code,
    _infer_country_from_latlng,
    resolve_chain_menu_for_place,
)


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

    def test_latlng_country_inference(self):
        self.assertEqual(_infer_country_from_latlng(37.77, -122.41), "US")  # San Francisco
        self.assertEqual(_infer_country_from_latlng(-33.87, 151.21), "AU")  # Sydney
        self.assertEqual(_infer_country_from_latlng(19.08, 72.88), "IN")    # Mumbai
        self.assertEqual(_infer_country_from_latlng(51.50, -0.12), "GB")    # London
        self.assertEqual(_infer_country_from_latlng(-36.85, 174.76), "NZ")  # Auckland
        self.assertEqual(_infer_country_from_latlng(None, None), "")
        self.assertEqual(_infer_country_from_latlng(0.0, 0.0), "")

    def test_no_country_does_not_silently_default_to_au(self):
        # Previously DEFAULT_COUNTRY_CODE="AU" silently routed all unknown-country
        # places to AU menus. Chipotle has no AU entry, so Chipotle requests without
        # explicit country but with US coords must now resolve via lat/lng, not AU.
        bundle = resolve_chain_menu_for_place(
            {"name": "Chipotle Mexican Grill", "lat": 37.77, "lng": -122.41},
            max_items=4,
        )
        self.assertTrue(bundle.get("chain_match"))
        self.assertEqual(bundle.get("chain_key"), "chipotle")
        self.assertEqual(bundle.get("country_code"), "US")

    def test_burger_king_us_resolves_via_latlng_not_hungry_jacks(self):
        # Prior bug: missing country_code + AU default → Burger King US coords
        # resolved as hungry_jacks (AU alias). After fix, lat/lng → US → burger_king.
        bundle = resolve_chain_menu_for_place(
            {"name": "Burger King", "lat": 40.71, "lng": -74.00},
            max_items=4,
        )
        self.assertTrue(bundle.get("chain_match"))
        self.assertEqual(bundle.get("chain_key"), "burger_king")
        self.assertNotEqual(bundle.get("chain_key"), "hungry_jacks")

    def test_covered_us_chains_resolve_from_latlng_only(self):
        # Smoke test for all US-only chains: with only name + SF coords, each should
        # return a real chain match. Locks in the end-to-end flow for the
        # "no address, no country_code" path common in test/dev.
        us_chains = [
            ("Chipotle Mexican Grill", "chipotle"),
            ("Taco Bell", "taco_bell"),
            ("Wendy's", "wendys"),
            ("Panera Bread", "panera"),
            ("Chick-fil-A", "chick_fil_a"),
            ("Cava", "cava"),
            ("Sweetgreen", "sweetgreen"),
        ]
        for name, expected_key in us_chains:
            with self.subTest(name=name):
                bundle = resolve_chain_menu_for_place(
                    {"name": name, "lat": 37.77, "lng": -122.41},
                    max_items=4,
                )
                self.assertTrue(bundle.get("chain_match"), f"{name} should match")
                self.assertEqual(bundle.get("chain_key"), expected_key)
                self.assertGreaterEqual(len(bundle.get("menu_items") or []), 1)


if __name__ == "__main__":
    unittest.main()

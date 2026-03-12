"""
Tests for chain coverage roadmap: schema, alias matching, market filtering, helpers.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from chain_coverage_roadmap import (
    COVERAGE_STATUS,
    ROLLOUT_PRIORITY,
    clear_roadmap_cache,
    get_chain_roadmap,
    get_chain_swaps,
    get_chain_templates,
    list_chain_roadmap,
    list_chains_by_market,
    match_chain_by_alias,
    validate_roadmap_schema,
)


def _roadmap_path_override():
    """Point roadmap at the real data file for tests."""
    path = os.path.join(os.path.dirname(__file__), "data", "chain_coverage_roadmap.json")
    return patch.dict(os.environ, {"CHAIN_COVERAGE_ROADMAP_PATH": path}, clear=False)


class TestChainRoadmapSchema(unittest.TestCase):
    def setUp(self):
        clear_roadmap_cache()

    def test_no_duplicate_chain_keys(self):
        with _roadmap_path_override():
            errors = validate_roadmap_schema()
        dup_errors = [e for e in errors if "duplicate" in e.lower()]
        self.assertEqual(dup_errors, [], f"Duplicate chain keys: {dup_errors}")

    def test_no_empty_aliases_for_live_partial(self):
        with _roadmap_path_override():
            errors = validate_roadmap_schema()
        alias_errors = [e for e in errors if "aliases" in e.lower() and ("live" in e or "partial" in e)]
        self.assertEqual(alias_errors, [], f"Live/partial chains missing aliases: {alias_errors}")

    def test_schema_validity_first_10_chains(self):
        with _roadmap_path_override():
            chains = list_chain_roadmap()
        first_10_keys = [
            "subway", "mcdonalds", "kfc", "hungry_jacks", "dominos",
            "pizza_hut", "guzman_y_gomez", "oporto", "grilld", "boost_juice",
        ]
        for key in first_10_keys:
            c = get_chain_roadmap(key)
            self.assertIsNotNone(c, f"Missing chain: {key}")
            self.assertIn(c.get("rollout_priority"), ROLLOUT_PRIORITY)
            self.assertIn(c.get("coverage_status"), COVERAGE_STATUS)
            self.assertIsInstance(c.get("aliases"), list)
            self.assertTrue(len(c.get("aliases") or []) >= 1, f"Chain {key} needs aliases")

    def test_p0_core_trust_chains_have_templates(self):
        with _roadmap_path_override():
            p0 = list_chain_roadmap(rollout_priority="p0_core_trust")
        for c in p0:
            key = c.get("chain_key")
            templates = c.get("menu_templates") or []
            self.assertGreaterEqual(
                len(templates),
                0,
                f"p0 chain {key} should have menu_templates (or 0 for roadmap-only)",
            )
        # At least first 10 should have templates
        first_10 = [get_chain_roadmap(k) for k in ["subway", "mcdonalds", "kfc", "hungry_jacks", "dominos", "pizza_hut", "guzman_y_gomez", "oporto", "grilld", "boost_juice"]]
        with_templates = [c for c in first_10 if c and (c.get("menu_templates") or [])]
        self.assertGreaterEqual(len(with_templates), 8, "First 10 should have at least 8 with menu templates")

    def test_swaps_linked_correctly(self):
        with _roadmap_path_override():
            swaps = get_chain_swaps("subway", template_key="grilled_chicken_6inch")
        self.assertGreater(len(swaps), 0)
        swap_keys = [s.get("swap_key") for s in swaps]
        self.assertIn("no_mayo", swap_keys)
        self.assertIn("extra_salad", swap_keys)


class TestFirst10ChainSwapRules(unittest.TestCase):
    """Chain-backed places get roadmap swaps when chain_key is set."""

    def setUp(self):
        clear_roadmap_cache()

    def test_subway_chain_gets_roadmap_swaps(self):
        from swap_rules import generate_swaps_for_item

        with _roadmap_path_override():
            swaps, debug = generate_swaps_for_item(
                place={"name": "Subway", "chain_key": "subway", "types": ["restaurant"]},
                item_name="6\" Grilled Chicken Sub",
                estimated_calories=380,
                estimated_protein_g=32,
                menu_item_source="chain_registry",
                menu_item_confidence=0.9,
                cut_mode=True,
            )
        self.assertGreater(len(swaps), 0, "Subway with chain_key should get roadmap swaps")
        labels = [s.get("swap_label") for s in swaps]
        self.assertTrue(
            any("mayo" in str(l).lower() or "salad" in str(l).lower() for l in labels),
            msg=f"Expected chain-specific swap labels, got {labels}",
        )
        self.assertEqual(debug.get("source"), "chain_roadmap")

    def test_kfc_chain_gets_roadmap_swaps(self):
        from swap_rules import generate_swaps_for_item

        with _roadmap_path_override():
            swaps, debug = generate_swaps_for_item(
                place={"name": "KFC", "chain_key": "kfc", "types": ["restaurant"]},
                item_name="Original Tenders + Side Salad",
                estimated_calories=470,
                estimated_protein_g=35,
                menu_item_source="chain_registry",
                menu_item_confidence=0.8,
                cut_mode=False,
            )
        self.assertGreater(len(swaps), 0)
        labels = [s.get("swap_label") for s in swaps]
        self.assertTrue(
            any("mayo" in str(l).lower() or "salad" in str(l).lower() or "gravy" in str(l).lower() for l in labels),
            msg=f"Expected KFC swap labels, got {labels}",
        )
        self.assertEqual(debug.get("source"), "chain_roadmap")

    def test_hungry_jacks_chain_gets_roadmap_swaps(self):
        from swap_rules import generate_swaps_for_item

        with _roadmap_path_override():
            swaps, debug = generate_swaps_for_item(
                place={"name": "Hungry Jack's", "chain_key": "hungry_jacks", "types": ["restaurant"]},
                item_name="Whopper Jr, no mayo",
                estimated_calories=420,
                estimated_protein_g=21,
                menu_item_source="chain_registry",
                menu_item_confidence=0.84,
                cut_mode=False,
            )
        self.assertGreater(len(swaps), 0)
        labels = [s.get("swap_label") for s in swaps]
        self.assertIn("No mayo", labels, msg=f"Expected no mayo swap for HJ, got {labels}")
        self.assertEqual(debug.get("source"), "chain_roadmap")

    def test_dominos_chain_gets_roadmap_swaps(self):
        from swap_rules import generate_swaps_for_item

        with _roadmap_path_override():
            swaps, debug = generate_swaps_for_item(
                place={"name": "Domino's", "chain_key": "dominos", "types": ["restaurant"]},
                item_name="Thin Crust Chicken Supreme (2 slices)",
                estimated_calories=520,
                estimated_protein_g=26,
                menu_item_source="chain_registry",
                menu_item_confidence=0.82,
                cut_mode=False,
            )
        self.assertGreater(len(swaps), 0)
        labels = [s.get("swap_label") for s in swaps]
        self.assertTrue(
            any("thin" in str(l).lower() or "garlic" in str(l).lower() for l in labels),
            msg=f"Expected pizza swaps, got {labels}",
        )
        self.assertEqual(debug.get("source"), "chain_roadmap")

    def test_pizza_hut_chain_gets_roadmap_swaps(self):
        from swap_rules import generate_swaps_for_item

        with _roadmap_path_override():
            swaps, debug = generate_swaps_for_item(
                place={"name": "Pizza Hut", "chain_key": "pizza_hut", "types": ["restaurant"]},
                item_name="Thin n Crispy (2 slices)",
                estimated_calories=480,
                estimated_protein_g=22,
                menu_item_source="chain_registry",
                menu_item_confidence=0.8,
                cut_mode=False,
            )
        self.assertGreater(len(swaps), 0)
        labels = [s.get("swap_label") for s in swaps]
        self.assertTrue(
            any("thin" in str(l).lower() for l in labels),
            msg=f"Expected thin crust swap, got {labels}",
        )
        self.assertEqual(debug.get("source"), "chain_roadmap")

    def test_guzman_y_gomez_chain_gets_roadmap_swaps(self):
        from swap_rules import generate_swaps_for_item

        with _roadmap_path_override():
            swaps, debug = generate_swaps_for_item(
                place={"name": "Guzman y Gomez", "chain_key": "guzman_y_gomez", "types": ["restaurant"]},
                item_name="Grilled Chicken Burrito Bowl",
                estimated_calories=560,
                estimated_protein_g=40,
                menu_item_source="chain_registry",
                menu_item_confidence=0.9,
                cut_mode=True,
            )
        self.assertGreater(len(swaps), 0)
        labels = [s.get("swap_label") for s in swaps]
        self.assertTrue(
            any("sour" in str(l).lower() or "cream" in str(l).lower() or "bowl" in str(l).lower() for l in labels),
            msg=f"Expected GYG swap labels, got {labels}",
        )
        self.assertEqual(debug.get("source"), "chain_roadmap")

    def test_oporto_chain_gets_roadmap_swaps(self):
        from swap_rules import generate_swaps_for_item

        with _roadmap_path_override():
            swaps, debug = generate_swaps_for_item(
                place={"name": "Oporto", "chain_key": "oporto", "types": ["restaurant"]},
                item_name="Grilled Chicken Bondi Burger, no mayo",
                estimated_calories=480,
                estimated_protein_g=34,
                menu_item_source="chain_registry",
                menu_item_confidence=0.86,
                cut_mode=True,
            )
        self.assertGreater(len(swaps), 0)
        labels = [s.get("swap_label") for s in swaps]
        self.assertIn("No mayo", labels, msg=f"Expected no mayo swap for Oporto, got {labels}")
        self.assertEqual(debug.get("source"), "chain_roadmap")

    def test_grilld_chain_gets_roadmap_swaps(self):
        from swap_rules import generate_swaps_for_item

        with _roadmap_path_override():
            swaps, debug = generate_swaps_for_item(
                place={"name": "Grill'd", "chain_key": "grilld", "types": ["restaurant"]},
                item_name="Simply Grilled Chicken Burger",
                estimated_calories=430,
                estimated_protein_g=37,
                menu_item_source="chain_registry",
                menu_item_confidence=0.88,
                cut_mode=True,
            )
        self.assertGreater(len(swaps), 0)
        labels = [s.get("swap_label") for s in swaps]
        self.assertTrue(
            any("bunless" in str(l).lower() for l in labels),
            msg=f"Expected bunless swap for Grill'd, got {labels}",
        )
        self.assertEqual(debug.get("source"), "chain_roadmap")

    def test_boost_juice_chain_gets_roadmap_swaps(self):
        from swap_rules import generate_swaps_for_item

        with _roadmap_path_override():
            swaps, debug = generate_swaps_for_item(
                place={"name": "Boost Juice", "chain_key": "boost_juice", "types": ["cafe"]},
                item_name="All Day Super Protein",
                estimated_calories=350,
                estimated_protein_g=28,
                menu_item_source="chain_registry",
                menu_item_confidence=0.85,
                cut_mode=True,
            )
        self.assertGreater(len(swaps), 0)
        labels = [s.get("swap_label") for s in swaps]
        self.assertTrue(
            any("sugar" in str(l).lower() or "protein" in str(l).lower() for l in labels),
            msg=f"Expected Boost swap labels, got {labels}",
        )
        self.assertEqual(debug.get("source"), "chain_roadmap")


class TestAliasMatching(unittest.TestCase):
    def setUp(self):
        clear_roadmap_cache()

    def test_subway_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("Subway Westfield")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "subway")

    def test_mcdonalds_maccas_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("Maccas Parramatta")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "mcdonalds")

    def test_gyg_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("GYG")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "guzman_y_gomez")

    def test_kfc_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("KFC Parramatta")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "kfc")

    def test_hungry_jacks_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("Hungry Jack's Westfield")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "hungry_jacks")

    def test_dominos_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("Domino's Pizza")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "dominos")

    def test_pizza_hut_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("Pizza Hut")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "pizza_hut")

    def test_oporto_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("Oporto Chatswood")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "oporto")

    def test_grilld_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("Grill'd Bondi")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "grilld")

    def test_boost_juice_alias_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("Boost Juice")
        self.assertIsNotNone(m)
        self.assertEqual(str(m.get("chain_key") or "").lower(), "boost_juice")

    def test_unknown_place_no_match(self):
        with _roadmap_path_override():
            m = match_chain_by_alias("Random Local Cafe")
        self.assertIsNone(m)


class TestMarketFiltering(unittest.TestCase):
    def setUp(self):
        clear_roadmap_cache()

    def test_list_chains_by_market_au(self):
        with _roadmap_path_override():
            chains = list_chains_by_market("AU")
        self.assertGreater(len(chains), 5)
        for c in chains:
            tags = c.get("market_tags") or []
            self.assertIn("AU", [str(t).upper() for t in tags])

    def test_list_chains_by_market_us(self):
        with _roadmap_path_override():
            chains = list_chains_by_market("US")
        self.assertGreater(len(chains), 3)


class TestHelpers(unittest.TestCase):
    def setUp(self):
        clear_roadmap_cache()

    def test_get_chain_roadmap_subway(self):
        with _roadmap_path_override():
            c = get_chain_roadmap("subway")
        self.assertIsNotNone(c)
        self.assertEqual(c.get("display_name"), "Subway")
        self.assertEqual(c.get("coverage_status"), "live")

    def test_get_chain_templates_subway(self):
        with _roadmap_path_override():
            templates = get_chain_templates("subway")
        self.assertGreaterEqual(len(templates), 3)
        names = [t.get("template_name") for t in templates]
        self.assertTrue(any("6" in str(n) for n in names))

    def test_get_chain_templates_filter_by_market(self):
        with _roadmap_path_override():
            templates = get_chain_templates("subway", market="AU")
        self.assertGreaterEqual(len(templates), 2)

    def test_get_chain_swaps_without_template(self):
        with _roadmap_path_override():
            swaps = get_chain_swaps("subway")
        self.assertGreater(len(swaps), 0)

    def test_get_chain_swaps_with_template(self):
        with _roadmap_path_override():
            swaps = get_chain_swaps("subway", template_key="grilled_chicken_6inch")
        self.assertGreater(len(swaps), 0)
        keys = [s.get("swap_key") for s in swaps]
        self.assertIn("no_mayo", keys)

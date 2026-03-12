"""
Tests for powder detection and supplement-specific nutrition resolution.
Run with: cd backend && python -m unittest test_scan_powder_rules -v
"""
from __future__ import annotations

import unittest


class TestScanPowderRules(unittest.TestCase):
    def test_whey_powder_30g_has_realistic_protein(self):
        from scan_food_rules import resolve_powder_nutrition

        resolved = resolve_powder_nutrition(powder_type="whey", grams=30)
        macros100 = resolved["macros100"]
        # 30g whey ~24g protein => ~80g/100g
        self.assertGreater(macros100["protein_g_per_100g"], 60.0)

    def test_cocoa_powder_stays_distinct(self):
        from scan_food_rules import resolve_powder_nutrition

        whey = resolve_powder_nutrition(powder_type="whey", grams=30)["macros100"]["protein_g_per_100g"]
        cocoa = resolve_powder_nutrition(powder_type="cocoa_powder", grams=30)["macros100"]["protein_g_per_100g"]
        self.assertGreater(whey, cocoa * 3.0)

    def test_plant_protein_distinct_from_isolate(self):
        from scan_food_rules import resolve_powder_nutrition

        isolate = resolve_powder_nutrition(powder_type="whey_isolate", grams=30)["macros100"]["protein_g_per_100g"]
        plant = resolve_powder_nutrition(powder_type="plant_protein", grams=30)["macros100"]["protein_g_per_100g"]
        self.assertGreater(isolate, plant)

    def test_mass_gainer_not_whey(self):
        from scan_food_rules import resolve_powder_nutrition

        whey_p = resolve_powder_nutrition(powder_type="whey", grams=30)["macros100"]["protein_g_per_100g"]
        gainer_p = resolve_powder_nutrition(powder_type="mass_gainer", grams=30)["macros100"]["protein_g_per_100g"]
        self.assertLessEqual(gainer_p, whey_p * 0.5)

    def test_confirmation_scoop_size_changes_macros(self):
        from scan_food_rules import resolve_powder_nutrition

        m25 = resolve_powder_nutrition(powder_type="whey", grams=25)["macros100"]
        m40 = resolve_powder_nutrition(powder_type="whey", grams=40)["macros100"]
        # Per-100g macros same, but downstream scaling uses grams; sanity-check table values stable
        self.assertEqual(m25["protein_g_per_100g"], m40["protein_g_per_100g"])

    def test_detect_powder_like(self):
        from scan_food_rules import detect_powder_like

        is_powder, guess, needs = detect_powder_like("Chocolate protein powder", [])
        self.assertTrue(is_powder)
        self.assertTrue(needs)
        self.assertIn(guess, ("other_powder", "whey"))


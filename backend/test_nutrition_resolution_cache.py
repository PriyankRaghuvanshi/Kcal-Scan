"""Tests for nutrition resolution cache and normalization."""
import os
import tempfile
import unittest
from pathlib import Path

from nutrition_resolution_cache import (
    normalize_food_lookup_key,
    get_cached_nutrition_resolution,
    set_cached_nutrition_resolution,
    resolve_nutrition_with_cache,
)


class NormalizationTests(unittest.TestCase):
    """A. Normalization groups common safe synonyms/variants properly."""

    def test_lowercase_and_trim(self):
        self.assertEqual(normalize_food_lookup_key(" Chicken Breast "), "chicken breast")
        self.assertEqual(normalize_food_lookup_key("BANANA"), "banana")

    def test_plural_to_singular(self):
        self.assertEqual(normalize_food_lookup_key("eggs"), "egg")
        self.assertEqual(normalize_food_lookup_key("bananas"), "banana")
        self.assertEqual(normalize_food_lookup_key("potatoes"), "potato")
        self.assertEqual(normalize_food_lookup_key("avocados"), "avocado")

    def test_spelling_variants(self):
        self.assertEqual(normalize_food_lookup_key("yoghurt"), "yogurt")
        self.assertEqual(normalize_food_lookup_key("daal"), "dal")
        self.assertEqual(normalize_food_lookup_key("dhaal"), "dal")

    def test_weak_descriptors_stripped(self):
        self.assertEqual(normalize_food_lookup_key("cooked chicken breast"), "chicken breast")
        self.assertEqual(normalize_food_lookup_key("fresh banana"), "banana")
        self.assertEqual(normalize_food_lookup_key("plain Greek yogurt"), "greek yogurt")

    def test_strong_descriptors_preserved(self):
        self.assertEqual(normalize_food_lookup_key("chicken breast"), "chicken breast")
        self.assertEqual(normalize_food_lookup_key("chicken thigh"), "chicken thigh")
        self.assertEqual(normalize_food_lookup_key("white rice"), "white rice")
        self.assertEqual(normalize_food_lookup_key("brown rice"), "brown rice")
        self.assertEqual(normalize_food_lookup_key("whole milk"), "whole milk")
        self.assertEqual(normalize_food_lookup_key("skim milk"), "skim milk")
        self.assertEqual(normalize_food_lookup_key("whey protein"), "whey protein")
        self.assertEqual(normalize_food_lookup_key("plant protein"), "plant protein")


class DistinctFoodsTests(unittest.TestCase):
    """B. Distinct foods are not collapsed incorrectly."""

    def test_breast_vs_thigh(self):
        self.assertNotEqual(
            normalize_food_lookup_key("chicken breast"),
            normalize_food_lookup_key("chicken thigh"),
        )

    def test_white_vs_brown_rice(self):
        self.assertNotEqual(
            normalize_food_lookup_key("white rice"),
            normalize_food_lookup_key("brown rice"),
        )

    def test_whole_vs_skim_milk(self):
        self.assertNotEqual(
            normalize_food_lookup_key("whole milk"),
            normalize_food_lookup_key("skim milk"),
        )


class CacheTests(unittest.TestCase):
    """C. Cache hit avoids resolver call. D. Cache miss triggers resolver and stores result."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "nutrition_cache.json")

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.unlink(self.path)
            if os.path.exists(self.tmpdir):
                os.rmdir(self.tmpdir)
        except Exception:
            pass

    def test_cache_miss_triggers_resolver_and_stores(self):
        os.environ["NUTRITION_RESOLUTION_CACHE_PATH"] = self.path
        try:
            call_count = [0]

            def resolver(name: str):
                call_count[0] += 1
                return {
                    "macros100": {"kcal_per_100g": 165, "protein_g_per_100g": 31},
                    "source": "usda",
                    "resolved_name": name,
                    "confidence": 0.9,
                }

            out = resolve_nutrition_with_cache({"name": "chicken breast"}, resolver)
            self.assertEqual(call_count[0], 1)
            self.assertFalse(out.get("_cache_hit"))
            self.assertEqual(out.get("macros100", {}).get("kcal_per_100g"), 165)

            # Cache hit on second call
            out2 = resolve_nutrition_with_cache({"name": "Chicken Breast"}, resolver)
            self.assertEqual(call_count[0], 1)
            self.assertTrue(out2.get("_cache_hit"))
            self.assertEqual(out2.get("macros100", {}).get("kcal_per_100g"), 165)
        finally:
            os.environ.pop("NUTRITION_RESOLUTION_CACHE_PATH", None)

    def test_cache_hit_avoids_resolver_call(self):
        os.environ["NUTRITION_RESOLUTION_CACHE_PATH"] = self.path
        try:
            set_cached_nutrition_resolution(
                "chicken breast",
                {
                    "macros100": {"kcal_per_100g": 165},
                    "source": "usda",
                },
                ttl_hours=168,
            )
            call_count = [0]

            def resolver(name: str):
                call_count[0] += 1
                return {}

            out = resolve_nutrition_with_cache({"name": "chicken breast"}, resolver)
            self.assertEqual(call_count[0], 0)
            self.assertTrue(out.get("_cache_hit"))
            self.assertEqual(out.get("macros100", {}).get("kcal_per_100g"), 165)
        finally:
            os.environ.pop("NUTRITION_RESOLUTION_CACHE_PATH", None)


if __name__ == "__main__":
    unittest.main()

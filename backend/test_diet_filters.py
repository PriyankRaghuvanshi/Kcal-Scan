"""
Tests for diet filters: vegetarian, vegan, omnivore.
"""
import unittest

from diet_filters import (
    normalize_diet_preference,
    is_item_allowed_for_diet,
    filter_candidates_for_diet,
    apply_diet_flags,
    DIET_OMNIVORE,
    DIET_VEGETARIAN,
    DIET_VEGAN,
)


class TestNormalizeDietPreference(unittest.TestCase):
    def test_omnivore_default(self):
        self.assertEqual(normalize_diet_preference(""), "omnivore")
        self.assertEqual(normalize_diet_preference(None), "omnivore")
        self.assertEqual(normalize_diet_preference("omnivore"), "omnivore")

    def test_vegetarian(self):
        self.assertEqual(normalize_diet_preference("vegetarian"), "vegetarian")
        self.assertEqual(normalize_diet_preference("veg"), "vegetarian")

    def test_vegan(self):
        self.assertEqual(normalize_diet_preference("vegan"), "vegan")


class TestIsItemAllowedForDiet(unittest.TestCase):
    def test_omnivore_all_allowed(self):
        self.assertTrue(is_item_allowed_for_diet({"item_name": "Grilled chicken"}, "omnivore"))
        self.assertTrue(is_item_allowed_for_diet({"item_name": "Dal + roti"}, "omnivore"))

    def test_vegetarian_blocks_meat_chicken_fish(self):
        self.assertFalse(is_item_allowed_for_diet({"item_name": "Grilled chicken wrap"}, "vegetarian"))
        self.assertFalse(is_item_allowed_for_diet({"item_name": "Tandoori chicken + dal"}, "vegetarian"))
        self.assertFalse(is_item_allowed_for_diet({"item_name": "Salmon bowl"}, "vegetarian"))
        self.assertTrue(is_item_allowed_for_diet({"item_name": "Paneer tikka + dal"}, "vegetarian"))
        self.assertTrue(is_item_allowed_for_diet({"item_name": "Eggs on toast"}, "vegetarian"))

    def test_vegan_blocks_egg_dairy_whey(self):
        self.assertFalse(is_item_allowed_for_diet({"item_name": "Eggs on toast"}, "vegan"))
        self.assertFalse(is_item_allowed_for_diet({"item_name": "Greek yogurt bowl"}, "vegan"))
        self.assertFalse(is_item_allowed_for_diet({"item_name": "Grilled chicken"}, "vegan"))
        self.assertTrue(is_item_allowed_for_diet({"item_name": "Dal + roti"}, "vegan"))
        self.assertTrue(is_item_allowed_for_diet({"item_name": "Veggie sub, extra salad"}, "vegan"))

    def test_explicit_flags_override_inference(self):
        self.assertFalse(is_item_allowed_for_diet({"item_name": "Mystery bowl", "contains_chicken": True}, "vegetarian"))
        self.assertTrue(is_item_allowed_for_diet({"item_name": "Chicken curry", "contains_chicken": False}, "vegetarian"))


class TestFilterCandidatesForDiet(unittest.TestCase):
    def test_omnivore_returns_all(self):
        cands = [{"item_name": "Chicken"}, {"item_name": "Dal"}]
        filtered, excluded = filter_candidates_for_diet(cands, "omnivore")
        self.assertEqual(len(filtered), 2)
        self.assertEqual(excluded, 0)

    def test_vegetarian_filters_meat(self):
        cands = [
            {"item_name": "Tandoori chicken", "contains_chicken": True},
            {"item_name": "Paneer tikka", "vegetarian_possible": True},
            {"item_name": "Dal + roti", "vegan_possible": True},
        ]
        filtered, excluded = filter_candidates_for_diet(cands, "vegetarian")
        self.assertEqual(len(filtered), 2)
        self.assertEqual(excluded, 1)
        names = [c.get("item_name") for c in filtered]
        self.assertIn("Paneer tikka", names)
        self.assertIn("Dal + roti", names)
        self.assertNotIn("Tandoori chicken", names)

    def test_vegan_filters_dairy(self):
        cands = [
            {"item_name": "Greek yogurt bowl", "contains_dairy": True},
            {"item_name": "Dal + roti", "vegan_possible": True},
        ]
        filtered, excluded = filter_candidates_for_diet(cands, "vegan")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["item_name"], "Dal + roti")


class TestApplyDietFlags(unittest.TestCase):
    def test_adds_diet_flags_to_item(self):
        item = {"item_name": "Grilled chicken wrap"}
        out = apply_diet_flags(item)
        self.assertIn("diet_flags", out)
        flags = out["diet_flags"]
        self.assertIsInstance(flags, dict)
        self.assertTrue(flags.get("contains_chicken", False))

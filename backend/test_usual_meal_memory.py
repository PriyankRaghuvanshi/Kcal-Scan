import os
import tempfile
import unittest
from pathlib import Path

import user_ingredient_choices as uic


class UsualMealMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["USER_INGREDIENT_CHOICES_STORE_PATH"] = str(Path(self.tmp.name) / "choices.json")
        os.environ["USER_INGREDIENT_CHOICES_SUPABASE"] = "0"

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("USER_INGREDIENT_CHOICES_STORE_PATH", None)
        os.environ.pop("USER_INGREDIENT_CHOICES_SUPABASE", None)

    def test_save_and_find_hint(self):
        uic.save_usual_meal_memory_for_label(
            "u1",
            "oatmeal with whey protein and greek yogurt",
            {"kcal": 420.0, "protein_g": 35.0, "carbs_g": 40.0, "fat_g": 12.0},
        )
        hint = uic.find_usual_meal_hint(
            "u1",
            "bowl of oatmeal with berries",
            {"kcal": 410.0, "protein_g": 34.0, "carbs_g": 38.0, "fat_g": 11.0},
        )
        self.assertIsNotNone(hint)
        self.assertIn("usual", (hint or {}).get("line", "").lower())
        self.assertTrue((hint or {}).get("label"))

    def test_no_hint_when_kcal_far(self):
        uic.save_usual_meal_memory_for_label(
            "u2",
            "oatmeal breakfast",
            {"kcal": 400.0, "protein_g": 20.0, "carbs_g": 50.0, "fat_g": 10.0},
        )
        hint = uic.find_usual_meal_hint(
            "u2",
            "oatmeal",
            {"kcal": 700.0, "protein_g": 20.0, "carbs_g": 50.0, "fat_g": 10.0},
        )
        self.assertIsNone(hint)

    def test_meal_memory_keys_isolated_from_dimensions(self):
        uic.save_user_ingredient_choices("u3", "latte", {"dairy_type": "Oat"})
        uic.save_usual_meal_memory_for_label(
            "u3",
            "latte",
            {"kcal": 180.0, "protein_g": 8.0, "carbs_g": 14.0, "fat_g": 6.0},
        )
        g = uic.get_user_ingredient_choices("u3", "latte")
        self.assertEqual(g.get("dairy_type"), "Oat")
        self.assertIn(uic.MEAL_MEMORY_LABEL, g)


if __name__ == "__main__":
    unittest.main()

import json
import os
import tempfile
import unittest
from pathlib import Path

import user_ingredient_choices as uic


class UserIngredientChoicesFileStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["USER_INGREDIENT_CHOICES_STORE_PATH"] = str(Path(self.tmp.name) / "choices.json")
        os.environ["USER_INGREDIENT_CHOICES_SUPABASE"] = "0"

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("USER_INGREDIENT_CHOICES_STORE_PATH", None)
        os.environ.pop("USER_INGREDIENT_CHOICES_SUPABASE", None)

    def test_save_merges_then_get(self):
        uic.save_user_ingredient_choices("user-1", "oatmeal with honey", {"dairy_type": "Oat"})
        uic.save_user_ingredient_choices("user-1", "oatmeal with honey", {"sweetener": "Honey"})
        g = uic.get_user_ingredient_choices("user-1", "oatmeal with honey")
        self.assertEqual(g.get("dairy_type"), "Oat")
        self.assertEqual(g.get("sweetener"), "Honey")

    def test_component_key_isolated(self):
        ck = uic.component_memory_key("Oatmeal")
        self.assertTrue(ck.startswith("cmp::"))
        uic.save_user_ingredient_choices("user-1", ck, {"dairy_type": "Almond"})
        g = uic.get_user_ingredient_choices("user-1", ck)
        self.assertEqual(g.get("dairy_type"), "Almond")

    def test_persisted_to_file(self):
        uic.save_user_ingredient_choices("u2", "latte", {"dairy_type": "Oat"})
        path = Path(os.environ["USER_INGREDIENT_CHOICES_STORE_PATH"])
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = list((data.get("choices") or {}).keys())
        self.assertTrue(any("u2::" in k for k in keys))

    def test_component_memory_keys_for_item_name(self):
        keys = uic.component_memory_keys_for_item_name("Oatmeal with berries and honey")
        self.assertTrue(any(str(k).startswith("cmp::") for k in keys))
        self.assertTrue(len(keys) >= 2)


if __name__ == "__main__":
    unittest.main()

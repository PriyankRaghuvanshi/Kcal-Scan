import unittest

import recipe_suggestions as rs


class RecipeSuggestionsQueryTests(unittest.TestCase):
    def test_keywords_from_meal_prefers_components_and_items(self):
        meal = {
            "meal_components": ["oatmeal", "whey protein"],
            "items": [{"name": "bowl with banana"}],
        }
        kw = rs._keywords_from_meal(meal)
        self.assertIn("oatmeal", kw)
        self.assertIn("whey", kw)
        self.assertIn("protein", kw)
        self.assertIn("banana", kw)

    def test_extract_search_query_short(self):
        meal = {
            "items": [{"name": "grilled chicken breast with broccoli"}],
        }
        q = rs._extract_search_query(meal)
        self.assertLessEqual(len(q), 100)
        self.assertIn("chicken", q.lower())

    def test_rank_prefers_title_overlap_and_density(self):
        prefs = {"cuisine_affinity": {}}
        dismissed = set()
        recipes = [
            {
                "recipe_key": "a",
                "title": "Chocolate cake delight",
                "est_kcal_per_serving": 500,
                "est_protein_g_per_serving": 6,
                "cuisines": [],
            },
            {
                "recipe_key": "b",
                "title": "Grilled chicken quinoa bowl",
                "est_kcal_per_serving": 420,
                "est_protein_g_per_serving": 38,
                "cuisines": [],
            },
        ]
        ranked = rs._rank_recipes(
            recipes,
            prefs,
            dismissed,
            limit=2,
            meal_kcal=480,
            meal_protein=35,
            keywords=["chicken", "quinoa"],
        )
        self.assertEqual(ranked[0]["recipe_key"], "b")

    def test_spoonacular_include_ingredients_two_tokens(self):
        s = rs._spoonacular_include_ingredients_param(["chicken", "broccoli", "quinoa"])
        self.assertEqual(s, "chicken,broccoli")

    def test_spoonacular_include_ingredients_skips_banned_and_short(self):
        s = rs._spoonacular_include_ingredients_param(["meal", "food", "salmon"])
        self.assertEqual(s, "salmon")

    def test_spoonacular_include_ingredients_none_when_no_usable(self):
        self.assertIsNone(rs._spoonacular_include_ingredients_param([]))
        self.assertIsNone(rs._spoonacular_include_ingredients_param(["meal", "food"]))


if __name__ == "__main__":
    unittest.main()

import unittest

from meal_accuracy_decompose import clarification_phrases_for_item_name, decompose_meal_label


class MealAccuracyDecomposeTests(unittest.TestCase):
    def test_decompose_with_and(self):
        parts = decompose_meal_label("Breakfast bowl with oatmeal and berries")
        self.assertIn("oatmeal", parts)
        self.assertIn("berries", parts)

    def test_clarification_phrases_order(self):
        phrases = clarification_phrases_for_item_name("Bowl with oatmeal and honey")
        self.assertTrue(phrases)
        self.assertEqual(phrases[0], "bowl with oatmeal and honey")
        self.assertIn("oatmeal", phrases)
        self.assertIn("honey", phrases)


if __name__ == "__main__":
    unittest.main()

import unittest

import main as m


class ScanCookingAndPriorsTests(unittest.TestCase):
    def test_default_oil_air_fried_not_treated_as_deep_fry(self):
        self.assertEqual(
            m._default_fry_oil_tsp_for_method("air_fried", oil_was_explicitly_set=False, current_tsp=0.0),
            0.0,
        )

    def test_default_oil_stir_fried_no_auto_tsp(self):
        self.assertEqual(
            m._default_fry_oil_tsp_for_method("stir_fried", oil_was_explicitly_set=False, current_tsp=0.0),
            0.0,
        )

    def test_default_oil_pan_fried_when_unspecified(self):
        self.assertEqual(
            m._default_fry_oil_tsp_for_method("pan_fried", oil_was_explicitly_set=False, current_tsp=0.0),
            1.0,
        )

    def test_explicit_zero_oil_respected_for_pan_fried(self):
        self.assertEqual(
            m._default_fry_oil_tsp_for_method("pan_fried", oil_was_explicitly_set=True, current_tsp=0.0),
            0.0,
        )

    def test_lean_prep_reduces_fat(self):
        k, p, c, f = m._adjust_usda_macros_for_cooking_style("steamed", 300.0, 20.0, 30.0, 15.0)
        self.assertLess(f, 15.0)
        self.assertLess(k, 300.0)

    def test_fry_oil_prior_not_for_air_fried(self):
        self.assertFalse(m._cooking_method_implies_fry_oil_prior("air_fried"))

    def test_fry_oil_prior_for_pan_fried(self):
        self.assertTrue(m._cooking_method_implies_fry_oil_prior("pan_fried"))

    def test_food_prior_lookup_includes_oatmeal_base(self):
        toks = m._food_prior_lookup_tokens("Overnight oats with berries and banana")
        self.assertIn("oatmeal", toks)


if __name__ == "__main__":
    unittest.main()

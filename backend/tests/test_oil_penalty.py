import unittest

from local_venue_enrichment import (
    _oil_intensity_from_ingredients,
    _oil_intensity_from_fat,
    _oil_penalty,
    _apply_oil_penalty,
    _calorie_control_score,
    _ensure_chain_candidate_scores,
)


class TestOilPenalty(unittest.TestCase):
    def test_ingredient_tier_detection(self):
        ing_top = ["palm oil", "salt", "water"]
        ing_mid = ["water"] * 6 + ["vegetable oil"]
        ing_low = ["water"] * 12 + ["canola oil"]
        self.assertEqual(_oil_intensity_from_ingredients(ing_top), 90.0)
        self.assertEqual(_oil_intensity_from_ingredients(ing_mid), 60.0)
        self.assertEqual(_oil_intensity_from_ingredients(ing_low), 30.0)

    def test_fat_proxy_fallback(self):
        self.assertGreater(_oil_intensity_from_fat(500, 30, 10), 30.0)
        self.assertLess(_oil_intensity_from_fat(500, 10, 5), 30.0)

    def test_penalty_clamping(self):
        item = {"ingredients": ["palm oil", "salt"], "estimated_calories": 500, "estimated_fat_g": 30}
        self.assertEqual(_oil_penalty(item), 5.4)

    def test_no_overwrite_original_score(self):
        items = [
            {
                "item_name": "Test",
                "estimated_calories": 500,
                "estimated_fat_g": 30,
                "fat_loss_fit_score": 80.0,
                "protein_density_score": 70.0,
                "ingredients": ["palm oil", "salt"],
            }
        ]
        out = _apply_oil_penalty(items)
        self.assertEqual(out[0].get("fat_loss_fit_score"), 80.0)
        self.assertIn("fat_loss_fit_score_oil_adj", out[0])

    def test_no_penalty_without_base_score(self):
        items = [
            {
                "item_name": "NoScore",
                "estimated_calories": 500,
                "estimated_fat_g": 30,
                "ingredients": ["palm oil", "salt"],
            }
        ]
        out = _apply_oil_penalty(items)
        self.assertNotIn("fat_loss_fit_score_oil_adj", out[0])

    def test_missing_score_derivation_with_footlong_penalty(self):
        items = [
            {
                "item_name": "Footlong Test Sub",
                "estimated_calories": 520,
                "estimated_protein_g": 30,
            }
        ]
        out = _ensure_chain_candidate_scores(items)
        cc_base = _calorie_control_score(520)
        self.assertAlmostEqual(out[0].get("calorie_control_score"), max(0.0, round(cc_base - 20.0, 2)))
        self.assertGreater(out[0].get("protein_density_score"), 0.0)
        self.assertGreater(out[0].get("fat_loss_fit_score"), 0.0)

    def test_missing_score_derivation_with_calorie_threshold_penalty(self):
        items = [
            {
                "item_name": "Big Sub",
                "estimated_calories": 520,
                "estimated_protein_g": 25,
            }
        ]
        out = _ensure_chain_candidate_scores(items)
        cc_base = _calorie_control_score(520)
        self.assertAlmostEqual(out[0].get("calorie_control_score"), max(0.0, round(cc_base - 20.0, 2)))

    def test_no_overwrite_existing_scores(self):
        items = [
            {
                "item_name": "Has Scores",
                "estimated_calories": 400,
                "estimated_protein_g": 30,
                "fat_loss_fit_score": 77.0,
                "protein_density_score": 5.0,
            }
        ]
        out = _ensure_chain_candidate_scores(items)
        self.assertEqual(out[0].get("fat_loss_fit_score"), 77.0)
        self.assertEqual(out[0].get("protein_density_score"), 5.0)
        self.assertNotIn("calorie_control_score", out[0])


if __name__ == "__main__":
    unittest.main()

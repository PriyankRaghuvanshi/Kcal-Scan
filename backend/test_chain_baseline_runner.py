import unittest
import os
import tempfile
from unittest.mock import patch

from chain_baseline_runner import _build_case_output, diff_chain_against_baseline, generate_baseline_for_chain


class ChainBaselineRunnerTests(unittest.TestCase):
    @patch("chain_baseline_runner.enrich_place_with_local_profile")
    def test_build_case_output_shape(self, mock_enrich):
        mock_enrich.return_value = {
            "matched_chain_key": "mcdonalds",
            "chain_menu_store": "supabase",
            "top_menu_items": [{"item_name": "McChicken", "fat_loss_fit_score": 0.72}],
            "top_menu_item": {"estimated_calories": 420, "estimated_protein_g": 25},
            "chain_fallback_mode": "strict",
        }
        payload = _build_case_output(mock_enrich.return_value)
        self.assertEqual(payload.get("matched_chain_key"), "mcdonalds")
        self.assertIn("top_item_names", payload)
        self.assertIn("totals", payload)

    @patch("chain_baseline_runner.enrich_place_with_local_profile")
    def test_generate_and_diff_ok_with_same_payload(self, mock_enrich):
        sample = {
            "matched_chain_key": "mcdonalds",
            "chain_menu_store": "supabase",
            "top_menu_items": [{"item_name": "McChicken", "fat_loss_fit_score": 0.72}],
            "top_menu_item": {"estimated_calories": 420, "estimated_protein_g": 25},
            "chain_fallback_mode": "strict",
        }
        mock_enrich.return_value = sample
        with tempfile.TemporaryDirectory() as td:
            os.environ["CHAIN_BASELINE_SNAPSHOT_DIR"] = td
            try:
                generate_baseline_for_chain("mcdonalds", "AU", 99)
                res = diff_chain_against_baseline("mcdonalds", "AU", 99)
                self.assertTrue(bool(res.get("has_baseline")))
                self.assertTrue(bool(res.get("ok")))
            finally:
                os.environ.pop("CHAIN_BASELINE_SNAPSHOT_DIR", None)


if __name__ == "__main__":
    unittest.main()

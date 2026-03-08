import os
import unittest
from unittest.mock import patch

from llm_macro_estimator import maybe_estimate_unknown_meal_macros


class LlmMacroEstimatorTests(unittest.TestCase):
    def test_unknown_meal_uses_llm_when_enabled(self):
        llm_json = """
        {
          "estimated_calories": 590,
          "estimated_protein_g": 41,
          "estimated_carbs_g": 46,
          "estimated_fat_g": 18,
          "estimated_satiety": "high",
          "macro_confidence": 0.79
        }
        """
        with patch.dict(os.environ, {"ENABLE_LLM_MACRO_ESTIMATION": "true"}, clear=False):
            with patch("llm_macro_estimator._llm_available", return_value=True):
                with patch("llm_macro_estimator._invoke_llm_response_text", return_value=llm_json):
                    out = maybe_estimate_unknown_meal_macros(
                        item_name="Volcano dragon crunch stack",
                        cuisine_hint="fusion",
                        deterministic_estimate={
                            "estimated_calories": 520,
                            "estimated_protein_g": 28,
                            "estimated_carbs_g": 48,
                            "estimated_fat_g": 18,
                            "macro_confidence": 0.47,
                        },
                        has_known_nutrition=False,
                        profile_hit_count=0,
                    )

        self.assertTrue(bool(out.get("attempted")))
        self.assertTrue(bool(out.get("used")))
        estimate = out.get("estimate") or {}
        self.assertEqual(int(estimate.get("estimated_protein_g") or 0), 41)
        self.assertIn(str(estimate.get("estimated_satiety") or ""), {"low", "medium", "high"})

    def test_malformed_llm_json_falls_back(self):
        with patch.dict(os.environ, {"ENABLE_LLM_MACRO_ESTIMATION": "true"}, clear=False):
            with patch("llm_macro_estimator._llm_available", return_value=True):
                with patch("llm_macro_estimator._invoke_llm_response_text", return_value="not-json"):
                    out = maybe_estimate_unknown_meal_macros(
                        item_name="Mystery meal",
                        deterministic_estimate={"macro_confidence": 0.4},
                        has_known_nutrition=False,
                        profile_hit_count=0,
                    )
        self.assertTrue(bool(out.get("attempted")))
        self.assertFalse(bool(out.get("used")))
        self.assertEqual(str(out.get("error") or ""), "invalid_llm_json")

    def test_llm_timeout_failure_falls_back(self):
        with patch.dict(os.environ, {"ENABLE_LLM_MACRO_ESTIMATION": "true"}, clear=False):
            with patch("llm_macro_estimator._llm_available", return_value=True):
                with patch("llm_macro_estimator._invoke_llm_response_text", side_effect=RuntimeError("timeout")):
                    out = maybe_estimate_unknown_meal_macros(
                        item_name="Mystery meal",
                        deterministic_estimate={"macro_confidence": 0.4},
                        has_known_nutrition=False,
                        profile_hit_count=0,
                    )
        self.assertTrue(bool(out.get("attempted")))
        self.assertFalse(bool(out.get("used")))
        self.assertIn("timeout", str(out.get("error") or ""))

    def test_bounds_validation_clamps_values(self):
        llm_json = """
        {
          "estimated_calories": 5000,
          "estimated_protein_g": -4,
          "estimated_carbs_g": 999,
          "estimated_fat_g": 999,
          "estimated_satiety": "extreme",
          "macro_confidence": 1.7
        }
        """
        with patch.dict(os.environ, {"ENABLE_LLM_MACRO_ESTIMATION": "true"}, clear=False):
            with patch("llm_macro_estimator._llm_available", return_value=True):
                with patch("llm_macro_estimator._invoke_llm_response_text", return_value=llm_json):
                    out = maybe_estimate_unknown_meal_macros(
                        item_name="Hyper mega loaded stack",
                        deterministic_estimate={"macro_confidence": 0.42},
                        has_known_nutrition=False,
                        profile_hit_count=0,
                    )
        self.assertTrue(bool(out.get("used")))
        estimate = out.get("estimate") or {}
        self.assertLessEqual(int(estimate.get("estimated_calories") or 0), 1300)
        self.assertGreaterEqual(int(estimate.get("estimated_protein_g") or 0), 8)
        self.assertLessEqual(float(estimate.get("macro_confidence") or 0.0), 0.92)
        self.assertIn(str(estimate.get("estimated_satiety") or ""), {"low", "medium", "high"})

    def test_known_nutrition_does_not_escalate_to_llm(self):
        with patch.dict(os.environ, {"ENABLE_LLM_MACRO_ESTIMATION": "true"}, clear=False):
            with patch("llm_macro_estimator._invoke_llm_response_text") as mocked_llm:
                out = maybe_estimate_unknown_meal_macros(
                    item_name="Chicken bowl",
                    deterministic_estimate={"macro_confidence": 0.42},
                    has_known_nutrition=True,
                    profile_hit_count=2,
                )
        mocked_llm.assert_not_called()
        self.assertFalse(bool(out.get("attempted")))
        self.assertFalse(bool(out.get("used")))


if __name__ == "__main__":
    unittest.main()


import os
import unittest
from unittest.mock import patch

from llm_explanation_copy import maybe_rewrite_explanation_copy


class LlmExplanationCopyTests(unittest.TestCase):
    def test_south_indian_sparse_place_gets_cuisine_aware_copy(self):
        llm_json = """
        {
          "why_this_works": "Likely easier to fit with simpler South Indian options here.",
          "short_reason": "Prefer less oily and less fried tiffin-style picks.",
          "copy_confidence": 0.78
        }
        """
        with patch.dict(os.environ, {"ENABLE_LLM_EXPLANATION_COPY": "true"}, clear=False):
            with patch("llm_explanation_copy._llm_available", return_value=True):
                with patch("llm_explanation_copy._invoke_llm", return_value=llm_json):
                    out = maybe_rewrite_explanation_copy(
                        place_name="Shri Temple Canteen",
                        cuisine="south indian, temple canteen",
                        recommended_order="Suggested lighter option",
                        estimated_calories=430,
                        estimated_protein_g=14,
                        typical_order_calories=780,
                        goal="fat_loss",
                        confidence=0.58,
                        recommendation_source="llm_inferred",
                        menu_item_confidence=0.52,
                        base_why_this_works="Likely easier to fit with simpler options here.",
                        base_short_reason="Prefer lighter picks over fried options.",
                    )
        self.assertEqual(out.get("copy_method"), "llm")
        merged = f"{out.get('why_this_works')} {out.get('short_reason')}".lower()
        self.assertTrue(any(token in merged for token in ("south indian", "tiffin", "lighter", "oily")))
        self.assertGreater(float(out.get("copy_confidence", 0.0)), 0.0)

    def test_cafe_sparse_place_gets_cafe_specific_copy(self):
        llm_json = """
        {
          "why_this_works": "Can work today if you keep cafe choices simple.",
          "short_reason": "Skip pastries and sweet drinks for better calorie control.",
          "copy_confidence": 0.74
        }
        """
        with patch.dict(os.environ, {"ENABLE_LLM_EXPLANATION_COPY": "true"}, clear=False):
            with patch("llm_explanation_copy._llm_available", return_value=True):
                with patch("llm_explanation_copy._invoke_llm", return_value=llm_json):
                    out = maybe_rewrite_explanation_copy(
                        place_name="Local Corner Cafe",
                        cuisine="cafe",
                        recommended_order="Suggested lighter option",
                        estimated_calories=480,
                        estimated_protein_g=24,
                        goal="maintenance",
                        confidence=0.53,
                        recommendation_source="heuristic",
                        menu_item_confidence=0.49,
                        base_why_this_works="Suggested lighter option; menu details are limited.",
                        base_short_reason="Look for simpler choices here.",
                    )
        merged = f"{out.get('why_this_works')} {out.get('short_reason')}".lower()
        self.assertIn(out.get("copy_method"), {"llm", "deterministic"})
        self.assertTrue(any(token in merged for token in ("cafe", "pastries", "sweet drinks", "simple")))

    def test_fast_food_copy_stays_short_and_practical(self):
        llm_json = """
        {
          "why_this_works": "A leaner swap here gives better protein for fewer calories.",
          "short_reason": "Skip fries and sugary drinks to keep this lighter.",
          "copy_confidence": 0.8
        }
        """
        with patch.dict(os.environ, {"ENABLE_LLM_EXPLANATION_COPY": "true"}, clear=False):
            with patch("llm_explanation_copy._llm_available", return_value=True):
                with patch("llm_explanation_copy._invoke_llm", return_value=llm_json):
                    out = maybe_rewrite_explanation_copy(
                        place_name="Burger Fast Food Corner",
                        cuisine="fast food, burger",
                        recommended_order="Single grilled chicken burger",
                        estimated_calories=470,
                        estimated_protein_g=28,
                        typical_order_calories=1080,
                        goal="fat_loss",
                        confidence=0.78,
                        recommendation_source="real_menu",
                        menu_item_confidence=0.81,
                        base_why_this_works="Better calorie control than usual combos.",
                        base_short_reason="Leaner option for your calories.",
                    )
        self.assertIn(out.get("copy_method"), {"llm", "deterministic"})
        self.assertLessEqual(len(str(out.get("why_this_works") or "")), 120)
        self.assertLessEqual(len(str(out.get("short_reason") or "")), 90)

    def test_invalid_output_fallback(self):
        with patch.dict(os.environ, {"ENABLE_LLM_EXPLANATION_COPY": "true"}, clear=False):
            with patch("llm_explanation_copy._llm_available", return_value=True):
                with patch("llm_explanation_copy._invoke_llm", return_value="not-json"):
                    out = maybe_rewrite_explanation_copy(
                        place_name="Nando's",
                        recommended_order="Quarter chicken + salad",
                        recommendation_source="real_menu",
                        menu_item_confidence=0.82,
                        base_why_this_works="High protein and easier to fit today.",
                        base_short_reason="High protein and easier calories.",
                    )
        self.assertEqual(out.get("copy_method"), "deterministic")
        self.assertIn("invalid_llm_json", str(out.get("copy_fallback_reason") or ""))
        self.assertGreater(float(out.get("copy_confidence", 0.0)), 0.0)

    def test_disabled_fallback(self):
        with patch.dict(os.environ, {"ENABLE_LLM_EXPLANATION_COPY": "false"}, clear=False):
            with patch("llm_explanation_copy._invoke_llm") as mocked:
                out = maybe_rewrite_explanation_copy(
                    place_name="Temple Canteen",
                    cuisine="south indian, canteen",
                    recommended_order="Grilled protein bowl",
                    recommendation_source="heuristic",
                    menu_item_confidence=0.34,
                    base_why_this_works="High protein and easier to fit today.",
                    base_short_reason="High protein and easier calories.",
                )
        mocked.assert_not_called()
        self.assertEqual(out.get("copy_method"), "deterministic")
        self.assertFalse(bool(out.get("copy_attempted")))
        merged = f"{out.get('why_this_works')} {out.get('short_reason')}".lower()
        self.assertNotIn("protein bowl", merged)
        self.assertTrue(any(token in merged for token in ("south indian", "tiffin", "lighter", "less fried")))

    def test_length_guardrails_fallback(self):
        llm_json = """
        {
          "why_this_works": "This explanation is intentionally too long and verbose to pass the compact mobile copy guardrails that we enforce in production.",
          "short_reason": "This short reason is also intentionally too long to pass."
        }
        """
        with patch.dict(os.environ, {"ENABLE_LLM_EXPLANATION_COPY": "true"}, clear=False):
            with patch("llm_explanation_copy._llm_available", return_value=True):
                with patch("llm_explanation_copy._invoke_llm", return_value=llm_json):
                    out = maybe_rewrite_explanation_copy(
                        place_name="Pizza Place",
                        recommended_order="Thin crust + protein topping",
                        recommendation_source="heuristic",
                        menu_item_confidence=0.47,
                        base_why_this_works="Lower calorie overload with better protein.",
                        base_short_reason="Leaner pizza move.",
                    )
        self.assertEqual(out.get("copy_method"), "deterministic")
        self.assertIn("output_too_long_or_invalid", str(out.get("copy_fallback_reason") or ""))

    def test_low_confidence_heuristic_copy_stays_soft_and_honest(self):
        llm_json = """
        {
          "why_this_works": "This grilled protein bowl is the perfect option for this place.",
          "short_reason": "Best possible macro choice here."
        }
        """
        with patch.dict(os.environ, {"ENABLE_LLM_EXPLANATION_COPY": "true"}, clear=False):
            with patch("llm_explanation_copy._llm_available", return_value=True):
                with patch("llm_explanation_copy._invoke_llm", return_value=llm_json):
                    out = maybe_rewrite_explanation_copy(
                        place_name="Local Temple Canteen",
                        cuisine="south indian, temple canteen",
                        recommended_order="Grilled protein bowl",
                        recommendation_source="heuristic",
                        menu_item_confidence=0.32,
                        confidence=0.36,
                        base_why_this_works="Suggested lighter option; menu details are still limited.",
                        base_short_reason="Look for simpler, less fried choices here.",
                    )
        self.assertEqual(out.get("copy_method"), "deterministic")
        self.assertIn("over", str(out.get("copy_fallback_reason") or "").lower())
        merged = f"{out.get('why_this_works')} {out.get('short_reason')}".lower()
        self.assertNotIn("grilled protein bowl", merged)
        self.assertTrue(any(token in merged for token in ("likely", "suggested", "look for", "lighter")))


if __name__ == "__main__":
    unittest.main()

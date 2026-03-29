import os
import unittest
from unittest.mock import patch

from llm_coach_phrasing import maybe_rephrase_coach_message


class LlmCoachPhrasingTests(unittest.TestCase):
    def test_successful_rewrite(self):
        llm_json = """
        {
          "headline": "Best fit for your calories.",
          "supporting_text": "High protein and easier to fit than heavier nearby options."
        }
        """
        with patch.dict(os.environ, {"ENABLE_LLM_COACH_PHRASING": "true"}, clear=False):
            with patch("llm_coach_phrasing._llm_available", return_value=True):
                with patch("llm_coach_phrasing._invoke_llm", return_value=llm_json):
                    out = maybe_rephrase_coach_message(
                        headline="Best fit for your remaining calories.",
                        supporting_text="High protein and easier to fit than heavier nearby lunch options.",
                        context={"tone": "encouraging"},
                    )
        self.assertEqual(out.get("phrasing_method"), "llm")
        self.assertIn("headline", out)
        self.assertIn("supporting_text", out)

    def test_too_long_output_falls_back(self):
        llm_json = """
        {
          "headline": "This is a very long headline that should fail the strict compact mobile length rule quickly",
          "supporting_text": "This supporting text is also intentionally too long and verbose for the mobile coach panel and should trigger fallback."
        }
        """
        with patch.dict(os.environ, {"ENABLE_LLM_COACH_PHRASING": "true"}, clear=False):
            with patch("llm_coach_phrasing._llm_available", return_value=True):
                with patch("llm_coach_phrasing._invoke_llm", return_value=llm_json):
                    out = maybe_rephrase_coach_message(
                        headline="Best fit for your remaining calories.",
                        supporting_text="High protein and easier to fit today.",
                    )
        self.assertEqual(out.get("phrasing_method"), "deterministic")
        self.assertIn("output_too_long_or_invalid", str(out.get("phrasing_fallback_reason") or ""))

    def test_invalid_json_fallback(self):
        with patch.dict(os.environ, {"ENABLE_LLM_COACH_PHRASING": "true"}, clear=False):
            with patch("llm_coach_phrasing._llm_available", return_value=True):
                with patch("llm_coach_phrasing._invoke_llm", return_value="not-json"):
                    out = maybe_rephrase_coach_message(
                        headline="Best fit for your remaining calories.",
                        supporting_text="High protein and easier to fit today.",
                    )
        self.assertEqual(out.get("phrasing_method"), "deterministic")
        self.assertIn("invalid_llm_json", str(out.get("phrasing_fallback_reason") or ""))

    def test_llm_disabled_fallback(self):
        with patch.dict(os.environ, {"ENABLE_LLM_COACH_PHRASING": "false"}, clear=False):
            with patch("llm_coach_phrasing._invoke_llm") as mocked:
                out = maybe_rephrase_coach_message(
                    headline="Best fit for your remaining calories.",
                    supporting_text="High protein and easier to fit today.",
                )
        mocked.assert_not_called()
        self.assertEqual(out.get("phrasing_method"), "deterministic")
        self.assertFalse(bool(out.get("phrasing_attempted")))


    def test_day_coach_variation_is_deterministic_without_llm(self):
        from day_coach import build_day_coach_summary
        a = build_day_coach_summary(remaining_protein_g=72, goal="fat_loss", cut_mode=True)
        b = build_day_coach_summary(remaining_protein_g=72, goal="fat_loss", cut_mode=True)
        c = build_day_coach_summary(remaining_protein_g=38, goal="fat_loss", cut_mode=True)
        self.assertEqual((a.get("headline"), a.get("supporting_text")), (b.get("headline"), b.get("supporting_text")))
        self.assertNotEqual((a.get("headline"), a.get("supporting_text")), (c.get("headline"), c.get("supporting_text")))
        self.assertEqual(a.get("phrasing_method"), "deterministic")


if __name__ == "__main__":
    unittest.main()


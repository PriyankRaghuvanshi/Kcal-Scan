import unittest
from unittest.mock import patch

from menu_scan import build_menu_scan_response, parse_menu_items_from_text


class MenuScanTests(unittest.TestCase):
    def test_menu_text_parsing_filters_noise(self):
        raw = """
        MENU
        STARTERS
        Chicken burrito bowl ........ $14.90
        Loaded nachos $18
        Chicken tacos (no crema) 12.50
        THANK YOU
        """
        items = parse_menu_items_from_text(raw)
        names = [str(x.get("item_name") or "").lower() for x in items]

        self.assertTrue(any("chicken burrito bowl" in n for n in names))
        self.assertTrue(any("loaded nachos" in n for n in names))
        self.assertFalse(any(n == "menu" for n in names))

    def test_top_recommendation_and_avoid_selection(self):
        raw = """
        Chicken burrito bowl $14
        Chicken tacos (no crema) $12
        Loaded nachos $18
        Double burger combo $17
        """
        out = build_menu_scan_response(
            raw_menu_text=raw,
            ocr_confidence=0.82,
            restaurant_name="Mexican Grill",
            cuisine="mexican",
            remaining_calories=1300,
            remaining_protein_g=90,
            goal="fat_loss",
            cut_mode=True,
        )

        self.assertEqual(out.get("title"), "Best Choice Here")
        self.assertTrue(len(out.get("top_recommendations") or []) >= 1)
        self.assertIsInstance(out.get("better_swap"), (dict, type(None)))
        self.assertIsInstance(out.get("avoid_if_cutting"), dict)
        avoid_name = str((out.get("avoid_if_cutting") or {}).get("item_name") or "").lower()
        self.assertTrue("nachos" in avoid_name or "burger" in avoid_name)

    def test_sparse_noisy_fallback(self):
        raw = """
        MENU
        $9.99
        $12.00
        WELCOME
        """
        out = build_menu_scan_response(raw_menu_text=raw, ocr_confidence=0.32)
        self.assertIn("clearer photo", str(out.get("title") or "").lower())
        self.assertEqual(len(out.get("top_recommendations") or []), 0)
        self.assertLessEqual(float(out.get("scan_confidence") or 0.0), 0.5)

    def test_daily_context_fit_enrichment(self):
        raw = """
        Loaded nachos
        Family pizza combo
        Crispy chicken bucket
        """
        out = build_menu_scan_response(
            raw_menu_text=raw,
            ocr_confidence=0.75,
            remaining_calories=300,
            remaining_protein_g=20,
            goal="fat_loss",
            cut_mode=True,
        )
        top = (out.get("top_recommendations") or [{}])[0]
        self.assertIn("fit_for_today", top)
        self.assertIn("decision_today", top)
        self.assertIn(str(top.get("decision_today") or ""), {"NO", "MAYBE", "YES", ""})

    def test_no_daily_context_keeps_fit_optional(self):
        raw = """
        Chicken bowl
        Tuna salad
        Steak rice plate
        """
        out = build_menu_scan_response(
            raw_menu_text=raw,
            ocr_confidence=0.8,
            restaurant_name="Protein House",
        )
        top = (out.get("top_recommendations") or [{}])[0]
        self.assertIsNone(top.get("fit_for_today"))
        self.assertIn("coach_message", out)

    def test_parse_metadata_fields_are_present(self):
        raw = """
        Chicken burrito bowl $14
        Chicken tacos $12
        Loaded nachos $18
        """
        with patch.dict("os.environ", {"ENABLE_LLM_MENU_PARSING": "false"}, clear=False):
            out = build_menu_scan_response(
                raw_menu_text=raw,
                ocr_confidence=0.8,
                restaurant_name="Mexican Grill",
            )

        self.assertIn(out.get("parse_method"), {"deterministic", "llm"})
        self.assertIn("parse_version", out)
        self.assertIn("parser_confidence", out)
        self.assertIsInstance(out.get("parsed_menu_items_structured"), list)


if __name__ == "__main__":
    unittest.main()

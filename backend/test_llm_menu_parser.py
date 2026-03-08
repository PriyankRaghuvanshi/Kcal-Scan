import os
import unittest
from unittest.mock import patch

from llm_menu_parser import (
    _call_llm_menu_parse,
    infer_place_menu_items_with_optional_llm,
    parse_menu_items_with_optional_llm,
)


class LlmMenuParserTests(unittest.TestCase):
    def test_clean_menu_text_keeps_deterministic_parse(self):
        deterministic_items = [
            {"item_name": "Chicken pesto bowl", "confidence": 0.82},
            {"item_name": "Steak rice plate", "confidence": 0.78},
            {"item_name": "Tuna salad", "confidence": 0.8},
        ]
        with patch.dict(os.environ, {"ENABLE_LLM_MENU_PARSING": "true"}, clear=False):
            with patch("llm_menu_parser._call_llm_menu_parse") as mocked_llm:
                out = parse_menu_items_with_optional_llm(
                    raw_text="Chicken pesto bowl\nSteak rice plate\nTuna salad\n",
                    deterministic_items=deterministic_items,
                )
        mocked_llm.assert_not_called()
        self.assertEqual(out.get("parse_method"), "deterministic")
        self.assertFalse(bool(out.get("llm_attempted")))
        self.assertGreaterEqual(len(out.get("parsed_items") or []), 3)

    def test_messy_menu_text_uses_llm_parse_when_available(self):
        deterministic_items = [{"item_name": "Combo", "confidence": 0.45}]
        llm_items = [
            {
                "item_name": "Chicken pesto bowl",
                "category": "bowl",
                "likely_protein": "chicken",
                "likely_carbs": ["rice"],
                "likely_fats": ["pesto"],
                "health_signals": ["high_protein"],
                "parser_confidence": 0.84,
            },
            {
                "item_name": "Loaded nachos",
                "category": "combo",
                "likely_protein": "beef",
                "likely_carbs": ["chips"],
                "likely_fats": ["cheese"],
                "health_signals": ["calorie_dense"],
                "parser_confidence": 0.73,
            },
        ]
        with patch.dict(os.environ, {"ENABLE_LLM_MENU_PARSING": "true"}, clear=False):
            with patch("llm_menu_parser._call_llm_menu_parse", return_value=(llm_items, "")):
                out = parse_menu_items_with_optional_llm(
                    raw_text="Specials | bowls | combos | chef table",
                    deterministic_items=deterministic_items,
                )
        self.assertEqual(out.get("parse_method"), "llm")
        self.assertTrue(bool(out.get("llm_attempted")))
        structured = out.get("structured_items") or []
        self.assertEqual(structured[0]["category"], "bowl")
        self.assertEqual(structured[0]["likely_protein"], "chicken")

    def test_llm_unavailable_falls_back_to_deterministic(self):
        deterministic_items = [
            {"item_name": "Chicken bowl", "confidence": 0.74},
            {"item_name": "Loaded nachos", "confidence": 0.68},
        ]
        with patch.dict(os.environ, {"ENABLE_LLM_MENU_PARSING": "true"}, clear=False):
            with patch("llm_menu_parser._call_llm_menu_parse", return_value=([], "llm_unavailable")):
                out = parse_menu_items_with_optional_llm(
                    raw_text="MENU | combos | ???",
                    deterministic_items=deterministic_items,
                )
        self.assertEqual(out.get("parse_method"), "deterministic")
        self.assertTrue(bool(out.get("llm_attempted")))
        self.assertIn("llm_unavailable", str(out.get("llm_error") or ""))
        self.assertEqual(len(out.get("parsed_items") or []), 2)

    def test_invalid_llm_json_returns_error(self):
        with patch("llm_menu_parser._llm_available", return_value=True):
            with patch("llm_menu_parser._invoke_llm_response_text", return_value="not json"):
                items, err = _call_llm_menu_parse(
                    raw_text="Loaded nachos\nChicken bowl",
                    ocr_lines=None,
                    max_items=8,
                )
        self.assertEqual(items, [])
        self.assertEqual(err, "invalid_llm_json")

    def test_ambiguous_lines_keep_safe_structure(self):
        out = parse_menu_items_with_optional_llm(
            raw_text="Chef pick ...\nHouse special / 17\nMeal option\n",
            deterministic_items=[],
        )
        self.assertEqual(out.get("parse_method"), "deterministic")
        self.assertIn("parse_version", out)
        self.assertIn("parsed_items", out)

    def test_place_understanding_uses_llm_when_enabled(self):
        place = {"name": "Shri Temple Canteen", "types": ["restaurant", "canteen"]}
        llm_items = [
            {
                "item_name": "Idli or plain dosa-style option",
                "category": "plate",
                "likely_protein": "lentil",
                "likely_carbs": ["rice"],
                "likely_fats": [],
                "health_signals": ["high_fiber"],
                "parser_confidence": 0.64,
            }
        ]
        with patch.dict(os.environ, {"ENABLE_LLM_MENU_PARSING": "true"}, clear=False):
            with patch("llm_menu_parser._llm_available", return_value=True):
                with patch("llm_menu_parser._call_llm_place_menu_understanding", return_value=(llm_items, "")):
                    out = infer_place_menu_items_with_optional_llm(
                        place=place,
                        heuristic_items=[{"item_name": "Grilled protein bowl"}],
                    )
        self.assertEqual(out.get("parse_method"), "llm_inferred")
        parsed = out.get("parsed_items") or []
        self.assertGreaterEqual(len(parsed), 1)
        self.assertEqual(parsed[0].get("menu_item_source"), "llm_inferred")

    def test_place_understanding_falls_back_when_llm_unavailable(self):
        place = {"name": "Unknown Food Spot", "types": ["restaurant"]}
        with patch.dict(os.environ, {"ENABLE_LLM_MENU_PARSING": "true"}, clear=False):
            with patch("llm_menu_parser._llm_available", return_value=False):
                out = infer_place_menu_items_with_optional_llm(
                    place=place,
                    heuristic_items=[{"item_name": "Lighter menu option"}],
                )
        self.assertEqual(out.get("parse_method"), "heuristic")
        self.assertTrue(bool(out.get("llm_attempted")))
        self.assertIn("llm_unavailable", str(out.get("llm_error") or ""))


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from menu_ingestion import ingest_real_menu_for_place, normalize_menu_text


class _MockResponse:
    def __init__(self, *, status_code=200, text="", url="", headers=None):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}


class MenuIngestionTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._old_store = os.environ.get("MENU_INTELLIGENCE_STORE_PATH")
        os.environ["MENU_INTELLIGENCE_STORE_PATH"] = os.path.join(self._tmp_dir.name, "menu_store.json")

    def tearDown(self):
        if self._old_store is None:
            os.environ.pop("MENU_INTELLIGENCE_STORE_PATH", None)
        else:
            os.environ["MENU_INTELLIGENCE_STORE_PATH"] = self._old_store
        self._tmp_dir.cleanup()

    def test_normalize_menu_text_filters_noise_and_dedupes(self):
        raw = """
        MENU
        Chicken tikka .... $14.50
        Chicken tikka .... $14.50
        Paneer wrap $12
        ---
        """
        out = normalize_menu_text(raw)
        self.assertIn("Chicken tikka", out)
        self.assertIn("Paneer wrap", out)
        self.assertEqual(out.lower().count("chicken tikka"), 1)

    def test_website_menu_extraction_uses_menu_link_text(self):
        place = {
            "place_id": "p-website-1",
            "name": "Spice House",
            "website_url": "https://example.com",
        }

        homepage = """
        <html><body>
          <a href="/menu">Our Menu</a>
          <p>Welcome to Spice House</p>
        </body></html>
        """
        menu_page = """
        <html><body>
          <h1>Menu</h1>
          <p>Chicken tikka - $14</p>
          <p>Paneer wrap - $12</p>
          <p>Loaded fries - $11</p>
        </body></html>
        """

        def _mock_fetch(url, timeout_sec=4.5):
            if str(url).endswith("/menu"):
                return (
                    normalize_menu_text("Chicken tikka - $14\nPaneer wrap - $12\nLoaded fries - $11"),
                    "https://example.com/menu",
                    "text/html; charset=utf-8",
                )
            return (normalize_menu_text(homepage), "https://example.com", "text/html; charset=utf-8")

        fake_requests = SimpleNamespace(
            get=lambda url, **kwargs: _MockResponse(text=homepage, url="https://example.com")
        )
        with patch("menu_ingestion.requests", new=fake_requests):
            with patch("menu_ingestion._extract_menu_links", return_value=["https://example.com/menu"]):
                with patch("menu_ingestion._fetch_url_text", side_effect=_mock_fetch):
                    out = ingest_real_menu_for_place(place, max_items=6)

        self.assertTrue(out.get("ingested"))
        self.assertIn(out.get("menu_source"), {"website_menu", "website_text"})
        self.assertTrue(str(out.get("source_url") or "").startswith("https://example.com"))
        items = out.get("menu_items") or []
        self.assertGreaterEqual(len(items), 2)
        self.assertTrue(any("tikka" in str(i.get("item_name") or "").lower() for i in items))
        self.assertTrue(any(i.get("menu_source") in {"website_menu", "website_text"} for i in items))

    def test_llm_parsing_integration_passes_parse_metadata(self):
        place = {
            "place_id": "p-llm-1",
            "name": "Cafe Hub",
            "menu_text": "Special board text",
        }
        llm_bundle = {
            "parsed_items": [
                {"item_name": "Egg and chicken plate", "confidence": 0.81},
            ],
            "structured_items": [
                {
                    "item_name": "Egg and chicken plate",
                    "category": "plate",
                    "likely_protein": "chicken",
                    "likely_carbs": [],
                    "likely_fats": ["oil"],
                    "health_signals": ["high_protein"],
                    "parser_confidence": 0.81,
                }
            ],
            "parse_method": "llm",
            "parse_version": "v1",
            "parser_confidence": 0.81,
            "llm_enabled": True,
            "llm_attempted": True,
            "llm_error": "",
        }

        with patch("menu_ingestion.parse_menu_items_with_optional_llm", return_value=llm_bundle):
            out = ingest_real_menu_for_place(place, max_items=3)

        self.assertTrue(out.get("ingested"))
        self.assertEqual(out.get("parse_method"), "llm")
        item = (out.get("menu_items") or [{}])[0]
        self.assertEqual(item.get("parsed_via"), "llm")
        self.assertEqual(item.get("parse_method"), "llm")
        self.assertTrue(item.get("raw_text_snippet"))

    def test_source_labeling_fields_exist(self):
        place = {
            "place_id": "p-label-1",
            "name": "Local Eatery",
            "review_snippets": ["Try the chicken dosa and avoid fried combo specials."],
        }
        out = ingest_real_menu_for_place(place, max_items=4)
        self.assertTrue(out.get("ingested"))
        item = (out.get("menu_items") or [{}])[0]
        self.assertIn(item.get("menu_source"), {"review_text", "website_text", "website_menu", "ocr_menu"})
        self.assertIn("menu_confidence", item)
        self.assertIn("extraction_method", item)
        self.assertIn("parse_method", item)
        self.assertIn("source_url", item)

    def test_fallback_when_no_menu_data(self):
        out = ingest_real_menu_for_place({"place_id": "none-1", "name": "Unknown Spot"})
        self.assertFalse(out.get("ingested"))
        self.assertEqual(out.get("menu_items"), [])
        self.assertEqual(out.get("menu_source"), "none")


if __name__ == "__main__":
    unittest.main()

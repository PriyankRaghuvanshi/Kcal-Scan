import json
import tempfile
import unittest
from pathlib import Path

from menu_intelligence_cleanup import cleanup_menu_intelligence_store


class MenuIntelligenceCleanupTests(unittest.TestCase):
    def _write_store(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def test_cleanup_downgrades_banned_generic_in_sensitive_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "store.json"
            payload = {
                "version": "v1",
                "places": {
                    "p1": {
                        "place_id": "p1",
                        "restaurant_name": "Temple Canteen",
                        "cuisine": "south indian",
                        "menu_items": [
                            {
                                "item_name": "Greek yogurt protein bowl",
                                "source": "scraped_menu",
                                "menu_source": "scraped_menu",
                                "confidence": 0.72,
                                "menu_confidence": 0.72,
                            }
                        ],
                        "confidence": 0.72,
                        "sources": ["scraped_menu"],
                        "last_updated": "2026-03-01T00:00:00+00:00",
                    }
                },
            }
            self._write_store(store_path, payload)

            report = cleanup_menu_intelligence_store(store_path, dry_run=False)
            self.assertEqual(report["removed_rows"], 0)
            self.assertEqual(report["downgraded_rows"], 1)

            out = json.loads(store_path.read_text(encoding="utf-8"))
            item = out["places"]["p1"]["menu_items"][0]
            self.assertNotIn("greek yogurt protein bowl", str(item.get("item_name") or "").lower())
            self.assertEqual(item.get("menu_item_source"), "heuristic")
            self.assertEqual(item.get("source"), "heuristic_generation")
            self.assertIn(item.get("display_label"), {"Needs Menu Check", "Suggested Lighter Option", "Estimated Best Fit"})
            self.assertIn("rank_adjusted_item_score", item)
            self.assertIn("source_rank_weight", item)

    def test_cleanup_preserves_strong_real_menu_and_backfills_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "store.json"
            payload = {
                "version": "v1",
                "places": {
                    "sub-1": {
                        "place_id": "sub-1",
                        "restaurant_name": "Subway",
                        "cuisine": "sandwich shop",
                        "menu_items": [
                            {
                                "item_name": '6" Chicken Breast Sub, extra salad, no mayo',
                                "source": "website_menu",
                                "menu_source": "website_menu",
                                "confidence": 0.88,
                                "menu_confidence": 0.88,
                                "estimated_calories": 430,
                                "estimated_protein_g": 38,
                            }
                        ],
                        "confidence": 0.88,
                        "sources": ["website_menu"],
                        "last_updated": "2026-03-01T00:00:00+00:00",
                    }
                },
            }
            self._write_store(store_path, payload)

            report = cleanup_menu_intelligence_store(store_path, dry_run=False)
            self.assertEqual(report["removed_rows"], 0)
            self.assertGreaterEqual(report["backfilled_rows"], 1)

            out = json.loads(store_path.read_text(encoding="utf-8"))
            item = out["places"]["sub-1"]["menu_items"][0]
            self.assertEqual(item.get("menu_item_source"), "real_menu")
            self.assertGreaterEqual(float(item.get("source_rank_weight") or 0.0), 0.95)
            self.assertGreaterEqual(int(item.get("source_priority") or 0), 4)
            self.assertTrue(str(item.get("display_label") or "").strip())
            self.assertGreater(int(item.get("rank_adjusted_item_score") or 0), 0)


if __name__ == "__main__":
    unittest.main()

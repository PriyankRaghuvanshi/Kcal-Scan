import os
import tempfile
import unittest

from menu_intelligence_store import get_menu_items_by_place_id, get_place_menu_intelligence, ingest_menu_intelligence
from menu_item_scoring import recommend_menu_items_for_place


class MenuIntelligenceStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._old_path = os.environ.get("MENU_INTELLIGENCE_STORE_PATH")
        os.environ["MENU_INTELLIGENCE_STORE_PATH"] = os.path.join(self._tmp_dir.name, "menu_store.json")

    def tearDown(self):
        if self._old_path is None:
            os.environ.pop("MENU_INTELLIGENCE_STORE_PATH", None)
        else:
            os.environ["MENU_INTELLIGENCE_STORE_PATH"] = self._old_path
        self._tmp_dir.cleanup()

    def test_ingest_and_retrieve_by_place_id(self):
        entry = ingest_menu_intelligence(
            place_id="abc123",
            restaurant_name="Protein Bowl House",
            cuisine="healthy bowls",
            source="scraped_menu",
            menu_items=[
                {
                    "item_name": "Chicken Pesto Bowl",
                    "estimated_calories": 520,
                    "estimated_protein_g": 42,
                    "confidence": 0.78,
                }
            ],
        )

        self.assertIsInstance(entry, dict)
        self.assertEqual(entry["place_id"], "abc123")

        fetched = get_place_menu_intelligence("abc123")
        self.assertIsInstance(fetched, dict)
        self.assertEqual(fetched["restaurant_name"], "Protein Bowl House")
        self.assertEqual(len(fetched["menu_items"]), 1)

        items = get_menu_items_by_place_id("abc123")
        self.assertEqual(items[0]["item_name"], "Chicken Pesto Bowl")

    def test_scoring_uses_stored_menu_by_place_id(self):
        ingest_menu_intelligence(
            place_id="stored-1",
            restaurant_name="Stored Menu Grill",
            cuisine="grill",
            source="user_scan",
            menu_items=[
                {
                    "item_name": "Custom Scan Chicken Plate",
                    "estimated_calories": 490,
                    "estimated_protein_g": 44,
                    "estimated_satiety": "high",
                    "confidence": 0.87,
                }
            ],
        )

        out = recommend_menu_items_for_place(
            {
                "place_id": "stored-1",
                "name": "Stored Menu Grill",
                "types": ["restaurant", "grill"],
            },
            health_score=8.1,
        )

        self.assertEqual(out["menu_items_source"], "menu_intelligence_store")
        self.assertEqual(out["menu_intelligence_place_id"], "stored-1")
        self.assertTrue(out["menu_item_scoring_available"])
        self.assertEqual(out["top_item"], "Custom Scan Chicken Plate")


    def test_heuristic_generation_persists_for_place_id(self):
        place = {
            "place_id": "heur-22",
            "name": "Grill Corner",
            "types": ["restaurant", "grill"],
        }

        out = recommend_menu_items_for_place(place, health_score=7.2)
        self.assertEqual(out["menu_items_source"], "heuristic")

        stored = get_place_menu_intelligence("heur-22")
        self.assertIsInstance(stored, dict)
        self.assertGreater(len(stored.get("menu_items") or []), 0)


if __name__ == "__main__":
    unittest.main()

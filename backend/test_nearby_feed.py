import os
import tempfile
import unittest

from nearby_feed import build_healthy_nearby_feed


class NearbyFeedTests(unittest.TestCase):
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

    def test_feed_sections_exist(self):
        places = [
            {
                "name": "Protein Grill House",
                "place_id": "p1",
                "types": ["restaurant", "grill"],
                "vicinity": "Main road",
                "menu_items": [
                    {"item_name": "Chicken bowl", "estimated_calories": 540, "estimated_protein_g": 42, "estimated_satiety": "high"}
                ],
            },
            {
                "name": "Pizza Combo Spot",
                "place_id": "p2",
                "types": ["restaurant", "pizza"],
                "menu_items": [
                    {"item_name": "Large loaded pizza", "estimated_calories": 920, "estimated_protein_g": 22}
                ],
            },
            {
                "name": "Salad + Bowl Co",
                "place_id": "p3",
                "types": ["restaurant", "salad", "healthy"],
                "menu_items": [
                    {"item_name": "Salmon salad", "estimated_calories": 470, "estimated_protein_g": 36, "estimated_satiety": "high"}
                ],
            },
        ]

        out = build_healthy_nearby_feed(places, limit_per_section=3)
        self.assertIn("sections", out)
        self.assertEqual(len(out["sections"]), 4)

        titles = [s.get("title") for s in out["sections"]]
        self.assertEqual(
            titles,
            [
                "Best lunch near you",
                "Under 600 kcal nearby",
                "High protein meals nearby",
                "Best options for Cut Mode",
            ],
        )
        self.assertTrue(all(isinstance(section.get("places"), list) for section in out["sections"]))

    def test_under_600_section_filters(self):
        places = [
            {
                "name": "Lean Grill",
                "place_id": "u1",
                "types": ["restaurant", "grill"],
                "menu_items": [
                    {"item_name": "Lean chicken plate", "estimated_calories": 520, "estimated_protein_g": 40}
                ],
            },
            {
                "name": "Heavy Pizza",
                "place_id": "u2",
                "types": ["restaurant", "pizza"],
                "menu_items": [
                    {"item_name": "Large pizza combo", "estimated_calories": 980, "estimated_protein_g": 22}
                ],
            },
        ]

        out = build_healthy_nearby_feed(places, limit_per_section=5)
        section = next(s for s in out["sections"] if s["title"] == "Under 600 kcal nearby")
        self.assertTrue(all(int(p.get("estimated_calories", 9999)) <= 600 for p in section["places"]))

    def test_high_protein_section_filters(self):
        places = [
            {
                "name": "High Protein Spot",
                "place_id": "h1",
                "types": ["restaurant", "grill"],
                "menu_items": [
                    {"item_name": "Chicken + rice", "estimated_calories": 590, "estimated_protein_g": 41}
                ],
            },
            {
                "name": "Low Protein Bakery",
                "place_id": "h2",
                "types": ["restaurant", "bakery"],
                "menu_items": [
                    {"item_name": "Sweet pastry box", "estimated_calories": 560, "estimated_protein_g": 9}
                ],
            },
        ]

        out = build_healthy_nearby_feed(places, limit_per_section=5)
        section = next(s for s in out["sections"] if s["title"] == "High protein meals nearby")
        self.assertTrue(all(int(p.get("estimated_protein_g", 0)) >= 30 for p in section["places"]))


if __name__ == "__main__":
    unittest.main()

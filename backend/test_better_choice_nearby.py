import unittest

from better_choice_nearby import build_better_choice_nearby_response


class BetterChoiceNearbyTests(unittest.TestCase):
    def test_weaker_place_returns_stronger_alternatives(self):
        nearby_places = [
            {
                "name": "McDonald's Central",
                "place_id": "sel-1",
                "lat": 28.6139,
                "lng": 77.2090,
                "types": ["restaurant", "fast_food", "burger"],
                "vicinity": "Connaught Place",
                "rating": 4.0,
            },
            {
                "name": "Protein Grill House",
                "place_id": "alt-1",
                "lat": 28.6148,
                "lng": 77.2105,
                "types": ["restaurant", "meal_takeaway"],
                "vicinity": "Nearby",
                "rating": 4.4,
            },
            {
                "name": "Salad Bowl Co",
                "place_id": "alt-2",
                "lat": 28.6152,
                "lng": 77.2110,
                "types": ["restaurant", "healthy"],
                "vicinity": "Nearby",
                "rating": 4.5,
            },
        ]

        out = build_better_choice_nearby_response(
            nearby_places=nearby_places,
            selected_place_name="McDonald's",
            selected_place_id="sel-1",
            origin_lat=28.6139,
            origin_lng=77.2090,
            min_score_delta=1.0,
            limit=5,
        )

        self.assertIn("selected_place", out)
        self.assertIn("better_choices_nearby", out)
        self.assertGreater(len(out["better_choices_nearby"]), 0)

        top = out["better_choices_nearby"][0]
        self.assertGreater(int(top["health_score"]), int(out["selected_place"]["health_score"]))
        self.assertIn("best_order", top)
        self.assertIn("why_better", top)

    def test_no_good_alternatives_returns_empty_list(self):
        nearby_places = [
            {
                "name": "Burger Point",
                "place_id": "sel-2",
                "lat": 28.6139,
                "lng": 77.2090,
                "types": ["restaurant", "fast_food", "burger"],
                "vicinity": "Main",
            },
            {
                "name": "Fried Bites",
                "place_id": "alt-3",
                "lat": 28.6140,
                "lng": 77.2092,
                "types": ["restaurant", "fast_food", "fried"],
                "vicinity": "Main",
            },
        ]

        out = build_better_choice_nearby_response(
            nearby_places=nearby_places,
            selected_place_name="Burger Point",
            selected_place_id="sel-2",
            origin_lat=28.6139,
            origin_lng=77.2090,
            min_score_delta=2.2,
            limit=5,
        )

        self.assertEqual(out["better_choices_nearby"], [])
        self.assertFalse(out["better_choice_scoring_available"])

    def test_selected_place_is_not_in_alternatives(self):
        nearby_places = [
            {
                "name": "Fast Burger Hub",
                "place_id": "sel-3",
                "lat": 28.6139,
                "lng": 77.2090,
                "types": ["restaurant", "fast_food"],
            },
            {
                "name": "Fast Burger Hub",
                "place_id": "sel-3",
                "lat": 28.6139,
                "lng": 77.2090,
                "types": ["restaurant", "fast_food"],
            },
            {
                "name": "Healthy Grill Bowl",
                "place_id": "alt-4",
                "lat": 28.6146,
                "lng": 77.2101,
                "types": ["restaurant", "meal_takeaway"],
            },
        ]

        out = build_better_choice_nearby_response(
            nearby_places=nearby_places,
            selected_place_name="Fast Burger Hub",
            selected_place_id="sel-3",
            origin_lat=28.6139,
            origin_lng=77.2090,
            min_score_delta=1.0,
            limit=5,
        )

        names = [str(row.get("name") or "").lower() for row in out["better_choices_nearby"]]
        self.assertTrue(all(name != "fast burger hub" for name in names))


if __name__ == "__main__":
    unittest.main()

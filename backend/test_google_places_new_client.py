import unittest

from google_places_new_client import (
    DEFAULT_PLACES_NEARBY_URL,
    PLACES_NEARBY_FIELD_MASK,
    build_nearby_search_payload,
    map_places_new_response,
    resolve_nearby_base,
)


class GooglePlacesNewClientTests(unittest.TestCase):
    def test_resolve_nearby_base_rejects_legacy(self):
        legacy = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        self.assertEqual(resolve_nearby_base(legacy), DEFAULT_PLACES_NEARBY_URL)

    def test_payload_uses_nearby_search_new_shape(self):
        payload = build_nearby_search_payload(28.6139, 77.2090, 1200)
        self.assertIn("includedTypes", payload)
        self.assertIn("locationRestriction", payload)
        self.assertIn("circle", payload["locationRestriction"])
        self.assertIn("restaurant", payload["includedTypes"])
        self.assertIn("fast_food", payload["includedTypes"])
        self.assertIn("cafe", payload["includedTypes"])
        self.assertEqual(payload.get("rankPreference"), "DISTANCE")
        self.assertGreaterEqual(int(payload.get("maxResultCount") or 0), 40)

    def test_map_places_response_keeps_internal_shape(self):
        body = {
            "places": [
                {
                    "id": "abc123",
                    "displayName": {"text": "Protein Grill House"},
                    "formattedAddress": "Connaught Place, New Delhi",
                    "location": {"latitude": 28.63, "longitude": 77.22},
                    "rating": 4.4,
                    "userRatingCount": 120,
                    "primaryType": "restaurant",
                    "types": ["restaurant", "meal_takeaway"],
                    "businessStatus": "OPERATIONAL",
                }
            ]
        }
        out = map_places_new_response(body)
        self.assertEqual(len(out), 1)
        row = out[0]
        self.assertEqual(row["name"], "Protein Grill House")
        self.assertIn("vicinity", row)
        self.assertIn("lat", row)
        self.assertIn("lng", row)
        self.assertEqual(row["place_id"], "abc123")

    def test_field_mask_minimum_fields_present(self):
        self.assertIn("places.displayName", PLACES_NEARBY_FIELD_MASK)
        self.assertIn("places.location", PLACES_NEARBY_FIELD_MASK)
        self.assertIn("places.rating", PLACES_NEARBY_FIELD_MASK)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

# Update these imports to match your repo if needed
from chain_menu_registry import match_chain_key
from local_venue_enrichment import enrich_place_with_local_profile
from place_trace_debug import build_place_trace


def make_mock_place(name: str, place_id: str, lat: float, lng: float, vicinity: str = "") -> dict:
    return {
        "place_id": place_id,
        "place_name": name,
        "name": name,
        "lat": lat,
        "lng": lng,
        "vicinity": vicinity,
        "rating": 4.2,
        "user_ratings_total": 120,
        "price_level": 2,
        "types": ["restaurant", "food", "point_of_interest"],
    }


CHIPOTLE_PLACE = make_mock_place(
    "Chipotle Mexican Grill – SoMa",
    "mock_chipotle_001",
    37.7749,
    -122.4194,
    "San Francisco, CA",
)

FAASOS_PLACE = make_mock_place(
    "Faasos by EatSure – Indiranagar",
    "mock_faasos_001",
    12.9716,
    77.5946,
    "Bengaluru, India",
)

TACO_BELL_PLACE = make_mock_place(
    "Taco Bell – Times Square",
    "mock_tacobell_001",
    40.7580,
    -73.9855,
    "New York, NY",
)

PANERA_PLACE = make_mock_place(
    "Panera Bread Bakery Cafe",
    "mock_panera_001",
    41.8781,
    -87.6298,
    "Chicago, IL",
)

WOW_MOMO_PLACE = make_mock_place(
    "Wow! Momo – Salt Lake",
    "mock_wowmomo_001",
    22.5726,
    88.3639,
    "Kolkata, India",
)

HALDIRAMS_PLACE = make_mock_place(
    "Haldiram's Restaurant",
    "mock_haldirams_001",
    28.6139,
    77.2090,
    "Delhi, India",
)

BARBEQUE_NATION_PLACE = make_mock_place(
    "Barbeque Nation – Indiranagar",
    "mock_bbqn_001",
    12.9716,
    77.5946,
    "Bengaluru, India",
)


class TestMockChainMatching(unittest.TestCase):
    def test_match_chipotle(self):
        self.assertEqual(match_chain_key(CHIPOTLE_PLACE["place_name"]), "chipotle")

    def test_match_faasos(self):
        self.assertEqual(match_chain_key(FAASOS_PLACE["place_name"]), "faasos")

    def test_match_taco_bell(self):
        self.assertEqual(match_chain_key(TACO_BELL_PLACE["place_name"]), "taco_bell")

    def test_match_panera(self):
        self.assertEqual(match_chain_key(PANERA_PLACE["place_name"]), "panera")

    def test_match_wow_momo(self):
        self.assertEqual(match_chain_key(WOW_MOMO_PLACE["place_name"]), "wow_momo")

    def test_match_haldirams(self):
        self.assertEqual(match_chain_key(HALDIRAMS_PLACE["place_name"]), "haldirams")

    def test_match_barbeque_nation(self):
        self.assertEqual(match_chain_key(BARBEQUE_NATION_PLACE["place_name"]), "barbeque_nation")


class TestMockChainEnrichment(unittest.TestCase):
    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_chipotle_enrichment_uses_supabase_items(self, mock_get_chain_menu_items):
        mock_get_chain_menu_items.return_value = [
            {
                "item_name": "High Protein Bowl",
                "estimated_calories": 820,
                "estimated_protein_g": 60,
                "estimated_carbs_g": 55,
                "estimated_fat_g": 35,
                "confidence": 0.82,
                "last_ingested_at": "2026-03-14T10:00:00Z",
            }
        ]

        enriched = enrich_place_with_local_profile(CHIPOTLE_PLACE.copy(), market_tag="US")

        self.assertEqual(enriched.get("matched_chain_key"), "chipotle")
        self.assertEqual(enriched.get("chain_menu_store"), "supabase")
        self.assertTrue(enriched.get("supabase_chain_candidates"))

        candidate = enriched["supabase_chain_candidates"][0]
        self.assertEqual(candidate.get("menu_item_source"), "ingested_chain_item")
        self.assertEqual(candidate.get("profile_source"), "chain_menu_supabase")
        self.assertEqual(candidate.get("specificity_tier"), "exact_menu_match")

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_faasos_enrichment_uses_supabase_items(self, mock_get_chain_menu_items):
        mock_get_chain_menu_items.return_value = [
            {
                "item_name": "High Protein Chicken Wrap",
                "estimated_calories": 520,
                "estimated_protein_g": 35,
                "estimated_carbs_g": 40,
                "estimated_fat_g": 20,
                "confidence": 0.76,
                "last_ingested_at": "2026-03-14T10:00:00Z",
            }
        ]

        enriched = enrich_place_with_local_profile(FAASOS_PLACE.copy(), market_tag="IN")

        self.assertEqual(enriched.get("matched_chain_key"), "faasos")
        self.assertEqual(enriched.get("chain_menu_store"), "supabase")
        self.assertTrue(enriched.get("supabase_chain_candidates"))

        candidate = enriched["supabase_chain_candidates"][0]
        self.assertEqual(candidate.get("menu_item_source"), "ingested_chain_item")
        self.assertEqual(candidate.get("profile_source"), "chain_menu_supabase")
        self.assertEqual(candidate.get("specificity_tier"), "exact_menu_match")


class TestMockTrace(unittest.TestCase):
    def test_trace_fields_present(self):
        place = {
            "place_id": "mock_chipotle_001",
            "place_name": "Chipotle Mexican Grill – SoMa",
            "matched_chain_key": "chipotle",
            "chain_match_status": "matched",
            "chain_menu_store": "supabase",
            "menu_item_source": "ingested_chain_item",
            "profile_source": "chain_menu_supabase",
            "specificity_tier": "exact_menu_match",
            "last_ingested_at": "2026-03-14T10:00:00Z",
            "chain_menu_item_count_for_match": 5,
        }

        trace = build_place_trace(place)

        self.assertEqual(trace.get("matched_chain_key"), "chipotle")
        self.assertEqual(trace.get("chain_menu_store"), "supabase")
        self.assertEqual(trace.get("menu_item_source"), "ingested_chain_item")
        self.assertEqual(trace.get("specificity_tier"), "exact_menu_match")
        self.assertEqual(trace.get("chain_menu_item_count_for_match"), 5)


if __name__ == "__main__":
    unittest.main()

"""
Serving path: enrichment returns correct chain metadata and candidate fields
for Chipotle (US) and Faasos (IN). Uses unittest and patches get_chain_menu_items.
"""
import unittest
from unittest.mock import patch

from local_venue_enrichment import enrich_place_with_local_profile


def _make_mock_place(name: str, place_id: str, lat: float, lng: float, vicinity: str = "") -> dict:
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


CHIPOTLE_PLACE = _make_mock_place(
    "Chipotle Mexican Grill – SoMa",
    "mock_chipotle_001",
    37.7749,
    -122.4194,
    "San Francisco, CA",
)

FAASOS_PLACE = _make_mock_place(
    "Faasos by EatSure – Indiranagar",
    "mock_faasos_001",
    12.9716,
    77.5946,
    "Bengaluru, India",
)


class TestChipotleServingPath(unittest.TestCase):
    """Mock Chipotle place resolves to matched_chain_key=chipotle and correct candidate fields."""

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_chipotle_resolves_to_matched_chain_key(self, mock_get_chain_menu_items):
        mock_get_chain_menu_items.return_value = [
            {
                "item_name": "High Protein Bowl",
                "estimated_calories": 820,
                "estimated_protein_g": 60,
                "estimated_carbs_g": 55,
                "estimated_fat_g": 35,
                "confidence": 0.82,
            },
            {
                "item_name": "Green Goddess Cobb Salad with Chicken",
                "estimated_calories": 520,
                "estimated_protein_g": 40,
                "confidence": 0.86,
            },
        ]
        enriched = enrich_place_with_local_profile(CHIPOTLE_PLACE.copy(), market_tag="US")
        self.assertEqual(enriched.get("matched_chain_key"), "chipotle")

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_chipotle_candidates_have_required_fields(self, mock_get_chain_menu_items):
        mock_get_chain_menu_items.return_value = [
            {
                "item_name": "High Protein Bowl",
                "estimated_calories": 820,
                "estimated_protein_g": 60,
                "confidence": 0.82,
            },
        ]
        enriched = enrich_place_with_local_profile(CHIPOTLE_PLACE.copy(), market_tag="US")
        self.assertEqual(enriched.get("chain_menu_store"), "supabase")
        self.assertGreater(enriched.get("chain_menu_item_count_for_match", 0), 0)
        self.assertTrue(enriched.get("supabase_chain_candidates"))
        for c in enriched["supabase_chain_candidates"]:
            self.assertEqual(c.get("menu_item_source"), "ingested_chain_item")
            self.assertEqual(c.get("profile_source"), "chain_menu_supabase")
            self.assertEqual(c.get("specificity_tier"), "exact_menu_match")


class TestFaasosServingPath(unittest.TestCase):
    """Mock Faasos place resolves to matched_chain_key=faasos and correct candidate fields."""

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_faasos_resolves_to_matched_chain_key(self, mock_get_chain_menu_items):
        mock_get_chain_menu_items.return_value = [
            {
                "item_name": "High Protein Chicken Wrap",
                "estimated_calories": 520,
                "estimated_protein_g": 35,
                "confidence": 0.76,
            },
        ]
        enriched = enrich_place_with_local_profile(FAASOS_PLACE.copy(), market_tag="IN")
        self.assertEqual(enriched.get("matched_chain_key"), "faasos")

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_faasos_candidates_have_required_fields(self, mock_get_chain_menu_items):
        mock_get_chain_menu_items.return_value = [
            {
                "item_name": "High Protein Chicken Wrap",
                "estimated_calories": 520,
                "estimated_protein_g": 35,
                "confidence": 0.76,
            },
        ]
        enriched = enrich_place_with_local_profile(FAASOS_PLACE.copy(), market_tag="IN")
        self.assertEqual(enriched.get("chain_menu_store"), "supabase")
        self.assertGreater(enriched.get("chain_menu_item_count_for_match", 0), 0)
        self.assertTrue(enriched.get("supabase_chain_candidates"))
        for c in enriched["supabase_chain_candidates"]:
            self.assertEqual(c.get("menu_item_source"), "ingested_chain_item")
            self.assertEqual(c.get("profile_source"), "chain_menu_supabase")
            self.assertEqual(c.get("specificity_tier"), "exact_menu_match")


class TestChainEnrichmentFitnessOrdering(unittest.TestCase):
    """Enrichment orders chain candidates by fitness; top_menu_item is best by fat_loss_fit_score / protein."""

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_faasos_top_menu_item_favors_high_protein_over_cheese_wrap(self, mock_get_chain_menu_items):
        # Return cheese-first order; enrichment should sort so High Protein Chicken Wrap is top
        mock_get_chain_menu_items.return_value = [
            {
                "item_name": "Cheese, Spinach & Corn Wrap",
                "estimated_calories": 540,
                "estimated_protein_g": 18,
                "estimated_carbs_g": 50,
                "estimated_fat_g": 26,
                "confidence": 0.72,
                "protein_density_score": 3.33,
                "fat_loss_fit_score": 20.0,
            },
            {
                "item_name": "High Protein Chicken Wrap",
                "estimated_calories": 520,
                "estimated_protein_g": 35,
                "estimated_carbs_g": 40,
                "estimated_fat_g": 20,
                "confidence": 0.76,
                "protein_density_score": 6.73,
                "fat_loss_fit_score": 45.0,
            },
        ]
        enriched = enrich_place_with_local_profile(FAASOS_PLACE.copy(), market_tag="IN")
        self.assertIsNotNone(enriched)
        top = enriched.get("top_menu_item") or {}
        self.assertEqual(top.get("item_name"), "High Protein Chicken Wrap")
        self.assertGreater(top.get("estimated_protein_g", 0), 30)

    @patch("local_venue_enrichment.get_chain_menu_items")
    def test_chipotle_top_menu_item_favors_salad_or_high_protein_over_heavy_burrito(self, mock_get_chain_menu_items):
        mock_get_chain_menu_items.return_value = [
            {
                "item_name": "Large Burrito with Queso",
                "estimated_calories": 950,
                "estimated_protein_g": 38,
                "estimated_carbs_g": 85,
                "estimated_fat_g": 42,
                "confidence": 0.78,
                "protein_density_score": 4.0,
                "fat_loss_fit_score": 10.0,
            },
            {
                "item_name": "Green Goddess Cobb Salad with Chicken",
                "estimated_calories": 520,
                "estimated_protein_g": 40,
                "estimated_carbs_g": 25,
                "estimated_fat_g": 30,
                "confidence": 0.86,
                "protein_density_score": 7.69,
                "fat_loss_fit_score": 55.0,
            },
        ]
        enriched = enrich_place_with_local_profile(CHIPOTLE_PLACE.copy(), market_tag="US")
        self.assertIsNotNone(enriched)
        top = enriched.get("top_menu_item") or {}
        self.assertEqual(top.get("item_name"), "Green Goddess Cobb Salad with Chicken")
        self.assertLess(top.get("estimated_calories", 999), 600)


if __name__ == "__main__":
    unittest.main()

"""
Tests for Healthy Nearby fast path: shortlist, pre-rank, chain detection.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from healthy_nearby_fastpath import (
    _cheap_chain_match,
    _pre_rank_score,
    run_fast_path,
    shortlist_places,
)
from venue_intelligence_cache import get, put, has, cache_to_menu_payload
from background_enrichment_queue import enqueue, list_pending, should_enqueue_for_low_specificity


def _temp_cache_and_queue():
    """Context manager that points cache and queue at temp dirs."""
    with tempfile.TemporaryDirectory() as d:
        cache_path = os.path.join(d, "venue_cache.json")
        queue_path = os.path.join(d, "enrichment_queue.json")
        env = {
            "VENUE_INTELLIGENCE_CACHE_PATH": cache_path,
            "BACKGROUND_ENRICHMENT_QUEUE_PATH": queue_path,
        }
        return patch.dict(os.environ, env, clear=False)


class TestShortlist(unittest.TestCase):
    def test_shortlist_reduces_deep_ranked_places(self):
        places = [
            {"place_id": f"p{i}", "name": f"Place {i}", "lat": -33.8 + i * 0.01, "lng": 151.0, "types": ["restaurant"]}
            for i in range(20)
        ]
        shortlisted, skipped, debug = shortlist_places(places, shortlist_size=8, origin_lat=-33.8, origin_lng=151.0)
        self.assertEqual(len(shortlisted), 8)
        self.assertEqual(len(skipped), 12)
        self.assertEqual(debug["fetched_count"], 20)
        self.assertEqual(debug["shortlisted_count"], 8)

    def test_subway_gets_shortlisted_when_fetched(self):
        places = [
            {"place_id": "p1", "name": "Subway", "lat": -33.8, "lng": 151.0, "types": ["meal_takeaway"]},
            {"place_id": "p2", "name": "Unknown Cafe", "lat": -33.81, "lng": 151.01, "types": ["cafe"]},
        ]
        shortlisted, _, _ = shortlist_places(places, shortlist_size=5, origin_lat=-33.8, origin_lng=151.0)
        names = [p["name"] for p in shortlisted]
        self.assertIn("Subway", names)

    def test_cheap_chain_match_subway(self):
        self.assertTrue(_cheap_chain_match({"name": "Subway Westfield"}))
        self.assertTrue(_cheap_chain_match({"name": "McDonald's", "types": []}))
        self.assertFalse(_cheap_chain_match({"name": "Local Cafe", "types": []}))

    def test_pre_rank_higher_for_chain_and_close(self):
        subway = {"place_id": "s1", "name": "Subway", "lat": -33.8, "lng": 151.0, "types": ["restaurant"]}
        far_cafe = {"place_id": "c1", "name": "Random Cafe", "lat": -34.0, "lng": 152.0, "types": ["cafe"]}
        s = _pre_rank_score(subway, origin_lat=-33.8, origin_lng=151.0)
        f = _pre_rank_score(far_cafe, origin_lat=-33.8, origin_lng=151.0)
        self.assertGreater(s, f)


class TestVenueCache(unittest.TestCase):
    def test_put_and_get(self):
        with _temp_cache_and_queue():
            put("test_place_123", candidates=[
                {"item_name": "Grilled chicken", "estimated_calories": 400, "estimated_protein_g": 35},
            ], specificity_tier="chain_registry", confidence=0.9)
            entry = get("test_place_123")
        self.assertIsNotNone(entry)
        self.assertEqual(len(entry.get("candidates") or []), 1)

    def test_cache_to_menu_payload(self):
        cached = {
            "candidates": [
                {"item_name": "6-inch Sub", "estimated_calories": 380, "estimated_protein_g": 30},
            ],
            "source_type": "chain_registry",
            "confidence": 0.9,
        }
        payload = cache_to_menu_payload(cached, {})
        self.assertTrue(payload.get("from_venue_cache"))
        self.assertEqual(payload.get("top_item"), "6-inch Sub")


class TestEnrichmentQueue(unittest.TestCase):
    def test_enqueue_and_list(self):
        with _temp_cache_and_queue():
            enqueue("chIJ_subway_123", place_name="Subway", reason_enqueued="candidate_low_specificity")
            pending = list_pending(limit=5)
        self.assertGreaterEqual(len(pending), 1)

    def test_should_enqueue_for_low_specificity(self):
        self.assertTrue(should_enqueue_for_low_specificity({"chosen_candidate_specificity_tier": "generic_fallback"}))
        self.assertFalse(should_enqueue_for_low_specificity({"chosen_candidate_specificity_tier": "chain_registry"}))


class TestRunFastPath(unittest.TestCase):
    def test_run_fast_path_returns_timings_and_shortlist_debug(self):
        places = [
            {"place_id": f"p{i}", "name": f"Place {i}", "lat": -33.8, "lng": 151.0 + i * 0.001, "types": ["restaurant"]}
            for i in range(15)
        ]
        def _deep_rank(pl):
            return sorted(pl, key=lambda x: x.get("name", ""))

        scored, debug = run_fast_path(places, deep_rank_fn=_deep_rank, shortlist_size=8, origin_lat=-33.8, origin_lng=151.0)

        self.assertIn("timings", debug)
        self.assertIn("shortlist_ms", debug["timings"])
        self.assertIn("ranking_ms", debug["timings"])
        self.assertIn("total_ms", debug["timings"])
        self.assertIn("shortlist_debug", debug)
        self.assertEqual(debug["fetched_count"], 15)
        self.assertEqual(debug["shortlisted_count"], 8)
        self.assertEqual(debug["deeply_ranked_count"], 8)

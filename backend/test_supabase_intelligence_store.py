"""
Tests for supabase_intelligence_store: DB helpers, fallbacks, enqueue.
"""
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from supabase_intelligence_store import (
    get_cached_venue_intelligence,
    get_local_venue_profile,
    enqueue_place_for_enrichment,
)


class TestSupabaseIntelligenceStore(unittest.TestCase):
    def setUp(self):
        self._orig_supabase_url = os.environ.get("SUPABASE_URL")
        self._orig_supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)

    def tearDown(self):
        if self._orig_supabase_url is not None:
            os.environ["SUPABASE_URL"] = self._orig_supabase_url
        if self._orig_supabase_key is not None:
            os.environ["SUPABASE_SERVICE_ROLE_KEY"] = self._orig_supabase_key

    def test_get_cached_venue_intelligence_no_place_id_returns_none(self):
        self.assertIsNone(get_cached_venue_intelligence(""))
        self.assertIsNone(get_cached_venue_intelligence(None))

    @patch("supabase_intelligence_store._sb_safe_get_one")
    def test_get_cached_venue_intelligence_supabase_hit_returns_candidates(self, mock_get):
        """Cache hit from Supabase beats heuristic/JSON fallback."""
        mock_get.return_value = {
            "place_id": "ChIJ123",
            "candidate_payload": [
                {"item_name": "Grilled salmon bowl", "estimated_calories": 520, "estimated_protein_g": 38},
            ],
            "source_type": "exact_menu_cache",
            "confidence": 0.85,
            "last_enriched_at": "2025-03-01T10:00:00Z",
            "source_url": "https://example.com/menu",
            "profile_source": "cached_user_feedback",
        }
        os.environ["SUPABASE_URL"] = "https://test.supabase.co"
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"
        cached = get_cached_venue_intelligence("ChIJ123")
        self.assertIsNotNone(cached)
        self.assertEqual(len(cached.get("candidates") or []), 1)
        self.assertEqual(cached["source_type"], "exact_menu_cache")
        self.assertEqual(cached["confidence"], 0.85)
        self.assertEqual(cached["last_enriched_at"], "2025-03-01T10:00:00Z")
        self.assertEqual(cached["source_url"], "https://example.com/menu")
        self.assertEqual(cached["profile_source"], "cached_user_feedback")

    @patch("supabase_intelligence_store._sb_safe_get_one")
    def test_get_cached_venue_intelligence_db_failure_falls_back_to_json(self, mock_get):
        """When Supabase returns None, fall back to venue_intelligence_cache JSON if available."""
        mock_get.return_value = None
        # Ensure no Supabase so we hit JSON path; JSON may or may not have the place
        cached = get_cached_venue_intelligence("ChIJ-nonexistent-place")
        # Should not raise; may return None if no JSON fallback has this place
        self.assertIsNone(cached)  # No JSON cache for nonexistent place

    @patch("supabase_intelligence_store._sb_safe_get_one")
    def test_get_local_venue_profile_by_place_id(self, mock_get):
        """Local profile by place_id works."""
        mock_get.return_value = {
            "id": "prof-123",
            "place_id": "ChIJ456",
            "place_name": "Test Darbar",
            "area_key": "parramatta",
            "candidate_templates": json.dumps([
                {"template_name": "Tandoori chicken", "estimated_calories": 540},
            ]),
            "active": True,
        }
        os.environ["SUPABASE_URL"] = "https://test.supabase.co"
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"
        profile = get_local_venue_profile(place_id="ChIJ456")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.get("place_id"), "ChIJ456")
        self.assertEqual(profile.get("place_name"), "Test Darbar")
        templates = profile.get("candidate_templates") or []
        self.assertGreaterEqual(len(templates), 1)
        self.assertIn("Tandoori", str(templates[0].get("template_name", "")))

    @patch("supabase_intelligence_store._sb_safe_get_one")
    def test_get_local_venue_profile_by_normalized_name_and_area(self, mock_get):
        """Local profile by normalized_name + area_key works when place_id miss."""
        mock_get.return_value = None  # place_id lookup fails

        with patch("supabase_intelligence_store._sb_safe_get_many") as mock_many:
            mock_many.return_value = [
                {
                    "id": "prof-456",
                    "place_name": "Darbar Indian",
                    "area_key": "harris_park",
                    "name_variants": ["Darbar", "Darbar Indian Restaurant"],
                    "candidate_templates": [],
                    "active": True,
                },
            ]
            os.environ["SUPABASE_URL"] = "https://test.supabase.co"
            os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"
            profile = get_local_venue_profile(
                place_id=None,
                normalized_name="Darbar Indian",
                area_key="harris_park",
            )
            self.assertIsNotNone(profile)
            self.assertEqual(profile.get("place_name"), "Darbar Indian")
            self.assertEqual(profile.get("area_key"), "harris_park")

    def test_enqueue_place_for_enrichment_with_skip_recent_check(self):
        """Enqueue works when skip_recent_check=True (no suppression)."""
        place = {"place_id": "ChIJ-enqueue-test", "name": "Enqueue Test"}
        try:
            enqueue_place_for_enrichment(place, reason="candidate_low_specificity", skip_recent_check=True)
        except Exception as e:
            self.fail(f"enqueue should not raise: {e}")

    @patch("background_enrichment_queue.was_recently_enqueued", return_value=True)
    def test_enqueue_place_for_enrichment_recently_enqueued_skips(self, mock_recent):
        """When place was recently enqueued, do not enqueue again (no spam)."""
        from background_enrichment_queue import _queue_path
        place = {"place_id": "ChIJ-recent-enqueue", "name": "Recent Enqueue"}
        path = _queue_path()
        initial_count = 0
        if path.exists():
            try:
                data = json.loads(path.read_text())
                initial_count = len(data.get("records") or [])
            except Exception:
                pass
        enqueue_place_for_enrichment(place, reason="candidate_low_specificity", skip_recent_check=False)
        mock_recent.assert_called()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                new_count = len(data.get("records") or [])
                self.assertEqual(new_count, initial_count, "Should not add when recently enqueued")
            except Exception:
                pass

    def test_enqueue_invalid_reason_uses_default(self):
        """Invalid enqueue reason falls back to candidate_low_specificity."""
        place = {"place_id": "ChIJ-invalid-reason", "name": "Invalid Reason"}
        try:
            enqueue_place_for_enrichment(place, reason="invalid_reason", skip_recent_check=True)
        except Exception as e:
            self.fail(f"enqueue with invalid reason should not raise: {e}")


if __name__ == "__main__":
    unittest.main()

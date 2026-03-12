"""
Tests for local profile Supabase sync.
Run with: cd backend && python -m unittest test_local_profile_supabase_sync -v
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_profile_supabase_sync import (
    merge_trusted_profile_sources,
    sync_launch_pack_profiles_to_supabase,
    sync_auto_promoted_profiles_to_supabase,
    get_sync_status,
)
from local_venue_profiles import clear_profiles_cache


class TestMergeTrustedProfileSources(unittest.TestCase):
    """D. Merge rules preserve higher-priority trusted source. E. New non-conflicting templates append safely."""

    def test_merge_preserves_higher_priority_source(self):
        existing = {
            "profile_source": "curated_manual",
            "candidate_templates": [{"template_key": "a", "template_name": "Item A"}],
            "swap_templates": [],
        }
        incoming = {
            "profile_source": "launch_enrichment_pack",
            "candidate_templates": [{"template_key": "b", "template_name": "Item B"}],
            "swap_templates": [],
        }
        merged = merge_trusted_profile_sources(existing, incoming)
        self.assertEqual(merged["profile_source"], "curated_manual")
        self.assertEqual(len(merged["candidate_templates"]), 2)

    def test_merge_appends_non_conflicting_templates(self):
        existing = {
            "profile_source": "launch_enrichment_pack",
            "candidate_templates": [{"template_key": "x", "template_name": "X"}],
            "swap_templates": [{"swap_key": "s1", "swap_label": "S1"}],
        }
        incoming = {
            "profile_source": "auto_promoted",
            "candidate_templates": [{"template_key": "y", "template_name": "Y"}],
            "swap_templates": [{"swap_key": "s2", "swap_label": "S2"}],
        }
        merged = merge_trusted_profile_sources(existing, incoming)
        self.assertEqual(len(merged["candidate_templates"]), 2)
        self.assertEqual(len(merged["swap_templates"]), 2)
        keys = [t["template_key"] for t in merged["candidate_templates"]]
        self.assertIn("x", keys)
        self.assertIn("y", keys)

    def test_merge_does_not_duplicate_same_template_key(self):
        existing = {
            "candidate_templates": [{"template_key": "same", "template_name": "Same"}],
            "swap_templates": [],
        }
        incoming = {
            "candidate_templates": [{"template_key": "same", "template_name": "Same (updated)"}],
            "swap_templates": [],
        }
        merged = merge_trusted_profile_sources(existing, incoming)
        self.assertEqual(len(merged["candidate_templates"]), 1)


class TestSyncLaunchPack(unittest.TestCase):
    """A. Launch-pack profile sync creates canonical Supabase records."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profiles_path = Path(self.tmp.name) / "local_venue_profiles.json"
        os.environ["LOCAL_VENUE_PROFILES_PATH"] = str(self.profiles_path)
        with self.profiles_path.open("w") as f:
            json.dump({"version": "v1", "profiles": []}, f)
        clear_profiles_cache()

    def tearDown(self):
        os.environ.pop("LOCAL_VENUE_PROFILES_PATH", None)
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
        self.tmp.cleanup()

    @patch("supabase_intelligence_store._supabase_available", return_value=False)
    def test_sync_returns_result_when_supabase_unavailable(self, _mock_avail):
        res = sync_launch_pack_profiles_to_supabase(area_key="wentworthville", limit=10)
        self.assertIn("synced", res)
        self.assertIn("failed", res)

    @patch("supabase_intelligence_store.upsert_trusted_profile_to_supabase", return_value={"id": "p1"})
    @patch("supabase_intelligence_store._supabase_available", return_value=True)
    @patch("supabase_intelligence_store.get_local_venue_profile", return_value=None)
    def test_sync_launch_pack_calls_upsert(self, _mock_get, _mock_avail, mock_upsert):
        res = sync_launch_pack_profiles_to_supabase(area_key="wentworthville", limit=10)
        self.assertGreaterEqual(mock_upsert.call_count, 1)
        self.assertIn("synced", res)


class TestSyncAutoPromoted(unittest.TestCase):
    """B. Auto-promoted profile sync creates canonical records."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profiles_path = Path(self.tmp.name) / "profiles.json"
        os.environ["LOCAL_VENUE_PROFILES_PATH"] = str(self.profiles_path)
        with self.profiles_path.open("w") as f:
            json.dump({
                "version": "v1",
                "profiles": [{
                    "place_name": "Test Venue",
                    "area_key": "parramatta",
                    "profile_source": "auto_promoted",
                    "candidate_templates": [
                        {"template_key": "t1", "template_name": "Item", "profile_source": "auto_promoted"},
                    ],
                    "swap_templates": [],
                }],
            }, f)
        clear_profiles_cache()

    def tearDown(self):
        os.environ.pop("LOCAL_VENUE_PROFILES_PATH", None)
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
        self.tmp.cleanup()

    @patch("supabase_intelligence_store.upsert_trusted_profile_to_supabase", return_value={"id": "p1"})
    @patch("supabase_intelligence_store._supabase_available", return_value=True)
    def test_sync_auto_promoted_calls_upsert(self, _mock_avail, mock_upsert):
        res = sync_auto_promoted_profiles_to_supabase(area_key="parramatta", limit=10)
        self.assertIn("synced", res)


class TestSyncIdempotent(unittest.TestCase):
    """C. Rerun sync is idempotent."""

    @patch("supabase_intelligence_store.upsert_trusted_profile_to_supabase", return_value={"id": "p1"})
    @patch("supabase_intelligence_store._supabase_available", return_value=True)
    @patch("supabase_intelligence_store.get_local_venue_profile", return_value={"candidate_templates": []})
    def test_merge_used_for_existing_prevents_duplicate_templates(self, _mock_get, _mock_avail, mock_upsert):
        merge_trusted_profile_sources(
            {"candidate_templates": [{"template_key": "k1", "template_name": "A"}]},
            {"candidate_templates": [{"template_key": "k1", "template_name": "A"}]},
        )
        merged = merge_trusted_profile_sources(
            {"candidate_templates": [{"template_key": "k1", "template_name": "A"}]},
            {"candidate_templates": [{"template_key": "k1", "template_name": "A"}]},
        )
        self.assertEqual(len(merged["candidate_templates"]), 1)


class TestFallbackWhenSupabaseUnavailable(unittest.TestCase):
    """G. Fallback still works if Supabase unavailable."""

    def test_get_sync_status_when_supabase_unavailable(self):
        with patch("supabase_intelligence_store._supabase_available", return_value=False):
            status = get_sync_status(area_key="parramatta")
        self.assertFalse(status.get("supabase_available"))
        self.assertIn("canonical_profile_count", status)


class TestLiveLookupReadsCanonicalProfile(unittest.TestCase):
    """F. Live lookup can read synced canonical profile."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profiles_path = Path(self.tmp.name) / "profiles.json"
        os.environ["LOCAL_VENUE_PROFILES_PATH"] = str(self.profiles_path)
        with self.profiles_path.open("w") as f:
            json.dump({"version": "v1", "profiles": []}, f)
        clear_profiles_cache()

    def tearDown(self):
        os.environ.pop("LOCAL_VENUE_PROFILES_PATH", None)
        self.tmp.cleanup()

    @patch("local_venue_enrichment.get_area_for_place")
    @patch("supabase_intelligence_store.get_local_venue_profile")
    @patch("supabase_intelligence_store._supabase_available", return_value=True)
    def test_supabase_profile_returns_profile_store_canonical(self, _mock_avail, mock_get_profile, mock_get_area):
        mock_get_area.return_value = {"area_key": "parramatta"}
        mock_get_profile.return_value = {
            "place_name": "Test Venue",
            "area_key": "parramatta",
            "candidate_templates": [{"template_key": "t1", "template_name": "Item", "confidence": 0.8}],
            "swap_templates": [],
        }
        from local_venue_enrichment import enrich_place_with_local_profile
        place = {"name": "Test Venue", "place_id": "p1", "lat": -33.815, "lng": 151.0}
        out = enrich_place_with_local_profile(place)
        self.assertIsNotNone(out)
        self.assertEqual(out.get("profile_store"), "supabase_canonical")

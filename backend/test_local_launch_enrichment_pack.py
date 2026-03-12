"""
Tests for local launch enrichment pack.
Run with: cd backend && python -m unittest test_local_launch_enrichment_pack -v
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from launch_area_config import list_launch_areas
from local_launch_enrichment_pack import (
    list_priority_launch_areas,
    list_priority_local_venues,
    seed_launch_area_enrichment,
    seed_all_priority_launch_areas,
    get_launch_enrichment_status,
    LAUNCH_ENRICHMENT_PACK,
)
from local_venue_profiles import get_profile_by_normalized_name, _profiles_list, clear_profiles_cache


class TestLocalLaunchEnrichmentPack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profiles_path = Path(self.tmp.name) / "local_venue_profiles.json"
        os.environ["LOCAL_VENUE_PROFILES_PATH"] = str(self.profiles_path)
        with self.profiles_path.open("w") as f:
            json.dump({"version": "v1", "profiles": []}, f)
        clear_profiles_cache()

    def tearDown(self):
        os.environ.pop("LOCAL_VENUE_PROFILES_PATH", None)
        self.tmp.cleanup()

    def test_A_seed_launch_area_enrichment_returns_seeded_counts(self):
        """seed_launch_area_enrichment returns seeded counts."""
        result = seed_launch_area_enrichment("wentworthville", limit=20)
        self.assertIn("area_key", result)
        self.assertEqual(result["area_key"], "wentworthville")
        self.assertIn("venues_seeded", result)
        self.assertIn("profiles_created", result)
        self.assertIn("templates_added", result)
        self.assertIn("coverage_after", result)
        self.assertGreaterEqual(result["venues_seeded"], 1)
        self.assertGreaterEqual(result["templates_added"], 1)

    def test_B_profiles_templates_created_for_target_venues(self):
        """Profiles and templates are created for target venues."""
        seed_launch_area_enrichment("wentworthville", limit=20)
        profile = get_profile_by_normalized_name("Raj's Curry House", "wentworthville")
        self.assertIsNotNone(profile)
        templates = profile.get("candidate_templates") or []
        self.assertGreaterEqual(len(templates), 2)
        template_names = [t.get("template_name") for t in templates]
        self.assertTrue(any("Tandoori" in str(n) for n in template_names))
        self.assertTrue(any("Paneer" in str(n) or "Dal" in str(n) for n in template_names))

    def test_C_diet_safe_variants_represented(self):
        """Diet-safe variants can be represented."""
        seed_launch_area_enrichment("wentworthville", limit=20)
        profile = get_profile_by_normalized_name("Raj's Curry House", "wentworthville")
        self.assertIsNotNone(profile)
        templates = profile.get("candidate_templates") or []
        veg_templates = [t for t in templates if t.get("vegetarian_possible")]
        vegan_templates = [t for t in templates if t.get("vegan_possible")]
        self.assertGreaterEqual(len(veg_templates), 1)
        self.assertGreaterEqual(len(vegan_templates), 1)

    def test_D_launch_readiness_coverage_reflects_seeded_profiles(self):
        """Launch-readiness coverage reflects seeded profiles."""
        from local_venue_enrichment import summarize_launch_area_coverage

        seed_launch_area_enrichment("wentworthville", limit=20)
        coverage = summarize_launch_area_coverage("wentworthville")
        self.assertIn("pack_seeded_profiles", coverage)
        self.assertGreaterEqual(coverage.get("pack_seeded_profiles", 0), 1)
        self.assertGreaterEqual(coverage.get("total_seeded_profiles", 0), 1)

    def test_E_generic_fallback_reduced_when_enriched_profile_available(self):
        """Generic fallback is reduced when enriched local profile is available."""
        seed_launch_area_enrichment("wentworthville", limit=20)
        profile = get_profile_by_normalized_name("Raj's Curry House", "wentworthville")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.get("specificity_tier"), "enriched_local_profile")
        self.assertIn("candidate_templates", profile)
        candidates = profile.get("candidate_templates") or []
        self.assertTrue(all("template_name" in t for t in candidates))
        for t in candidates:
            name = str(t.get("template_name") or "").lower()
            self.assertNotIn("lighter menu option", name)
            self.assertNotIn("healthy option", name)
            self.assertNotIn("protein bowl", name)

    def test_list_priority_launch_areas(self):
        """list_priority_launch_areas returns area keys."""
        areas = list_priority_launch_areas(limit=5)
        self.assertIsInstance(areas, list)
        self.assertGreaterEqual(len(areas), 1)
        self.assertIn("wentworthville", areas)

    def test_list_priority_local_venues(self):
        """list_priority_local_venues returns venue definitions."""
        venues = list_priority_local_venues("parramatta", limit=10)
        self.assertIsInstance(venues, list)
        if venues:
            v = venues[0]
            self.assertIn("place_name", v)
            self.assertIn("candidate_templates", v)
            self.assertIn("area_key", v)

    def test_seed_all_priority_launch_areas(self):
        """seed_all_priority_launch_areas returns aggregated summary."""
        result = seed_all_priority_launch_areas(limit_areas=2, limit_per_area=10)
        self.assertIn("areas_seeded", result)
        self.assertIn("total_profiles_created", result)
        self.assertIn("area_results", result)
        self.assertIn("coverage_summary", result)


if __name__ == "__main__":
    unittest.main()

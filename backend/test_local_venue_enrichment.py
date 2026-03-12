"""
Tests for local venue enrichment: profiles, launch areas, coverage, trace.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from launch_area_config import (
    get_launch_area,
    is_place_in_launch_area,
    list_launch_areas,
)
from local_venue_profiles import (
    get_profile_by_place_id,
    get_profile_by_normalized_name,
    match_local_profile,
    profile_to_candidates,
    validate_profile_schema,
)
from local_venue_enrichment import (
    enrich_place_with_local_profile,
    get_local_profile_for_place,
    summarize_launch_area_coverage,
    list_high_priority_local_venues,
)


def _profiles_path_override(profiles_json: dict):
    """Point profiles at a temp file."""
    import local_venue_profiles as lvp
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w") as f:
        json.dump(profiles_json, f)
    return os.environ.get("LOCAL_VENUE_PROFILES_PATH"), path


class TestLaunchAreaConfig(unittest.TestCase):
    def test_list_launch_areas(self):
        areas = list_launch_areas()
        self.assertGreater(len(areas), 5)
        keys = [a.get("area_key") for a in areas]
        self.assertIn("parramatta", keys)
        self.assertIn("harris_park", keys)

    def test_get_launch_area(self):
        a = get_launch_area("parramatta")
        self.assertIsNotNone(a)
        self.assertEqual(a.get("display_name"), "Parramatta")
        self.assertAlmostEqual(float(a.get("center_lat")), -33.815, places=2)

    def test_is_place_in_launch_area(self):
        in_area = is_place_in_launch_area(-33.815, 151.0)  # Parramatta
        self.assertIsNotNone(in_area)
        self.assertEqual(in_area.get("area_key"), "parramatta")

    def test_is_place_outside_launch_area(self):
        out = is_place_in_launch_area(-34.0, 151.2)
        self.assertIsNone(out)


class TestLocalVenueProfiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.profiles = {
            "version": "v1",
            "profiles": [
                {
                    "place_id": "ChIJ123",
                    "place_name": "Test Darbar",
                    "normalized_name": "test darbar",
                    "area_key": "parramatta",
                    "coverage_status": "strong",
                    "profile_source": "curated_manual",
                    "specificity_tier": "enriched_local_profile",
                    "active": True,
                    "candidate_templates": [
                        {
                            "template_key": "t1",
                            "template_name": "Tandoori chicken + dal",
                            "estimated_calories": 520,
                            "estimated_protein_g": 42,
                            "confidence": 0.88,
                        }
                    ],
                    "swap_templates": [
                        {"swap_key": "no_naan", "swap_label": "No naan", "swap_type": "side_omit", "calories_delta": -180}
                    ],
                }
            ],
        }
        with open(self.tmp.name, "w") as f:
            json.dump(self.profiles, f)
        self._orig = os.environ.get("LOCAL_VENUE_PROFILES_PATH")
        os.environ["LOCAL_VENUE_PROFILES_PATH"] = self.tmp.name

    def tearDown(self):
        if self._orig is not None:
            os.environ["LOCAL_VENUE_PROFILES_PATH"] = self._orig
        else:
            os.environ.pop("LOCAL_VENUE_PROFILES_PATH", None)
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_get_profile_by_place_id(self):
        import local_venue_profiles as lvp
        lvp.clear_profiles_cache()
        p = get_profile_by_place_id("ChIJ123")
        self.assertIsNotNone(p)
        self.assertEqual(p.get("place_name"), "Test Darbar")

    def test_get_profile_by_normalized_name(self):
        import local_venue_profiles as lvp
        lvp.clear_profiles_cache()
        p = get_profile_by_normalized_name("Test Darbar", "parramatta")
        self.assertIsNotNone(p)
        self.assertEqual(p.get("place_name"), "Test Darbar")

    def test_match_local_profile(self):
        import local_venue_profiles as lvp
        lvp.clear_profiles_cache()
        place = {"place_id": "ChIJ123", "name": "Test Darbar", "lat": -33.815, "lng": 151.0}
        p = match_local_profile(place, area_key="parramatta")
        self.assertIsNotNone(p)

    def test_profile_to_candidates(self):
        p = self.profiles["profiles"][0]
        cands = profile_to_candidates(p)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["item_name"], "Tandoori chicken + dal")
        self.assertEqual(cands[0]["menu_item_source"], "enriched_local_profile")

    def test_validate_profile_schema(self):
        errs = validate_profile_schema({"place_name": "X", "area_key": "y", "candidate_templates": [{"template_name": "a"}]})
        self.assertEqual(errs, [])


class TestLocalVenueEnrichment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.profiles = {
            "version": "v1",
            "profiles": [
                {
                    "place_id": "",
                    "place_name": "Darbar",
                    "normalized_name": "darbar",
                    "name_variants": ["Darbar", "Darbar Indian"],
                    "area_key": "parramatta",
                    "coverage_status": "strong",
                    "profile_source": "curated_manual",
                    "specificity_tier": "enriched_local_profile",
                    "active": True,
                    "candidate_templates": [
                        {"template_key": "t1", "template_name": "Tandoori chicken half + dal", "estimated_calories": 520, "estimated_protein_g": 42, "confidence": 0.88}
                    ],
                    "swap_templates": [],
                }
            ],
        }
        with open(self.tmp.name, "w") as f:
            json.dump(self.profiles, f)
        self._orig = os.environ.get("LOCAL_VENUE_PROFILES_PATH")
        os.environ["LOCAL_VENUE_PROFILES_PATH"] = self.tmp.name

    def tearDown(self):
        if self._orig is not None:
            os.environ["LOCAL_VENUE_PROFILES_PATH"] = self._orig
        else:
            os.environ.pop("LOCAL_VENUE_PROFILES_PATH", None)
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_enrich_place_in_launch_area(self):
        from launch_area_config import get_area_for_place

        import local_venue_profiles as lvp
        lvp.clear_profiles_cache()
        # Parramatta center - matches area_key parramatta from profile
        place = {"name": "Darbar", "place_id": "x", "lat": -33.815, "lng": 151.0}
        area = get_area_for_place(place)
        self.assertIsNotNone(area, "Place should be in a launch area")
        self.assertEqual(area.get("area_key"), "parramatta")
        profile = match_local_profile(place, area_key=area["area_key"])
        self.assertIsNotNone(profile, "Should match Darbar in parramatta")
        out = enrich_place_with_local_profile(place)
        self.assertIsNotNone(out)
        self.assertEqual(out.get("menu_items_source"), "enriched_local_profile")
        self.assertIn("Tandoori chicken half + dal", str(out.get("candidates", [])))

    def test_enrich_place_outside_launch_area(self):
        import local_venue_profiles as lvp
        lvp.clear_profiles_cache()
        place = {"name": "Darbar", "lat": -34.5, "lng": 150.5}
        out = enrich_place_with_local_profile(place)
        self.assertIsNone(out)

    def test_summarize_launch_area_coverage(self):
        import local_venue_profiles as lvp
        lvp.clear_profiles_cache()
        s = summarize_launch_area_coverage("parramatta")
        self.assertIn("total_seeded_profiles", s)
        self.assertIn("strong_profiles", s)
        self.assertGreaterEqual(s["total_seeded_profiles"], 0)

    def test_list_high_priority_local_venues(self):
        import local_venue_profiles as lvp
        lvp.clear_profiles_cache()
        venues = list_high_priority_local_venues("parramatta")
        self.assertIsInstance(venues, list)


class TestEnrichedOutranksGeneric(unittest.TestCase):
    """Enriched local profile should outrank generic fallback when scores close."""

    def test_specificity_tier_preference(self):
        from place_trace_debug import get_specificity_bonus_100, TIER_ENRICHED_LOCAL_PROFILE, TIER_GENERIC_FALLBACK
        enriched_bonus = get_specificity_bonus_100(TIER_ENRICHED_LOCAL_PROFILE)
        generic_bonus = get_specificity_bonus_100(TIER_GENERIC_FALLBACK)
        self.assertGreater(enriched_bonus, generic_bonus)
        self.assertEqual(enriched_bonus, 4)
        self.assertEqual(generic_bonus, -4)

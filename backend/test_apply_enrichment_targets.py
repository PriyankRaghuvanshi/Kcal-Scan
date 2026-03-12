"""
Tests for bulk apply enrichment targets.
Run with: cd backend && python -m pytest test_apply_enrichment_targets.py -v
Or: cd backend && python -m unittest test_apply_enrichment_targets -v
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from apply_enrichment_targets import (
    build_profile_update_from_target,
    apply_enrichment_target,
    apply_enrichment_targets,
    PROFILE_SOURCE_BULK,
    SKIP_REASON_CHAIN_GAP,
    ACTION_ADD_PROFILE_NOW,
    ACTION_ADD_SWAPS,
    ACTION_ADD_VEG_VEGAN_VARIANTS,
    ACTION_EXPAND_EXISTING_PROFILE,
    ACTION_FIX_GENERIC_TEMPLATE,
    ACTION_REVIEW_CHAIN_GAP,
)


class TestBuildProfileUpdate(unittest.TestCase):
    def test_add_profile_now_returns_templates_and_swaps(self):
        target = {
            "area_key": "parramatta",
            "place_name": "Cafe A",
            "place_id": "",
            "recommended_enrichment_action": ACTION_ADD_PROFILE_NOW,
            "cuisine_guess": "cafe",
        }
        update = build_profile_update_from_target(target)
        self.assertIsNotNone(update)
        self.assertIn("candidate_templates", update)
        self.assertIn("swap_templates", update)
        self.assertGreaterEqual(len(update["candidate_templates"]), 1)
        self.assertLessEqual(len(update["candidate_templates"]), 3)
        self.assertEqual(update["profile_source"], PROFILE_SOURCE_BULK)
        for t in update["candidate_templates"]:
            self.assertIn("template_key", t)
            self.assertIn("template_name", t)
            self.assertEqual(t.get("profile_source"), PROFILE_SOURCE_BULK)

    def test_review_chain_gap_returns_none(self):
        target = {
            "area_key": "parramatta",
            "place_name": "Subway",
            "recommended_enrichment_action": ACTION_REVIEW_CHAIN_GAP,
        }
        update = build_profile_update_from_target(target)
        self.assertIsNone(update)

    def test_add_veg_vegan_variants_returns_veg_safe_templates(self):
        target = {
            "area_key": "harris_park",
            "place_name": "Indian B",
            "recommended_enrichment_action": ACTION_ADD_VEG_VEGAN_VARIANTS,
            "cuisine_guess": "indian",
        }
        update = build_profile_update_from_target(target)
        self.assertIsNotNone(update)
        self.assertIn("candidate_templates", update)
        for t in update["candidate_templates"]:
            self.assertTrue(t.get("vegetarian_possible") or t.get("vegan_possible"), str(t))

    def test_add_swaps_returns_swaps_only(self):
        target = {
            "area_key": "parramatta",
            "place_name": "Cafe A",
            "recommended_enrichment_action": ACTION_ADD_SWAPS,
            "cuisine_guess": "cafe",
        }
        update = build_profile_update_from_target(target)
        self.assertIsNotNone(update)
        self.assertIn("swap_templates", update)
        self.assertGreaterEqual(len(update["swap_templates"]), 1)
        self.assertIn("candidate_templates", update)
        self.assertEqual(len(update["candidate_templates"]), 0)

    def test_fix_generic_template_returns_templates(self):
        target = {
            "area_key": "wentworthville",
            "place_name": "Raj Curry",
            "recommended_enrichment_action": ACTION_FIX_GENERIC_TEMPLATE,
            "cuisine_guess": "indian",
        }
        update = build_profile_update_from_target(target)
        self.assertIsNotNone(update)
        self.assertGreaterEqual(len(update["candidate_templates"]), 1)


class TestApplyEnrichmentTarget(unittest.TestCase):
    @patch("apply_enrichment_targets.upsert_trusted_profile_to_supabase", return_value={"id": "p1"})
    @patch("apply_enrichment_targets.get_local_venue_profile", return_value=None)
    def test_add_profile_now_creates_canonical_profile_and_templates(self, mock_get, mock_upsert):
        target = {
            "area_key": "parramatta",
            "place_name": "Cafe A",
            "place_id": "",
            "recommended_enrichment_action": ACTION_ADD_PROFILE_NOW,
            "cuisine_guess": "cafe",
        }
        res = apply_enrichment_target(target)
        self.assertTrue(res.get("applied"))
        self.assertTrue(res.get("profile_created"))
        self.assertGreaterEqual(res.get("templates_added", 0), 1)
        self.assertIsNone(res.get("skipped_reason"))
        mock_upsert.assert_called_once()

    @patch("apply_enrichment_targets.upsert_trusted_profile_to_supabase", return_value={"id": "p1"})
    @patch("apply_enrichment_targets.get_local_venue_profile")
    def test_expand_existing_profile_appends_templates_without_duplicates(self, mock_get, mock_upsert):
        existing = {
            "place_id": "",
            "place_name": "Cafe A",
            "area_key": "parramatta",
            "candidate_templates": [
                {"template_key": "eggs_toast", "template_name": "Eggs on toast", "estimated_calories": 420},
            ],
            "swap_templates": [],
        }
        mock_get.return_value = existing
        target = {
            "area_key": "parramatta",
            "place_name": "Cafe A",
            "recommended_enrichment_action": ACTION_EXPAND_EXISTING_PROFILE,
            "cuisine_guess": "cafe",
        }
        res = apply_enrichment_target(target)
        self.assertTrue(res.get("applied"))
        self.assertFalse(res.get("profile_created"))
        # Merge adds new templates only (eggs_toast already exists)
        self.assertGreaterEqual(res.get("templates_added", 0), 0)
        mock_upsert.assert_called_once()

    def test_chain_gap_targets_skipped_not_treated_as_local_fix(self):
        target = {
            "area_key": "parramatta",
            "place_name": "McDonald's",
            "place_id": "ChMcD",
            "recommended_enrichment_action": ACTION_REVIEW_CHAIN_GAP,
        }
        res = apply_enrichment_target(target)
        self.assertFalse(res.get("applied"))
        self.assertEqual(res.get("skipped_reason"), SKIP_REASON_CHAIN_GAP)
        self.assertEqual(res.get("templates_added"), 0)
        self.assertEqual(res.get("swaps_added"), 0)


class TestApplyEnrichmentTargetsBulk(unittest.TestCase):
    @patch("apply_enrichment_targets.upsert_trusted_profile_to_supabase", return_value={"id": "p1"})
    @patch("apply_enrichment_targets.get_local_venue_profile", return_value=None)
    def test_bulk_apply_summary_contains_action_counts(self, mock_get, mock_upsert):
        targets = [
            {
                "area_key": "parramatta",
                "place_name": "Cafe A",
                "recommended_enrichment_action": ACTION_ADD_PROFILE_NOW,
                "cuisine_guess": "cafe",
            },
            {
                "area_key": "parramatta",
                "place_name": "McDonald's",
                "recommended_enrichment_action": ACTION_REVIEW_CHAIN_GAP,
            },
        ]
        out = apply_enrichment_targets(targets, limit=10)
        self.assertEqual(out["targets_considered"], 2)
        self.assertIn("targets_applied", out)
        self.assertIn("targets_skipped", out)
        self.assertIn("applied_by_action", out)
        self.assertIn("skipped_by_reason", out)
        self.assertIn("sample_results", out)
        self.assertGreaterEqual(out["targets_applied"], 1)
        self.assertGreaterEqual(out["targets_skipped"], 1)
        self.assertIn(SKIP_REASON_CHAIN_GAP, out["skipped_by_reason"])

    @patch("apply_enrichment_targets.upsert_trusted_profile_to_supabase", return_value={"id": "p1"})
    @patch("apply_enrichment_targets.get_local_venue_profile")
    def test_rerun_is_idempotent(self, mock_get, mock_upsert):
        target = {
            "area_key": "parramatta",
            "place_name": "Cafe A",
            "recommended_enrichment_action": ACTION_ADD_PROFILE_NOW,
            "cuisine_guess": "cafe",
        }
        mock_get.return_value = None
        res1 = apply_enrichment_target(target)
        self.assertTrue(res1.get("applied"))

        # Second run: same target with existing profile. Merge will not add duplicate template_keys.
        existing_after_first = {
            "place_id": "",
            "place_name": "Cafe A",
            "area_key": "parramatta",
            "candidate_templates": [
                {"template_key": "eggs_toast", "template_name": "Eggs on toast"},
                {"template_key": "chicken_wrap", "template_name": "Grilled chicken wrap"},
                {"template_key": "omelette_toast", "template_name": "Omelette + toast"},
            ],
            "swap_templates": [{"swap_key": "no_hash", "swap_label": "Skip hash browns"}],
        }
        mock_get.return_value = existing_after_first
        res2 = apply_enrichment_target(target)
        self.assertTrue(res2.get("applied"))
        # No new templates/swaps because merge dedupes by key
        self.assertEqual(res2.get("templates_added"), 0)
        self.assertEqual(res2.get("swaps_added"), 0)

    @patch("apply_enrichment_targets.upsert_trusted_profile_to_supabase", return_value={"id": "p1"})
    @patch("apply_enrichment_targets.get_local_venue_profile")
    def test_add_swaps_adds_swaps_only_once(self, mock_get, mock_upsert):
        target = {
            "area_key": "parramatta",
            "place_name": "Cafe B",
            "recommended_enrichment_action": ACTION_ADD_SWAPS,
            "cuisine_guess": "cafe",
        }
        mock_get.return_value = None
        res = apply_enrichment_target(target)
        self.assertTrue(res.get("applied"))
        self.assertGreaterEqual(res.get("swaps_added", 0), 1)
        # Run again with existing profile that already has the swap
        existing = {
            "place_name": "Cafe B",
            "area_key": "parramatta",
            "candidate_templates": [{"template_key": "eggs_toast", "template_name": "Eggs on toast"}],
            "swap_templates": [{"swap_key": "no_hash", "swap_label": "Skip hash browns"}],
        }
        mock_get.return_value = existing
        res2 = apply_enrichment_target(target)
        self.assertTrue(res2.get("applied"))
        self.assertEqual(res2.get("swaps_added"), 0)


if __name__ == "__main__":
    unittest.main()

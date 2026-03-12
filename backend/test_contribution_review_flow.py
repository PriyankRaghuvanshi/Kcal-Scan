"""
Tests for contribution review flow: list, approve, reject, audit.
"""
from __future__ import annotations

import contextlib
import os
import tempfile
import unittest

from user_venue_contributions import (
    create_contribution,
    get_contribution,
    list_pending,
    update_contribution_status,
    STATUS_ACCEPTED,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from contribution_review_flow import (
    list_pending_contributions,
    get_contribution_review_bundle,
    approve_contribution,
    reject_contribution,
    ACTION_ACCEPT_AS_NEW_TEMPLATE,
    ACTION_ACCEPT_AS_SWAP,
    ACTION_REJECT,
)
from local_venue_profiles import get_profile_by_normalized_name, add_candidate_template


@contextlib.contextmanager
def _tmp_store(store_name: str):
    """Context manager to use a temp JSON store for tests."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.environ[store_name] = path
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)
        os.environ.pop(store_name, None)


class TestContributionReviewFlow(unittest.TestCase):
    def setUp(self):
        self.contrib_store = None
        self.profiles_store = None

    def test_list_pending_contributions(self):
        """A. list pending contributions."""
        with _tmp_store("USER_VENUE_CONTRIBUTIONS_PATH"):
            create_contribution(
                place_name="Test Cafe",
                area_key="parramatta",
                contribution_type="better_order_suggestion",
                payload={"suggested_order": "Avocado toast"},
            )
            create_contribution(
                place_name="Other Place",
                area_key="harris_park",
                contribution_type="vegetarian_option_missing",
                payload={},
            )
            pending = list_pending_contributions(limit=50)
            self.assertGreaterEqual(len(pending), 2)
            names = [c.get("place_name") for c in pending]
            self.assertIn("Test Cafe", names)
            area_filtered = list_pending_contributions(area_key="parramatta", limit=50)
            self.assertEqual(len([c for c in area_filtered if c.get("place_name") == "Test Cafe"]), 1)

    def test_approve_better_order_suggestion_inserts_template(self):
        """B. approve better_order_suggestion -> inserts new local template."""
        with _tmp_store("USER_VENUE_CONTRIBUTIONS_PATH"), _tmp_store("LOCAL_VENUE_PROFILES_PATH"):
            contrib = create_contribution(
                place_name="Darbar",
                area_key="harris_park",
                contribution_type="better_order_suggestion",
                payload={"suggested_order": "Paneer tikka + dal"},
            )
            cid = contrib["contribution_id"]
            result = approve_contribution(
                cid,
                reviewer_id="admin_1",
                action_payload={
                    "action_type": ACTION_ACCEPT_AS_NEW_TEMPLATE,
                    "template_payload": {
                        "template_key": "paneer_tikka_dal",
                        "template_name": "Paneer tikka + dal",
                        "estimated_calories": 620,
                        "estimated_protein_g": 31,
                        "cut_friendly": True,
                        "food_quality_tags": ["high_protein"],
                        "diet_tags": ["vegetarian"],
                    },
                    "reviewer_notes": "Plausible for this venue",
                },
            )
            self.assertEqual(result.get("outcome"), "accepted")
            self.assertTrue(result.get("applied_changes", {}).get("add_template"))
            updated = get_contribution(cid)
            self.assertEqual(updated.get("status"), STATUS_ACCEPTED)
            profile = get_profile_by_normalized_name("Darbar", "harris_park")
            self.assertIsNotNone(profile)
            names = [t.get("template_name") for t in profile.get("candidate_templates") or []]
            self.assertIn("Paneer tikka + dal", names)

    def test_approve_vegan_option_missing_creates_vegan_safe_template(self):
        """C. approve vegan_option_missing -> creates vegan-safe template."""
        with _tmp_store("USER_VENUE_CONTRIBUTIONS_PATH"), _tmp_store("LOCAL_VENUE_PROFILES_PATH"):
            contrib = create_contribution(
                place_name="Jasmine Indian",
                area_key="parramatta",
                contribution_type="vegan_option_missing",
                payload={"suggested_order": "Dal + roti, no ghee"},
            )
            cid = contrib["contribution_id"]
            result = approve_contribution(
                cid,
                reviewer_id="admin_1",
                action_payload={
                    "action_type": ACTION_ACCEPT_AS_NEW_TEMPLATE,
                    "template_payload": {
                        "template_key": "dal_roti_vegan",
                        "template_name": "Dal + roti (no ghee)",
                        "estimated_calories": 480,
                        "estimated_protein_g": 16,
                        "diet_tags": ["vegan"],
                    },
                    "reviewer_notes": "Vegan-safe option",
                },
            )
            self.assertEqual(result.get("outcome"), "accepted")
            self.assertTrue(result.get("applied_changes", {}).get("add_template"))
            profile = get_profile_by_normalized_name("Jasmine Indian", "parramatta")
            self.assertIsNotNone(profile)
            vegan_templates = [
                t for t in profile.get("candidate_templates") or []
                if t.get("vegan_possible") or "vegan" in (t.get("diet_tags") or [])
            ]
            self.assertGreater(len(vegan_templates), 0)

    def test_reject_contribution_updates_status_only(self):
        """D. reject contribution updates status only."""
        with _tmp_store("USER_VENUE_CONTRIBUTIONS_PATH"):
            contrib = create_contribution(
                place_name="Unknown Place",
                area_key="parramatta",
                contribution_type="better_order_suggestion",
                payload={"suggested_order": "Vague suggestion"},
            )
            cid = contrib["contribution_id"]
            result = reject_contribution(
                cid,
                reviewer_id="admin_1",
                reviewer_notes="Too vague / insufficient evidence",
            )
            self.assertEqual(result.get("outcome"), "rejected")
            updated = get_contribution(cid)
            self.assertEqual(updated.get("status"), STATUS_REJECTED)
            self.assertIn("vague", (updated.get("reviewer_notes") or "").lower())

    def test_approve_item_not_on_menu_can_deactivate(self):
        """E. approve item_not_on_menu can deactivate or lower confidence safely."""
        with _tmp_store("USER_VENUE_CONTRIBUTIONS_PATH"), _tmp_store("LOCAL_VENUE_PROFILES_PATH"):
            add_candidate_template(
                place_id="",
                place_name="Test Deactivate",
                area_key="parramatta",
                template={"template_key": "old_item", "template_name": "Old item not on menu", "estimated_calories": 500},
            )
            contrib = create_contribution(
                place_name="Test Deactivate",
                area_key="parramatta",
                contribution_type="item_not_on_menu",
                payload={"item_key": "old_item", "item_name": "Old item not on menu"},
            )
            cid = contrib["contribution_id"]
            result = approve_contribution(
                cid,
                reviewer_id="admin_1",
                action_payload={
                    "action_type": "accept_mark_inaccurate_previous",
                    "template_payload": {"template_key": "old_item", "notes": "Not on menu"},
                },
            )
            self.assertEqual(result.get("outcome"), "accepted")
            self.assertTrue(result.get("applied_changes", {}).get("mark_inactive"))

    def test_review_bundle_includes_profile_and_related(self):
        """Review bundle contains contribution, profile, templates, related."""
        with _tmp_store("USER_VENUE_CONTRIBUTIONS_PATH"), _tmp_store("LOCAL_VENUE_PROFILES_PATH"):
            contrib = create_contribution(
                place_name="Darbar",
                area_key="harris_park",
                contribution_type="better_order_suggestion",
                payload={"suggested_order": "Paneer wrap"},
            )
            bundle = get_contribution_review_bundle(contrib["contribution_id"])
            self.assertNotIn("error", bundle)
            self.assertEqual(bundle.get("place_name"), "Darbar")
            self.assertEqual(bundle.get("area_key"), "harris_park")
            self.assertIn("contribution", bundle)
            self.assertIn("contribution_count_for_place", bundle)
            self.assertIn("pending_count_for_place", bundle)

    def test_review_audit_trail_created(self):
        """F. review audit trail created."""
        with _tmp_store("USER_VENUE_CONTRIBUTIONS_PATH"), _tmp_store(
            "LOCAL_VENUE_PROFILES_PATH"
        ), _tmp_store("CONTRIBUTION_REVIEW_AUDIT_PATH"):
            contrib = create_contribution(
                place_name="Audit Test",
                area_key="parramatta",
                contribution_type="better_order_suggestion",
                payload={"suggested_order": "Test order"},
            )
            result = approve_contribution(
                contrib["contribution_id"],
                reviewer_id="admin_1",
                action_payload={
                    "action_type": ACTION_ACCEPT_AS_NEW_TEMPLATE,
                    "template_payload": {
                        "template_key": "test_audit",
                        "template_name": "Test order",
                        "estimated_calories": 400,
                    },
                },
            )
            self.assertEqual(result.get("outcome"), "accepted")
            self.assertIn("review_id", result)
            import json
            audit_path = os.environ.get("CONTRIBUTION_REVIEW_AUDIT_PATH")
            if audit_path and os.path.exists(audit_path):
                with open(audit_path, "r") as f:
                    audit = json.load(f)
                reviews = audit.get("reviews") or []
                self.assertGreater(len(reviews), 0)
                last = reviews[-1]
                self.assertEqual(last.get("contribution_id"), contrib["contribution_id"])
                self.assertEqual(last.get("action_type"), ACTION_ACCEPT_AS_NEW_TEMPLATE)
                self.assertIn("applied_changes", last)

    def test_existing_profile_not_destructively_overwritten(self):
        """G. existing profile not destructively overwritten."""
        with _tmp_store("USER_VENUE_CONTRIBUTIONS_PATH"), _tmp_store("LOCAL_VENUE_PROFILES_PATH"):
            add_candidate_template(
                place_id="",
                place_name="Existing Venue",
                area_key="harris_park",
                template={"template_key": "original", "template_name": "Original template", "estimated_calories": 500},
            )
            profile_before = get_profile_by_normalized_name("Existing Venue", "harris_park")
            orig_templates = list(profile_before.get("candidate_templates") or [])
            self.assertEqual(len(orig_templates), 1)
            contrib = create_contribution(
                place_name="Existing Venue",
                area_key="harris_park",
                contribution_type="better_order_suggestion",
                payload={"suggested_order": "New option"},
            )
            approve_contribution(
                contrib["contribution_id"],
                reviewer_id="admin_1",
                action_payload={
                    "action_type": ACTION_ACCEPT_AS_NEW_TEMPLATE,
                    "template_payload": {
                        "template_key": "new_option",
                        "template_name": "New option",
                        "estimated_calories": 450,
                    },
                },
            )
            profile_after = get_profile_by_normalized_name("Existing Venue", "harris_park")
            after_templates = profile_after.get("candidate_templates") or []
            self.assertEqual(len(after_templates), 2)
            self.assertTrue(any(t.get("template_key") == "original" for t in after_templates))
            self.assertTrue(any(t.get("template_key") == "new_option" for t in after_templates))


if __name__ == "__main__":
    unittest.main()

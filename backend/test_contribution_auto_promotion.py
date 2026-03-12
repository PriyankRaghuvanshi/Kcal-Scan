"""
Tests for contribution auto-promotion pipeline.
Run with: cd backend && python -m pytest test_contribution_auto_promotion.py -v
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from user_venue_contributions import (
    create_contribution,
    _load_store,
    _save_store,
    _store_path,
    CONTRIBUTION_VERSION,
    list_all_contributions,
)
from contribution_auto_promotion import (
    normalize_contribution_signature,
    aggregate_contributions_for_place,
    score_contribution_evidence,
    should_auto_promote,
    auto_promote_contribution_group,
    run_auto_promotion_for_place,
    PROMOTION_THRESHOLD,
)
from local_venue_profiles import (
    get_profile_by_place_id,
    get_profile_by_normalized_name,
    match_local_profile,
    _profiles_path,
    _load_raw,
    clear_profiles_cache,
)


def _empty_contrib_store():
    return {"version": CONTRIBUTION_VERSION, "contributions": []}


def _empty_profiles():
    return {"version": "v1", "profiles": []}


class TestContributionAutoPromotion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.contrib_path = Path(self.tmp.name) / "contributions.json"
        self.profiles_path = Path(self.tmp.name) / "profiles.json"
        self.audit_path = Path(self.tmp.name) / "promotion_audit.json"
        os.environ["USER_VENUE_CONTRIBUTIONS_PATH"] = str(self.contrib_path)
        os.environ["LOCAL_VENUE_PROFILES_PATH"] = str(self.profiles_path)
        os.environ["CONTRIBUTION_AUTO_PROMOTION_AUDIT_PATH"] = str(self.audit_path)
        with self.contrib_path.open("w") as f:
            json.dump(_empty_contrib_store(), f)
        with self.profiles_path.open("w") as f:
            json.dump(_empty_profiles(), f)
        clear_profiles_cache()

    def tearDown(self):
        for k in ("USER_VENUE_CONTRIBUTIONS_PATH", "LOCAL_VENUE_PROFILES_PATH", "CONTRIBUTION_AUTO_PROMOTION_AUDIT_PATH"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def _add_contrib(self, place_id="", place_name="Darbar", area_key="parramatta", contribution_type="better_order_suggestion", user_id="u1", suggested_order="paneer tikka + dal"):
        return create_contribution(
            place_id=place_id,
            place_name=place_name,
            area_key=area_key,
            contribution_type=contribution_type,
            user_id=user_id,
            payload={"suggested_order": suggested_order} if suggested_order else {},
        )

    def test_A_repeated_same_suggestion_auto_promotes(self):
        self._add_contrib(place_name="Darbar", area_key="parramatta", user_id="u1", suggested_order="paneer tikka + dal")
        self._add_contrib(place_name="Darbar", area_key="parramatta", user_id="u2", suggested_order="paneer tikka + dal")
        aggs = aggregate_contributions_for_place(place_name="Darbar", area_key="parramatta")
        self.assertGreaterEqual(len(aggs), 1)
        agg = next((a for a in aggs if "paneer" in (a.get("normalized_suggestion") or "")), None)
        self.assertIsNotNone(agg)
        self.assertEqual(agg["unique_user_count"], 2)
        self.assertEqual(agg["total_submission_count"], 2)
        decision = should_auto_promote(agg)
        self.assertTrue(decision.get("promote"), f"Expected promote=True, got {decision}")
        result = auto_promote_contribution_group(agg)
        self.assertTrue(result.get("ok"), f"Expected ok=True, got {result}")

    def test_B_vague_generic_suggestion_does_not_auto_promote(self):
        self._add_contrib(place_name="Cafe X", area_key="parramatta", user_id="u1", suggested_order="healthy option")
        self._add_contrib(place_name="Cafe X", area_key="parramatta", user_id="u2", suggested_order="healthy option")
        aggs = aggregate_contributions_for_place(place_name="Cafe X", area_key="parramatta")
        agg = next((a for a in aggs if a.get("contribution_type") == "better_order_suggestion"), None)
        self.assertIsNotNone(agg)
        decision = should_auto_promote(agg)
        self.assertFalse(decision.get("promote"))
        self.assertEqual(decision.get("blocked_reason"), "suggestion_too_generic")

    def test_C_vegan_unsafe_suggestion_blocked(self):
        self._add_contrib(
            place_name="Bakery Y",
            area_key="parramatta",
            contribution_type="vegan_option_missing",
            user_id="u1",
            suggested_order="cheese toast",
        )
        self._add_contrib(
            place_name="Bakery Y",
            area_key="parramatta",
            contribution_type="vegan_option_missing",
            user_id="u2",
            suggested_order="cheese toast",
        )
        aggs = aggregate_contributions_for_place(place_name="Bakery Y", area_key="parramatta")
        agg = next((a for a in aggs if a.get("contribution_type") == "vegan_option_missing"), None)
        self.assertIsNotNone(agg)
        decision = should_auto_promote(agg)
        self.assertFalse(decision.get("promote"))
        self.assertIn("diet", decision.get("blocked_reason", ""))

    def test_D_item_not_on_menu_blocks_promotion(self):
        self._add_contrib(place_name="Resto Z", area_key="parramatta", contribution_type="item_not_on_menu", user_id="u1", suggested_order="chicken tikka")
        self._add_contrib(place_name="Resto Z", area_key="parramatta", contribution_type="better_order_suggestion", user_id="u2", suggested_order="chicken tikka")
        aggs = aggregate_contributions_for_place(place_name="Resto Z", area_key="parramatta")
        agg = next((a for a in aggs if "chicken" in (a.get("normalized_suggestion") or "")), None)
        if agg:
            self.assertGreater(agg.get("item_not_on_menu_count", 0), 0)
            decision = should_auto_promote(agg)
            self.assertFalse(decision.get("promote"))

    def test_E_existing_trusted_template_not_destructively_overwritten(self):
        profiles_data = _load_raw()
        profiles_data["profiles"] = [{
            "place_id": "",
            "place_name": "Darbar",
            "normalized_name": "darbar",
            "name_variants": ["Darbar"],
            "area_key": "parramatta",
            "profile_source": "curated_manual",
            "candidate_templates": [{
                "template_key": "tandoori_chicken_half",
                "template_name": "tandoori chicken half + dal",
                "estimated_calories": 550,
                "estimated_protein_g": 35,
                "confidence": 0.85,
            }],
            "swap_templates": [],
            "active": True,
        }]
        with self.profiles_path.open("w") as f:
            json.dump(profiles_data, f, indent=2)
        clear_profiles_cache()

        self._add_contrib(place_name="Darbar", area_key="parramatta", user_id="u1", suggested_order="tandoori chicken half + dal")
        self._add_contrib(place_name="Darbar", area_key="parramatta", user_id="u2", suggested_order="tandoori chicken half + dal")
        aggs = aggregate_contributions_for_place(place_name="Darbar", area_key="parramatta")
        agg = next((a for a in aggs if "tandoori" in (a.get("normalized_suggestion") or "")), None)
        self.assertIsNotNone(agg)
        result = auto_promote_contribution_group(agg)
        if result.get("ok"):
            profile = get_profile_by_normalized_name("Darbar", "parramatta")
            templates = profile.get("candidate_templates") or []
            self.assertGreaterEqual(len(templates), 1)
            existing = next((t for t in templates if t.get("template_key") == "tandoori_chicken_half"), None)
            self.assertIsNotNone(existing)

    def test_F_auto_promotion_creates_audit_trail(self):
        self._add_contrib(place_name="NewPlace", area_key="parramatta", user_id="u1", suggested_order="idli sambar")
        self._add_contrib(place_name="NewPlace", area_key="parramatta", user_id="u2", suggested_order="idli sambar")
        aggs = aggregate_contributions_for_place(place_name="NewPlace", area_key="parramatta")
        agg = next((a for a in aggs if "idli" in (a.get("normalized_suggestion") or "")), None)
        self.assertIsNotNone(agg)
        result = auto_promote_contribution_group(agg)
        self.assertTrue(result.get("ok"))
        self.assertTrue(self.audit_path.exists())
        with self.audit_path.open() as f:
            data = json.load(f)
        promotions = data.get("promotions") or []
        self.assertGreaterEqual(len(promotions), 1)
        last = promotions[-1]
        self.assertIn("promotion_id", last)
        self.assertIn("action_type", last)
        self.assertIn("contribution_ids", last)

    def test_G_confidence_boost_path_for_recommendation_accurate(self):
        self._add_contrib(
            place_name="Grill House",
            area_key="parramatta",
            contribution_type="recommendation_accurate",
            user_id="u1",
            suggested_order="grilled chicken salad",
        )
        self._add_contrib(
            place_name="Grill House",
            area_key="parramatta",
            contribution_type="recommendation_accurate",
            user_id="u2",
            suggested_order="grilled chicken salad",
        )
        profiles_data = _load_raw()
        profiles_data["profiles"] = [{
            "place_id": "",
            "place_name": "Grill House",
            "normalized_name": "grill house",
            "name_variants": ["Grill House"],
            "area_key": "parramatta",
            "profile_source": "curated_manual",
            "candidate_templates": [{
                "template_key": "grilled_chicken_salad",
                "template_name": "grilled chicken salad",
                "estimated_calories": 420,
                "estimated_protein_g": 32,
                "confidence": 0.75,
            }],
            "swap_templates": [],
            "active": True,
        }]
        with self.profiles_path.open("w") as f:
            json.dump(profiles_data, f, indent=2)
        clear_profiles_cache()

        aggs = aggregate_contributions_for_place(place_name="Grill House", area_key="parramatta")
        agg = next((a for a in aggs if a.get("contribution_type") == "recommendation_accurate"), None)
        self.assertIsNotNone(agg)
        decision = should_auto_promote(agg)
        self.assertTrue(decision.get("promote"))
        self.assertEqual(decision.get("action_type"), "auto_promoted_confidence_boost")
        result = auto_promote_contribution_group(agg)
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("applied_changes", {}).get("confidence_boost") or result.get("applied_changes", {}).get("add_template"))

    def test_H_promoted_template_available_to_local_profile_lookup(self):
        self._add_contrib(place_name="NewVenue", area_key="parramatta", user_id="u1", suggested_order="dal makhani + roti")
        self._add_contrib(place_name="NewVenue", area_key="parramatta", user_id="u2", suggested_order="dal makhani + roti")
        result = run_auto_promotion_for_place(place_name="NewVenue", area_key="parramatta")
        self.assertGreaterEqual(result.get("promoted", 0), 1)
        profile = get_profile_by_normalized_name("NewVenue", "parramatta")
        self.assertIsNotNone(profile)
        templates = profile.get("candidate_templates") or []
        self.assertGreaterEqual(len(templates), 1)
        match = match_local_profile({"place_name": "NewVenue", "name": "NewVenue"}, area_key="parramatta")
        self.assertIsNotNone(match)


if __name__ == "__main__":
    unittest.main()

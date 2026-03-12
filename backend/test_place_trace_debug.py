"""
Tests for place_trace_debug: trace output, specificity tiers, hidden reasons.
"""
import unittest

from place_trace_debug import (
    TIER_CHAIN_REGISTRY,
    TIER_EXACT_MENU_MATCH,
    TIER_GENERIC_FALLBACK,
    TIER_HEURISTIC_STRONG,
    TIER_HEURISTIC_WEAK,
    build_place_trace,
    infer_specificity_tier,
    get_specificity_bonus_100,
    infer_hidden_reason,
)


class TestPlaceTraceDebug(unittest.TestCase):
    def test_infer_specificity_tier_chain_registry(self):
        tier = infer_specificity_tier("chain_registry", "6-inch Chicken Sub", "subway")
        self.assertEqual(tier, TIER_CHAIN_REGISTRY)

    def test_infer_specificity_tier_exact_menu(self):
        tier = infer_specificity_tier("real_menu", "Grilled Chicken Bowl", None)
        self.assertEqual(tier, TIER_EXACT_MENU_MATCH)

    def test_infer_specificity_tier_generic_fallback(self):
        tier = infer_specificity_tier("heuristic", "Tandoori + dal + roti", None)
        self.assertEqual(tier, TIER_GENERIC_FALLBACK)

    def test_infer_specificity_tier_heuristic_strong(self):
        tier = infer_specificity_tier("heuristic", "6-inch grilled chicken sub, extra salad", None)
        self.assertEqual(tier, TIER_HEURISTIC_STRONG)

    def test_get_specificity_bonus(self):
        self.assertEqual(get_specificity_bonus_100(TIER_EXACT_MENU_MATCH), 5)
        self.assertEqual(get_specificity_bonus_100(TIER_CHAIN_REGISTRY), 4)
        self.assertEqual(get_specificity_bonus_100(TIER_GENERIC_FALLBACK), -4)
        self.assertEqual(get_specificity_bonus_100(TIER_HEURISTIC_STRONG), 1)
        self.assertEqual(get_specificity_bonus_100(TIER_HEURISTIC_WEAK), 0)

    def test_build_place_trace_visible_chain(self):
        place = {
            "place_id": "ChIJSubway123",
            "name": "Subway",
            "recommended_order": "6-inch Chicken Teriyaki Sub",
            "best_order": "6-inch Chicken Teriyaki Sub",
            "menu_item_source": "chain_registry",
            "menu_item_confidence": 0.9,
            "display_rank_score_100": 82,
            "meal_fitness_score_100": 82,
            "eligibility_band": 3,
            "section": "Best fit for your goal",
            "chain_key": "subway",
            "top_menu_items": [{"item_name": "6-inch Chicken Teriyaki Sub"}],
        }
        trace = build_place_trace(place, user_context={}, visible_rank=1, visible_places=[place])
        self.assertEqual(trace["place_name"], "Subway")
        self.assertEqual(trace["chosen_candidate_specificity_tier"], TIER_CHAIN_REGISTRY)
        self.assertEqual(trace["specificity_bonus_100"], 4)
        self.assertTrue(trace["visible_in_results"])
        self.assertEqual(trace["visible_rank"], 1)
        self.assertFalse(trace["fetched_but_hidden"])
        self.assertIn("chosen_candidate_source", trace)
        self.assertIn("chosen_candidate_name", trace)

    def test_build_place_trace_fetched_but_hidden(self):
        place = {
            "place_id": "ChIJDarbar456",
            "name": "Darbar",
            "recommended_order": "Tandoori + dal + roti",
            "best_order": "Tandoori + dal + roti",
            "menu_item_source": "heuristic",
            "menu_item_confidence": 0.55,
            "display_rank_score_100": 72,
            "meal_fitness_score_100": 72,
            "eligibility_band": 1,
            "section": "Decent nearby options",
            "best_item_is_generic_fallback": True,
        }
        visible = [{"place_id": "other", "display_rank_score_100": 90}]
        trace = build_place_trace(place, user_context={}, visible_rank=None, visible_places=visible)
        self.assertTrue(trace["fetched_but_hidden"])
        self.assertEqual(trace["chosen_candidate_specificity_tier"], TIER_GENERIC_FALLBACK)
        self.assertIsNotNone(trace.get("hidden_reason"))

    def test_build_place_trace_includes_hidden_reason(self):
        place = {
            "place_name": "Subway Westfield",
            "place_id": "sub1",
            "name": "Subway Westfield",
            "best_order": "Lighter menu option",
            "menu_item_source": "heuristic",
            "display_rank_score_100": 65,
            "chain_key": None,
        }
        trace = build_place_trace(place, visible_rank=None, visible_places=[])
        self.assertIn("hidden_reason", trace)
        self.assertTrue(trace["fetched_but_hidden"])

    def test_infer_hidden_reason_generic_demoted(self):
        place = {
            "name": "Darbar",
            "best_item_name": "Tandoori + dal + roti",
            "best_item_is_generic_fallback": True,
            "chosen_candidate_specificity_tier": TIER_GENERIC_FALLBACK,
            "display_rank_score_100": 70,
        }
        visible = [{"display_rank_score_100": 85}] * 20
        reason = infer_hidden_reason(place, visible, None, top_n_cutoff=20)
        self.assertIn(reason, ("generic_fallback_demoted", "low_score", "top_n_cutoff"))

    def test_build_place_trace_includes_cache_and_local_profile_fields(self):
        """Trace includes used_venue_intelligence_cache, matched_local_profile, enqueued_for_enrichment."""
        place = {
            "place_id": "p1",
            "name": "Test Venue",
            "best_order": "Grilled salmon bowl",
            "menu_item_source": "exact_menu_cache",
            "_used_venue_intelligence_cache": True,
            "_cache_source_type": "exact_menu_cache",
            "_matched_local_profile": False,
            "_enqueued_for_enrichment": False,
        }
        trace = build_place_trace(place)
        self.assertTrue(trace["used_venue_intelligence_cache"])
        self.assertEqual(trace["cache_source_type"], "exact_menu_cache")
        self.assertFalse(trace["matched_local_profile"])
        self.assertFalse(trace["enqueued_for_enrichment"])
        self.assertIn("chosen_candidate_specificity_tier", trace)

        place2 = {
            "place_id": "p2",
            "name": "Generic Place",
            "best_order": "Lighter menu option",
            "menu_item_source": "heuristic",
            "_matched_local_profile": False,
            "_enqueued_for_enrichment": True,
            "_enrichment_enqueue_reason": "candidate_low_specificity",
        }
        trace2 = build_place_trace(place2)
        self.assertTrue(trace2["enqueued_for_enrichment"])
        self.assertEqual(trace2["enrichment_enqueue_reason"], "candidate_low_specificity")

    def test_build_place_trace_includes_cache_last_enriched_at_and_local_profile_id(self):
        """Trace includes cache_last_enriched_at and local_profile_id for audit visibility."""
        place = {
            "place_id": "p4",
            "name": "Cached Venue",
            "best_order": "Salmon bowl",
            "_used_venue_intelligence_cache": True,
            "_cache_source_type": "exact_menu_cache",
            "_cache_last_enriched_at": "2025-03-01T10:00:00Z",
            "_local_profile_id": None,
        }
        trace = build_place_trace(place)
        self.assertEqual(trace.get("cache_last_enriched_at"), "2025-03-01T10:00:00Z")
        self.assertIsNone(trace.get("local_profile_id"))

        place2 = {
            "place_id": "p5",
            "name": "Local Profile Venue",
            "_matched_local_profile": True,
            "_local_profile_id": "prof-uuid-123",
        }
        trace2 = build_place_trace(place2)
        self.assertEqual(trace2.get("local_profile_id"), "prof-uuid-123")

    def test_infer_specificity_tier_local_venue_profile(self):
        """local_venue_profile source maps to high-tier specificity."""
        tier = infer_specificity_tier("local_venue_profile", "Tandoori chicken half + dal", None)
        self.assertEqual(tier, TIER_EXACT_MENU_MATCH)

    def test_build_place_trace_includes_diet_and_fallback_fields(self):
        """G. Audit/trace fields show fallback + diet filtering info."""
        place = {
            "place_id": "p3",
            "name": "Unknown Indian",
            "best_order": "Dal + roti (needs menu check)",
            "menu_item_source": "heuristic",
            "diet_preference": "vegan",
            "_diet_excluded_candidate_count": 3,
            "best_item_is_generic_fallback": True,
            "_enqueued_for_enrichment": True,
            "_enrichment_enqueue_reason": "missing_vegan_profile",
        }
        trace = build_place_trace(place)
        self.assertEqual(trace.get("diet_preference"), "vegan")
        self.assertEqual(trace.get("diet_excluded_candidate_count"), 3)
        self.assertTrue(trace.get("fallback_used"))
        self.assertIn(trace.get("fallback_reason"), ("generic_heuristic_only", None))
        self.assertTrue(trace.get("enqueued_for_enrichment"))
        self.assertEqual(trace.get("enrichment_enqueue_reason"), "missing_vegan_profile")


if __name__ == "__main__":
    unittest.main()

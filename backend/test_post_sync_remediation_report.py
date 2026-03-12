"""
Tests for post-sync remediation report.
Run with: cd backend && python -m pytest test_post_sync_remediation_report.py -v
Or: cd backend && python -m unittest test_post_sync_remediation_report -v
"""
from __future__ import annotations

import asyncio
import unittest

from post_sync_remediation_report import (
    run_post_sync_launch_report,
    run_post_sync_reports_for_priority_areas,
    build_next_enrichment_targets,
    score_enrichment_target,
    build_next_enrichment_targets_from_fetch,
    ACTION_ADD_PROFILE_NOW,
    ACTION_REVIEW_CHAIN_GAP,
)


def _mock_healthy_places_response(generic_count: int = 2, total: int = 5):
    """Build mock healthy_places response with configurable generic fallback."""
    items = []
    for i in range(total):
        is_generic = i < generic_count
        items.append({
            "name": f"Venue {i + 1}",
            "place_name": f"Venue {i + 1}",
            "place_id": f"Ch{i:03d}",
            "best_item_name": "Tandoori + dal" if is_generic else "Chicken tikka masala",
            "chosen_candidate_specificity_tier": "generic_fallback" if is_generic else "enriched_local_profile",
            "menu_item_source": "generic_fallback" if is_generic else "enriched_local_profile",
            "display_rank_score_100": 80 - i,
            "profile_store": "supabase_canonical",
            "local_profile_source": "",
            "seeded_by_launch_pack": False,
        })
    return {
        "items": items,
        "places": items,
        "_debug": {
            "timings_ms": {"total_ms": 100, "nearby_fetch_ms": 50, "shortlist_ms": 20, "ranking_ms": 30},
            "fetched_count": 20,
            "shortlisted_count": 10,
            "deeply_ranked_count": 5,
        },
    }


class TestPostSyncReport(unittest.TestCase):
    def test_run_post_sync_launch_report_includes_canonical_metrics(self):
        """Post-sync report includes key canonical/profile metrics."""
        async def fetcher(lat: float, lng: float):
            return _mock_healthy_places_response(generic_count=3, total=5)

        report = asyncio.run(
            run_post_sync_launch_report("parramatta", fetch_fn=fetcher, include_examples=True)
        )

        self.assertIn("area_key", report)
        self.assertEqual(report["area_key"], "parramatta")
        self.assertIn("canonical_sync", report)
        sync = report["canonical_sync"]
        self.assertIn("canonical_profile_count", sync)
        self.assertIn("pack_seeded_profiles", sync)
        self.assertIn("auto_promoted_profiles", sync)
        self.assertIn("supabase_available", sync)
        self.assertIn("local_enrichment", report)
        self.assertIn("canonical_trusted_local_profiles_count", report["local_enrichment"])
        self.assertIn("percent_top_5_generic_fallback", report)
        self.assertIn("generic_problem_examples", report)
        self.assertIn("known_chain_hidden_rate", report)
        self.assertIn("remediation_examples", report)
        rem = report["remediation_examples"]
        self.assertIn("top_remaining_generic_fallback_venues", rem)
        self.assertIn("top_missing_chain_opportunities", rem)
        self.assertIn("top_duplicate_score_cluster_examples", rem)

    def test_run_post_sync_reports_for_priority_areas(self):
        """Post-sync reports for priority areas returns structured summaries."""
        async def fetcher(lat: float, lng: float):
            return _mock_healthy_places_response(generic_count=2, total=5)

        result = asyncio.run(run_post_sync_reports_for_priority_areas(
            fetch_fn=fetcher,
            limit_areas=3,
            include_examples=True,
        ))

        self.assertIn("areas", result)
        self.assertIn("total_areas", result)
        self.assertIn("priority_order", result)
        self.assertLessEqual(len(result["areas"]), 3)
        for r in result["areas"]:
            self.assertIn("canonical_sync", r)
            self.assertIn("percent_top_5_generic_fallback", r)


class TestNextEnrichmentTargets(unittest.TestCase):
    def test_build_next_enrichment_targets_returns_sorted_targets(self):
        """Next-enrichment target scoring returns sorted targets."""
        reports = [
            {
                "area_key": "parramatta",
                "percent_top_5_generic_fallback": 60,
                "generic_problem_examples": [
                    {"name": "Cafe A", "place_name": "Cafe A", "place_id": "", "best_item_name": "Eggs on toast", "tier": "generic_fallback"},
                    {"name": "Indian B", "place_name": "Indian B", "place_id": "Ch01", "best_item_name": "Tandoori + dal", "tier": "generic_fallback"},
                ],
                "top_missing_chain_examples": [{"place_name": "Subway X", "place_id": "Ch99", "hidden_reason": "not_in_top_5"}],
                "top_cuisines_needing_enrichment": [{"cuisine": "indian", "generic_count": 5}, {"cuisine": "cafe", "generic_count": 3}],
                "local_enrichment": {},
            },
            {
                "area_key": "wentworthville",
                "percent_top_5_generic_fallback": 40,
                "generic_problem_examples": [
                    {"name": "Indian B", "place_name": "Indian B", "place_id": "Ch01", "best_item_name": "Tandoori + dal", "tier": "generic_fallback"},
                ],
                "top_missing_chain_examples": [],
                "top_cuisines_needing_enrichment": [{"cuisine": "indian", "generic_count": 2}],
                "local_enrichment": {},
            },
        ]

        targets = build_next_enrichment_targets(reports=reports, limit_total=20)

        self.assertGreaterEqual(len(targets), 1)
        scores = [float(t.get("priority_score", 0)) for t in targets]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for t in targets:
            self.assertIn("recommended_enrichment_action", t)
            self.assertIn("reason_summary", t)
            self.assertIn("area_key", t)

    def test_targets_include_recommended_action(self):
        """Targets include recommended action."""
        reports = [
            {
                "area_key": "parramatta",
                "percent_top_5_generic_fallback": 70,
                "generic_problem_examples": [
                    {"name": "Generic Venue", "place_name": "Generic Venue", "place_id": "", "best_item_name": "Protein bowl", "tier": "generic_fallback"},
                ],
                "top_missing_chain_examples": [{"place_name": "McDonald's", "place_id": "ChMcD", "hidden_reason": "not_in_top_5"}],
                "top_cuisines_needing_enrichment": [],
                "local_enrichment": {},
            },
        ]

        targets = build_next_enrichment_targets(reports=reports, limit_total=10)

        actions = {t.get("recommended_enrichment_action") for t in targets}
        self.assertTrue(ACTION_ADD_PROFILE_NOW in actions or ACTION_REVIEW_CHAIN_GAP in actions)

    def test_already_strongly_covered_venues_rank_lower(self):
        """Already-strongly-covered venues rank lower than generic weak venues."""
        generic_target = {
            "area_key": "parramatta",
            "place_name": "Weak Cafe",
            "source_type": "generic_fallback",
            "chosen_candidate_specificity_tier": "generic_fallback",
            "visibility_count": 2,
            "percent_top_5_generic_in_area": 60,
        }
        strong_target = {
            "area_key": "parramatta",
            "place_name": "Strong Local",
            "source_type": "generic_fallback",
            "chosen_candidate_specificity_tier": "enriched_local_profile",
            "visibility_count": 2,
            "percent_top_5_generic_in_area": 60,
        }

        g_scored = score_enrichment_target(generic_target)
        s_scored = score_enrichment_target(strong_target)

        self.assertGreater(g_scored["priority_score"], s_scored["priority_score"])

    def test_high_priority_suburbs_influence_scoring(self):
        """High-priority suburbs influence scoring."""
        wentworthville = {
            "area_key": "wentworthville",
            "place_name": "Venue A",
            "source_type": "generic_fallback",
            "chosen_candidate_specificity_tier": "generic_fallback",
            "visibility_count": 1,
            "percent_top_5_generic_in_area": 50,
        }
        low_priority_area = {
            "area_key": "sydney_olympic_park",
            "place_name": "Venue B",
            "source_type": "generic_fallback",
            "chosen_candidate_specificity_tier": "generic_fallback",
            "visibility_count": 1,
            "percent_top_5_generic_in_area": 50,
        }

        w_scored = score_enrichment_target(wentworthville)
        l_scored = score_enrichment_target(low_priority_area)

        self.assertGreater(w_scored["priority_score"], l_scored["priority_score"])

    def test_score_enrichment_target_returns_scored_dict(self):
        """score_enrichment_target returns target with priority_score."""
        target = {
            "area_key": "parramatta",
            "place_name": "Test",
            "source_type": "generic_fallback",
            "chosen_candidate_specificity_tier": "generic_fallback",
        }
        out = score_enrichment_target(target)
        self.assertIn("priority_score", out)
        self.assertIsInstance(out["priority_score"], (int, float))
        self.assertGreaterEqual(out["priority_score"], 0)

    def test_build_next_enrichment_targets_from_fetch(self):
        """Full pipeline returns targets and by_action buckets."""
        async def fetcher(lat: float, lng: float):
            return _mock_healthy_places_response(generic_count=3, total=5)

        result = asyncio.run(build_next_enrichment_targets_from_fetch(
            fetch_fn=fetcher,
            limit_total=20,
            limit_areas=3,
        ))

        self.assertIn("targets", result)
        self.assertIn("by_action", result)
        self.assertIn("areas_analyzed", result)
        self.assertIn("total_targets", result)
        self.assertIsInstance(result["by_action"], dict)


if __name__ == "__main__":
    unittest.main()

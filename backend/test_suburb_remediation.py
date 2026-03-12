"""
Tests for suburb remediation: ranking, remediation list, surface_top_problems.
"""
from __future__ import annotations

import unittest

from suburb_remediation import (
    rank_suburbs_by_worst,
    build_remediation_list,
    surface_top_problems,
    _worst_suburb_score,
)


class TestSuburbRanking(unittest.TestCase):
    def test_worst_score_higher_for_generic_and_hidden_chains(self):
        r1 = {"percent_top_5_generic_fallback": 80, "known_chain_fetched_count": 4, "known_chain_hidden_count": 2}
        r2 = {"percent_top_5_generic_fallback": 20, "known_chain_fetched_count": 4, "known_chain_hidden_count": 0}
        self.assertGreater(_worst_suburb_score(r1), _worst_suburb_score(r2))

    def test_rank_suburbs_worst_first(self):
        reports = [
            {"area_key": "a", "percent_top_5_generic_fallback": 30, "known_chain_fetched_count": 1, "known_chain_hidden_count": 0},
            {"area_key": "b", "percent_top_5_generic_fallback": 90, "known_chain_fetched_count": 2, "known_chain_hidden_count": 1},
        ]
        ranked = rank_suburbs_by_worst(reports)
        self.assertEqual(ranked[0]["area_key"], "b")


class TestRemediationList(unittest.TestCase):
    def test_build_remediation_list_shape(self):
        report = {
            "area_key": "parramatta",
            "display_name": "Parramatta",
            "readiness_status": "too_generic",
            "percent_top_5_generic_fallback": 70,
            "known_chain_hidden_count": 2,
            "top_missing_chain_examples": [
                {"place_name": "Subway Parramatta", "hidden_reason": "not_in_top_5"},
            ],
            "generic_problem_examples": [
                {"name": "Generic Cafe", "best_item_name": "Protein bowl", "tier": "generic_fallback"},
            ],
            "top_cuisines_needing_enrichment": [{"cuisine": "indian", "generic_count": 3}],
            "duplicate_score_clusters": [{"score": 72, "count": 3, "places": ["A", "B", "C"]}],
        }
        out = build_remediation_list(report)
        self.assertEqual(out["area_key"], "parramatta")
        self.assertEqual(len(out["top_10_missing_chain_opportunities"]), 1)
        self.assertEqual(len(out["top_10_generic_fallback_venues"]), 1)
        self.assertEqual(len(out["top_cuisines_needing_enrichment"]), 1)
        self.assertEqual(len(out["top_duplicate_score_clusters"]), 1)


class TestSurfaceTopProblems(unittest.TestCase):
    def test_surface_returns_worst_two(self):
        reports = [
            {"area_key": "bad", "display_name": "Bad", "percent_top_5_generic_fallback": 95, "known_chain_fetched_count": 2, "known_chain_hidden_count": 1, "top_missing_chain_examples": [], "generic_problem_examples": []},
            {"area_key": "ok", "display_name": "OK", "percent_top_5_generic_fallback": 20, "known_chain_fetched_count": 1, "known_chain_hidden_count": 0, "top_missing_chain_examples": [], "generic_problem_examples": []},
        ]
        out = surface_top_problems(reports, top_n=2)
        self.assertEqual(len(out["worst_suburbs"]), 2)
        self.assertEqual(out["worst_suburbs"][0]["area_key"], "bad")

"""
Tests for launch readiness report: specificity, concrete-order, genericity, grading.
"""
from __future__ import annotations

import asyncio
import unittest

from launch_readiness_report import (
    SPECIFICITY_SCORE,
    _specificity_score,
    _is_generic_item,
    _is_concrete_order,
    _has_specific_swap,
    _has_high_confidence,
    _has_clear_difference_reason,
    _is_known_chain,
    _compute_readiness_status,
    build_launch_readiness_report,
)
from launch_area_config import sample_points_for_area


class TestSpecificityScoring(unittest.TestCase):
    def test_exact_menu_match_scores_5(self):
        self.assertEqual(_specificity_score("exact_menu_match"), 5)

    def test_chain_registry_scores_4(self):
        self.assertEqual(_specificity_score("chain_registry"), 4)

    def test_enriched_local_profile_scores_4(self):
        self.assertEqual(_specificity_score("enriched_local_profile"), 4)

    def test_generic_fallback_scores_0(self):
        self.assertEqual(_specificity_score("generic_fallback"), 0)

    def test_unknown_tier_scores_0(self):
        self.assertEqual(_specificity_score("unknown_tier"), 0)


class TestConcreteOrderDetection(unittest.TestCase):
    def test_concrete_specific_item(self):
        self.assertTrue(_is_concrete_order({"best_item_name": "6-inch Grilled Chicken Sub"}))
        self.assertTrue(_is_concrete_order({"best_item_name": "Tandoori chicken half + dal"}))

    def test_generic_item_not_concrete(self):
        self.assertFalse(_is_concrete_order({"best_item_name": "Lighter menu option"}))
        self.assertFalse(_is_concrete_order({"best_item_name": "Tandoori + dal + roti"}))


class TestGenericItemDetection(unittest.TestCase):
    def test_generic_tokens(self):
        self.assertTrue(_is_generic_item("Lighter menu option"))
        self.assertTrue(_is_generic_item("egg + chicken plate"))
        self.assertTrue(_is_generic_item("protein bowl"))

    def test_specific_not_generic(self):
        self.assertFalse(_is_generic_item("6-inch Grilled Chicken Sub"))
        self.assertFalse(_is_generic_item("Tandoori chicken half + dal tadka"))


class TestSpecificSwap(unittest.TestCase):
    def test_has_swap(self):
        self.assertTrue(_has_specific_swap({
            "best_item_swaps": [{"swap_label": "No mayo"}],
        }))
        self.assertTrue(_has_specific_swap({
            "best_item_swaps": [{"swap_label": "Skip fries"}],
        }))

    def test_no_swap(self):
        self.assertFalse(_has_specific_swap({"best_item_swaps": []}))
        self.assertFalse(_has_specific_swap({}))


class TestKnownChainDetection(unittest.TestCase):
    def test_known_chains(self):
        self.assertTrue(_is_known_chain({"name": "Subway Westfield"}))
        self.assertTrue(_is_known_chain({"name": "McDonald's"}))
        self.assertTrue(_is_known_chain({"name": "Grill'd Parramatta"}))

    def test_unknown_not_chain(self):
        self.assertFalse(_is_known_chain({"name": "Random Cafe"}))


class TestReadinessGrading(unittest.TestCase):
    def test_launch_ready_when_all_pass(self):
        s = _compute_readiness_status(
            p90_ms=2000,
            pct_top5_generic=20,
            pct_top3_concrete=70,
            pct_local=15,
            known_hidden_rate=0.2,
        )
        self.assertEqual(s, "launch_ready")

    def test_too_slow(self):
        s = _compute_readiness_status(
            p90_ms=6000,
            pct_top5_generic=20,
            pct_top3_concrete=70,
            pct_local=15,
            known_hidden_rate=0.2,
        )
        self.assertEqual(s, "too_slow")

    def test_too_generic(self):
        s = _compute_readiness_status(
            p90_ms=2000,
            pct_top5_generic=70,
            pct_top3_concrete=70,
            pct_local=15,
            known_hidden_rate=0.2,
        )
        self.assertEqual(s, "too_generic")

    def test_chain_coverage_gap(self):
        s = _compute_readiness_status(
            p90_ms=2000,
            pct_top5_generic=20,
            pct_top3_concrete=70,
            pct_local=15,
            known_hidden_rate=0.6,
        )
        self.assertEqual(s, "chain_coverage_gap")


class TestSamplePoints(unittest.TestCase):
    def test_sample_points_for_area(self):
        pts = sample_points_for_area("parramatta", count=5)
        self.assertGreaterEqual(len(pts), 1)
        self.assertIn("lat", pts[0])
        self.assertIn("lng", pts[0])
        self.assertEqual(pts[0].get("label"), "center")


class TestReportStructure(unittest.TestCase):
    def test_report_without_fetch_returns_valid_structure(self):
        async def run():
            return await build_launch_readiness_report(
                "parramatta", fetch_fn=None, include_examples=True,
            )

        report = asyncio.run(run())
        self.assertIn("area_key", report)
        self.assertIn("readiness_status", report)
        self.assertIn("percent_top_5_generic_fallback", report)
        self.assertIn("local_enrichment", report)
        self.assertEqual(report["readiness_status"], "no_data")

    def test_report_with_mock_fetch(self):
        async def mock_fetch(lat: float, lng: float):
            return {
                "places": [
                    {
                        "name": "Subway",
                        "place_id": "1",
                        "best_item_name": "6-inch Grilled Chicken Sub",
                        "chosen_candidate_specificity_tier": "chain_registry",
                        "display_rank_score_100": 82,
                        "confidence_label": "Estimated",
                        "rank_reason_short": "Higher protein, fits today",
                        "menu_item_source": "chain_registry",
                        "best_item_swaps": [{"swap_label": "No mayo"}],
                    },
                    {
                        "name": "Cafe X",
                        "place_id": "2",
                        "best_item_name": "Lighter menu option",
                        "chosen_candidate_specificity_tier": "generic_fallback",
                        "display_rank_score_100": 55,
                        "confidence_label": "Needs menu check",
                        "rank_reason_short": "Check menu for best pick",
                        "menu_item_source": "heuristic",
                    },
                ],
                "_debug": {
                    "timings_ms": {"total_ms": 1200, "nearby_fetch_ms": 400, "ranking_ms": 700},
                    "fetched_count": 20,
                    "shortlisted_count": 10,
                    "deeply_ranked_count": 10,
                },
            }

        async def run():
            return await build_launch_readiness_report(
                "parramatta",
                sample_points=[{"lat": -33.815, "lng": 151.0, "label": "center"}],
                fetch_fn=mock_fetch,
                include_examples=True,
            )

        report = asyncio.run(run())
        self.assertEqual(report["sample_count"], 1)
        self.assertIn("percent_top_1_exact_or_chain_backed", report)
        self.assertGreater(report["percent_top_1_exact_or_chain_backed"], 0)
        self.assertIn("concrete_examples", report)

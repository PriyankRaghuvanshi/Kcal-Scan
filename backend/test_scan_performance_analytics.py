"""Tests for scan performance analytics."""
import os
import tempfile
import unittest

from scan_performance_analytics import (
    record_scan_performance_event,
    build_scan_performance_summary,
    compute_percentiles,
    list_recent_events,
)


class ComputePercentilesTests(unittest.TestCase):
    """E, F, G. Percentile computation and summary."""

    def test_compute_percentiles_empty(self):
        self.assertEqual(compute_percentiles([]), {"p50": 0.0, "p90": 0.0})

    def test_compute_percentiles_single(self):
        out = compute_percentiles([100.0])
        self.assertEqual(out["p50"], 100.0)
        self.assertEqual(out["p90"], 100.0)

    def test_compute_percentiles_multiple(self):
        vals = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        out = compute_percentiles(vals)
        self.assertEqual(out["p50"], 50.0)
        self.assertEqual(out["p90"], 90.0)


class RecordAndSummaryTests(unittest.TestCase):
    """E, F. time_to_first_result_ms and time_to_final_result_ms recorded. G. Summary computes median/p90."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        try:
            os.unlink(self.path)
        except Exception:
            pass

    def test_record_and_summary(self):
        os.environ["SCAN_PERFORMANCE_EVENTS_PATH"] = self.path
        try:
            record_scan_performance_event({
                "request_id": "r1",
                "analysis_id": "a1",
                "user_id": "u1",
                "time_to_first_result_ms": 1200,
                "time_to_final_result_ms": 2500,
                "vision_ms": 800,
                "nutrition_ms": 300,
                "meal_qa_ms": 400,
                "enrichment_ms": 200,
                "nutrition_cache_hit_count": 2,
                "nutrition_cache_miss_count": 1,
            })
            record_scan_performance_event({
                "request_id": "r2",
                "analysis_id": "a2",
                "user_id": "u1",
                "time_to_first_result_ms": 1000,
                "time_to_final_result_ms": 2200,
                "vision_ms": 700,
                "nutrition_ms": 250,
                "meal_qa_ms": 350,
                "enrichment_ms": 150,
                "nutrition_cache_hit_count": 3,
                "nutrition_cache_miss_count": 0,
            })
            summary = build_scan_performance_summary(window_days=7)
            self.assertEqual(summary["total_scans"], 2)
            self.assertEqual(summary["median_time_to_first_result_ms"], 1000.0)
            self.assertEqual(summary["median_time_to_final_result_ms"], 2200.0)
            self.assertEqual(summary["median_vision_ms"], 700.0)
            self.assertEqual(summary["median_nutrition_ms"], 250.0)
            self.assertGreater(summary["cache_hit_rate"], 0)
        finally:
            os.environ.pop("SCAN_PERFORMANCE_EVENTS_PATH", None)

    def test_list_recent_events(self):
        os.environ["SCAN_PERFORMANCE_EVENTS_PATH"] = self.path
        try:
            record_scan_performance_event({"request_id": "r1", "analysis_id": "a1"})
            record_scan_performance_event({"request_id": "r2", "analysis_id": "a2"})
            events = list_recent_events(limit=10)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["request_id"], "r2")
        finally:
            os.environ.pop("SCAN_PERFORMANCE_EVENTS_PATH", None)


class AnalyticsFailureTests(unittest.TestCase):
    """H. Analytics failure does not break scan flow."""

    def test_record_accepts_empty_or_none_event(self):
        record_scan_performance_event({})
        record_scan_performance_event(None)

    def test_record_swallows_exceptions(self):
        """record_scan_performance_event must not raise so scan flow is never broken."""
        record_scan_performance_event({"invalid_key_that_might_cause_issues": object()})


if __name__ == "__main__":
    unittest.main()

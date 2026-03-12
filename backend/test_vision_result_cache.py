"""Tests for vision result cache and safe reuse rules."""
import os
import tempfile
import unittest

from vision_result_cache import (
    compute_image_fingerprint,
    get_cached_vision_result,
    set_cached_vision_result,
    should_reuse_cached_vision_result,
    vision_cache_skipped_reason,
)


class FingerprintTests(unittest.TestCase):
    """A. Identical image fingerprint gives cache hit. B. Different image bytes do not match."""

    def test_identical_bytes_same_fingerprint(self):
        data = b"identical image bytes"
        fp1 = compute_image_fingerprint(data)
        fp2 = compute_image_fingerprint(data)
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)

    def test_different_bytes_different_fingerprint(self):
        fp1 = compute_image_fingerprint(b"image a")
        fp2 = compute_image_fingerprint(b"image b")
        self.assertNotEqual(fp1, fp2)

    def test_empty_bytes_empty_fingerprint(self):
        self.assertEqual(compute_image_fingerprint(b""), "")


class SafeReuseTests(unittest.TestCase):
    """C. Weak-confidence cached result is not reused."""

    def test_low_confidence_not_reused(self):
        cached = {
            "vision_confidence": 0.5,
            "items": [
                {"name": "chicken", "grams": 150, "confidence": 0.7},
            ],
        }
        self.assertFalse(should_reuse_cached_vision_result(cached, min_confidence=0.72))
        self.assertEqual(vision_cache_skipped_reason(cached, 0.72), "low_confidence")

    def test_high_confidence_reused(self):
        cached = {
            "vision_confidence": 0.85,
            "items": [
                {"name": "chicken breast", "grams": 150, "confidence": 0.82},
            ],
        }
        self.assertTrue(should_reuse_cached_vision_result(cached, min_confidence=0.72))

    def test_no_items_not_reused(self):
        cached = {
            "vision_confidence": 0.9,
            "items": [],
        }
        self.assertFalse(should_reuse_cached_vision_result(cached))
        self.assertEqual(vision_cache_skipped_reason(cached), "no_items")

    def test_too_many_items_not_reused(self):
        cached = {
            "vision_confidence": 0.85,
            "items": [{"name": f"item_{i}", "grams": 50, "confidence": 0.8} for i in range(10)],
        }
        self.assertFalse(should_reuse_cached_vision_result(cached))
        self.assertEqual(vision_cache_skipped_reason(cached), "too_many_items")

    def test_invalid_item_not_reused(self):
        cached = {
            "vision_confidence": 0.85,
            "items": [
                {"name": "chicken", "grams": 150},
                {"name": "", "grams": 100},
            ],
        }
        self.assertFalse(should_reuse_cached_vision_result(cached))
        self.assertEqual(vision_cache_skipped_reason(cached), "invalid_items")


class CacheTests(unittest.TestCase):
    """D. Safe cache hit skips resolver/vision call. E. Miss falls back to normal vision and stores cache."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "vision_cache.json")

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.unlink(self.path)
            if os.path.exists(self.tmpdir):
                os.rmdir(self.tmpdir)
        except Exception:
            pass

    def test_cache_miss_returns_none(self):
        os.environ["VISION_RESULT_CACHE_PATH"] = self.path
        try:
            fp = compute_image_fingerprint(b"unique image")
            self.assertIsNone(get_cached_vision_result(fp))
        finally:
            os.environ.pop("VISION_RESULT_CACHE_PATH", None)

    def test_cache_hit_after_set(self):
        os.environ["VISION_RESULT_CACHE_PATH"] = self.path
        try:
            fp = compute_image_fingerprint(b"meal image")
            payload = {
                "vision_confidence": 0.82,
                "items": [{"name": "rice", "grams": 200, "confidence": 0.8}],
                "top_candidates": [{"label": "rice", "confidence": 0.8}],
            }
            set_cached_vision_result(fp, payload, ttl_hours=72)
            cached = get_cached_vision_result(fp)
            self.assertIsNotNone(cached)
            self.assertEqual(cached.get("vision_confidence"), 0.82)
            self.assertTrue(should_reuse_cached_vision_result(cached, min_confidence=0.72))
        finally:
            os.environ.pop("VISION_RESULT_CACHE_PATH", None)

    def test_cache_miss_then_hit(self):
        os.environ["VISION_RESULT_CACHE_PATH"] = self.path
        try:
            data = b"repeated scan image"
            fp = compute_image_fingerprint(data)
            self.assertIsNone(get_cached_vision_result(fp))
            payload = {
                "vision_confidence": 0.85,
                "items": [{"name": "salad", "grams": 150}],
                "top_candidates": [{"label": "salad", "confidence": 0.85}],
            }
            set_cached_vision_result(fp, payload, ttl_hours=72)
            cached = get_cached_vision_result(fp)
            self.assertIsNotNone(cached)
            self.assertTrue(should_reuse_cached_vision_result(cached))
        finally:
            os.environ.pop("VISION_RESULT_CACHE_PATH", None)


class AnalyticsTests(unittest.TestCase):
    """F. Analytics reflect cache hit/miss."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "scan_perf.json")

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.unlink(self.path)
            if os.path.exists(self.tmpdir):
                os.rmdir(self.tmpdir)
        except Exception:
            pass

    def test_vision_cache_in_summary(self):
        os.environ["SCAN_PERFORMANCE_EVENTS_PATH"] = self.path
        try:
            from scan_performance_analytics import record_scan_performance_event, build_scan_performance_summary

            record_scan_performance_event({
                "vision_cache_reuse_used": True,
                "vision_cache_hit_count": 1,
                "vision_cache_miss_count": 0,
                "vision_ms": 0,
                "time_to_first_result_ms": 500,
            })
            record_scan_performance_event({
                "vision_cache_reuse_used": False,
                "vision_cache_hit_count": 0,
                "vision_cache_miss_count": 1,
                "vision_ms": 1200,
                "time_to_first_result_ms": 1800,
            })
            summary = build_scan_performance_summary(window_days=7)
            self.assertEqual(summary["total_scans"], 2)
            self.assertEqual(summary["vision_cache_hit_rate"], 0.5)
            self.assertEqual(summary["vision_cache_hit_count"], 1)
            self.assertEqual(summary["vision_cache_miss_count"], 1)
            self.assertEqual(summary["median_time_to_first_result_ms_when_vision_cache_hit"], 500.0)
            self.assertEqual(summary["median_time_to_first_result_ms_when_vision_cache_miss"], 1800.0)
        finally:
            os.environ.pop("SCAN_PERFORMANCE_EVENTS_PATH", None)

    def test_vision_cache_skipped_reasons_in_summary(self):
        os.environ["SCAN_PERFORMANCE_EVENTS_PATH"] = self.path
        try:
            from scan_performance_analytics import record_scan_performance_event, build_scan_performance_summary

            record_scan_performance_event({
                "vision_cache_reuse_used": False,
                "vision_cache_skipped_reason": "low_confidence",
                "time_to_first_result_ms": 1500,
            })
            record_scan_performance_event({
                "vision_cache_reuse_used": False,
                "vision_cache_skipped_reason": "low_confidence",
                "time_to_first_result_ms": 1600,
            })
            summary = build_scan_performance_summary(window_days=7)
            self.assertEqual(summary["vision_cache_skipped_reasons"], {"low_confidence": 2})
        finally:
            os.environ.pop("SCAN_PERFORMANCE_EVENTS_PATH", None)


if __name__ == "__main__":
    unittest.main()

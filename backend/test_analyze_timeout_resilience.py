import io
import os
import time
import unittest
from unittest.mock import patch

try:
    import main as appmod
    _IMPORT_ERR = ""
except Exception as e:  # pragma: no cover
    appmod = None
    _IMPORT_ERR = str(e)

try:  # pragma: no cover
    from fastapi.testclient import TestClient
except Exception:
    TestClient = None

try:  # pragma: no cover
    from PIL import Image
except Exception:
    Image = None


@unittest.skipIf(appmod is None, f"main dependencies unavailable: {_IMPORT_ERR}")
class AnalyzeTimeoutResilienceTests(unittest.TestCase):
    def _image_bytes(self, size=(24, 24)) -> bytes:
        img = Image.new("RGB", size, color=(220, 120, 80))
        bio = io.BytesIO()
        img.save(bio, format="JPEG")
        return bio.getvalue()

    def test_model_candidates_exclude_gemini_3_family(self):
        self.assertTrue(appmod.is_deprecated_model("gemini-3-flash-preview"))
        self.assertTrue(appmod.is_deprecated_model("models/gemini-3-pro"))
        cands = appmod._llm_model_candidates("gemini-3-flash-preview", ["gemini-2.5-flash", "gemini-3-pro"])
        self.assertIn("gemini-2.5-flash", cands)
        self.assertNotIn("gemini-3-flash-preview", cands)
        self.assertNotIn("gemini-3-pro", cands)

    def test_compute_scan_nutrition_uses_unverified_when_usda_unavailable(self):
        item = {
            "item_id": "i1",
            "name": "veg curry bowl",
            "grams": 250,
            "confidence": 0.75,
            "cooking_method": "pan_fried",
            "oil_added_tsp": 1.0,
            "candidate_alternatives": ["veg stir fry"],
        }
        with patch.object(appmod, "usda_search_candidates", side_effect=Exception("usda timeout")):
            results, totals, micros, warnings, cache_stats = appmod._compute_scan_nutrition([item])

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].get("unverified"))
        self.assertGreaterEqual(float(totals.get("kcal", 0.0) or 0.0), 0.0)
        self.assertGreaterEqual(float(micros.get("fiber_g", 0.0) or 0.0), 0.0)
        self.assertTrue(any(w.get("warning") == "nutrition_lookup_failed" for w in warnings))
        self.assertIsInstance(cache_stats, dict)
        self.assertIn("hit_count", cache_stats)
        self.assertIn("miss_count", cache_stats)

    @unittest.skipIf(TestClient is None or Image is None, "httpx/TestClient not installed in local env")
    def test_analyze_returns_quick_202_even_if_supabase_persist_is_slow(self):
        client = TestClient(appmod.app)
        img_bytes = self._image_bytes()

        def _slow_store(row):
            time.sleep(12)
            return row

        with patch.object(appmod, "_enqueue_analysis_job", return_value=None), patch.object(
            appmod, "_store_analysis_job", side_effect=_slow_store
        ):
            started = time.time()
            res = client.post(
                "/analyze",
                params={"user_id": "11111111-1111-1111-1111-111111111111"},
                files={"file": ("meal.jpg", img_bytes, "image/jpeg")},
            )
            elapsed = time.time() - started

        self.assertEqual(res.status_code, 202)
        body = res.json()
        self.assertTrue(str(body.get("job_id") or "").strip())
        self.assertLess(elapsed, 2.5)

        jid = str(body.get("job_id") or "").strip()
        if jid:
            try:
                path = appmod._analysis_job_file_path(jid)
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    @unittest.skipIf(Image is None, "PIL not installed")
    def test_resize_image_for_scan_reduces_large_image(self):
        large = self._image_bytes((2000, 1500))
        out, orig = appmod._resize_image_for_scan(large)
        self.assertIsInstance(out, bytes)
        self.assertLess(len(out), len(large))
        self.assertEqual(orig, {"w": 2000, "h": 1500})

    @unittest.skipIf(Image is None, "PIL not installed")
    def test_resize_image_for_scan_passes_through_small_image(self):
        small = self._image_bytes((640, 480))
        out, orig = appmod._resize_image_for_scan(small)
        self.assertEqual(out, small)
        self.assertEqual(orig, {"w": 640, "h": 480})


if __name__ == "__main__":
    unittest.main()

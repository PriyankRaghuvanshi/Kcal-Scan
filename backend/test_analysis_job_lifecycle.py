import unittest

try:
    import main as appmod
    _IMPORT_ERR = ""
except Exception as e:  # pragma: no cover
    appmod = None
    _IMPORT_ERR = str(e)


@unittest.skipIf(appmod is None, f"main dependencies unavailable: {_IMPORT_ERR}")
class AnalysisJobLifecycleTests(unittest.TestCase):
    def test_job_patch_progress_and_stage(self):
        row = appmod._store_analysis_job_async_best_effort(
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "user_id": "22222222-2222-2222-2222-222222222222",
                "status": "queued",
                "stage": "queued",
                "progress_pct": 5,
                "input_path": "/tmp/no-file",
            }
        )
        self.assertEqual(str(row.get("status")), "queued")

        running = appmod._patch_analysis_job(str(row.get("id")), {"status": "running", "stage": "vision_scan", "progress_pct": 25})
        self.assertEqual(str(running.get("status")), "running")
        self.assertEqual(str(running.get("stage")), "vision_scan")
        self.assertEqual(int(running.get("progress_pct") or 0), 25)

        done = appmod._patch_analysis_job(str(row.get("id")), {"status": "done", "stage": "done", "progress_pct": 100, "result_json": {"ok": True}})
        self.assertEqual(str(done.get("status")), "done")
        self.assertEqual(str(done.get("stage")), "done")
        self.assertEqual(int(done.get("progress_pct") or 0), 100)
        self.assertIsInstance(done.get("result_json"), dict)


if __name__ == "__main__":
    unittest.main()

import unittest

from chain_baseline_snapshots import load_chain_baseline_snapshot, snapshot_file_path


class ChainBaselineSnapshotsTests(unittest.TestCase):
    def test_snapshot_path_shape(self):
        p = snapshot_file_path("mcdonalds", "AU", 1)
        self.assertTrue(str(p).endswith("AU/mcdonalds__v1.json"))

    def test_known_snapshot_readable(self):
        snap = load_chain_baseline_snapshot("mcdonalds", "AU", 1)
        self.assertIsInstance(snap, dict)
        self.assertEqual(str(snap.get("chain_key")), "mcdonalds")


if __name__ == "__main__":
    unittest.main()

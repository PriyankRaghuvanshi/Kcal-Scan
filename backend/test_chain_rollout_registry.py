import unittest

from chain_rollout_registry import get_chain_runtime_config, load_chain_rollout_registry


class ChainRolloutRegistryTests(unittest.TestCase):
    def test_registry_loads(self):
        out = load_chain_rollout_registry(force_reload=True)
        self.assertIsInstance(out, dict)
        self.assertIn("chains", out)

    def test_unknown_chain_fails_safe(self):
        cfg = get_chain_runtime_config("unknown_chain", "US")
        self.assertEqual(str(cfg.get("status")), "unconfigured")
        self.assertEqual(int(cfg.get("registry_version") or 0), 0)
        self.assertEqual(bool(cfg.get("configured")), False)


if __name__ == "__main__":
    unittest.main()

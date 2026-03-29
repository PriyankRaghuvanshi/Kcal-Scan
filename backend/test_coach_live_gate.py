import os
import unittest
from unittest.mock import patch

import coach_live_gate as gate


class CoachLiveGateTests(unittest.TestCase):
    @patch.dict(os.environ, {"COACH_LIVE_CALL_ENABLED": "0"}, clear=False)
    def test_server_disabled(self):
        ok, plan, reason, beta = gate.coach_live_eligible("u1", "pro")
        self.assertFalse(ok)
        self.assertEqual(plan, "pro")
        self.assertEqual(reason, "feature_disabled")
        self.assertFalse(beta)

    @patch.dict(os.environ, {"COACH_LIVE_CALL_ENABLED": "1", "COACH_LIVE_CALL_BETA_USER_IDS": ""}, clear=False)
    def test_advanced_not_eligible(self):
        ok, _, reason, beta = gate.coach_live_eligible("u2", "advanced")
        self.assertFalse(ok)
        self.assertEqual(reason, "upgrade_required")
        self.assertFalse(beta)

    @patch.dict(os.environ, {"COACH_LIVE_CALL_ENABLED": "1", "COACH_LIVE_CALL_BETA_USER_IDS": ""}, clear=False)
    def test_pro_eligible(self):
        ok, _, reason, beta = gate.coach_live_eligible("u3", "pro")
        self.assertTrue(ok)
        self.assertEqual(reason, "plan_ok")
        self.assertFalse(beta)

    @patch.dict(os.environ, {"COACH_LIVE_CALL_ENABLED": "1", "COACH_LIVE_CALL_BETA_USER_IDS": "u4"}, clear=False)
    def test_beta_allowlist_overrides_plan(self):
        ok, _, reason, beta = gate.coach_live_eligible("u4", "elite")
        self.assertTrue(ok)
        self.assertEqual(reason, "beta_allowlist")
        self.assertTrue(beta)

    @patch.dict(os.environ, {"COACH_LIVE_CALL_ENABLED": "1", "COACH_LIVE_CALL_BETA_USER_IDS": ""}, clear=False)
    def test_infinite_eligible(self):
        ok, _, reason, beta = gate.coach_live_eligible("u5", "infinite")
        self.assertTrue(ok)
        self.assertEqual(reason, "plan_ok")
        self.assertFalse(beta)


if __name__ == "__main__":
    unittest.main()

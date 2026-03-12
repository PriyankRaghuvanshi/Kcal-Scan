"""Tests for push rollout: modes, percentage, active-user, dry_run bypass."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from push_rollout import (
    MODES,
    get_push_rollout_mode,
    get_push_test_user_ids,
    is_user_in_rollout_percentage,
    get_user_percentage_bucket,
    can_send_real_push,
    get_user_push_eligibility,
    get_rollout_status,
    get_rollout_percent,
    reset_cache_for_tests,
)


class TestPushRollout(unittest.TestCase):
    def tearDown(self):
        reset_cache_for_tests()
        for k in ("EXPO_PUSH_SENDING_ENABLED", "PUSH_REAL_SEND_MODE", "PUSH_TEST_USER_IDS", "PUSH_ROLLOUT_PERCENT"):
            os.environ.pop(k, None)

    def test_A_allowlist_user_allowed_in_allowlist_only_mode(self):
        with patch.dict(os.environ, {
            "EXPO_PUSH_SENDING_ENABLED": "true",
            "PUSH_REAL_SEND_MODE": "allowlist_only",
            "PUSH_TEST_USER_IDS": "u1,u2,u3",
        }):
            reset_cache_for_tests()
            eligibility = {"has_token": True, "fatigue_6h_ok": True, "fatigue_24h_ok": True}
            allowed, reason = can_send_real_push("u1", dry_run=False, user_activity=eligibility)
            self.assertTrue(allowed)
            self.assertEqual(reason, "allowed_allowlist")

    def test_B_non_allowlist_user_blocked_in_allowlist_only_mode(self):
        with patch.dict(os.environ, {
            "EXPO_PUSH_SENDING_ENABLED": "true",
            "PUSH_REAL_SEND_MODE": "allowlist_only",
            "PUSH_TEST_USER_IDS": "u1,u2",
        }):
            reset_cache_for_tests()
            eligibility = {"has_token": True, "fatigue_6h_ok": True, "fatigue_24h_ok": True}
            allowed, reason = can_send_real_push("u99", dry_run=False, user_activity=eligibility)
            self.assertFalse(allowed)
            self.assertEqual(reason, "allowlist_blocked")

    def test_C_active_user_allowed_in_active_users_only_mode(self):
        with patch.dict(os.environ, {
            "EXPO_PUSH_SENDING_ENABLED": "true",
            "PUSH_REAL_SEND_MODE": "active_users_only",
            "PUSH_ACTIVE_USER_DAYS": "7",
        }):
            reset_cache_for_tests()
            eligibility = {"has_token": True, "active": True, "fatigue_6h_ok": True, "fatigue_24h_ok": True}
            allowed, reason = can_send_real_push("u1", dry_run=False, user_activity=eligibility)
            self.assertTrue(allowed)
            self.assertEqual(reason, "allowed_active_user")

    def test_D_inactive_user_blocked_in_active_users_only_mode(self):
        with patch.dict(os.environ, {
            "EXPO_PUSH_SENDING_ENABLED": "true",
            "PUSH_REAL_SEND_MODE": "active_users_only",
        }):
            reset_cache_for_tests()
            eligibility = {"has_token": True, "active": False, "fatigue_6h_ok": True, "fatigue_24h_ok": True}
            allowed, reason = can_send_real_push("u1", dry_run=False, user_activity=eligibility)
            self.assertFalse(allowed)
            self.assertEqual(reason, "inactive_user")

    def test_E_deterministic_percentage_rollout_allows_correct_users(self):
        with patch.dict(os.environ, {
            "EXPO_PUSH_SENDING_ENABLED": "true",
            "PUSH_REAL_SEND_MODE": "percentage",
            "PUSH_ROLLOUT_PERCENT": "10",
        }):
            reset_cache_for_tests()
            buckets_in = set()
            for i in range(1000):
                uid = f"user_{i}"
                if is_user_in_rollout_percentage(uid, 10):
                    bucket = get_user_percentage_bucket(uid)
                    buckets_in.add(bucket)
            self.assertEqual(buckets_in, set(range(10)))
            allowed_count = sum(1 for i in range(100) if is_user_in_rollout_percentage(f"user_{i}", 10))
            self.assertGreater(allowed_count, 0)
            self.assertLess(allowed_count, 100)

    def test_F_percentage_rollout_blocks_others(self):
        with patch.dict(os.environ, {
            "EXPO_PUSH_SENDING_ENABLED": "true",
            "PUSH_REAL_SEND_MODE": "percentage",
            "PUSH_ROLLOUT_PERCENT": "10",
        }):
            reset_cache_for_tests()
            in_bucket = []
            out_bucket = []
            for i in range(50):
                uid = f"u{i}"
                if is_user_in_rollout_percentage(uid, 10):
                    in_bucket.append(get_user_percentage_bucket(uid))
                else:
                    out_bucket.append(get_user_percentage_bucket(uid))
            self.assertTrue(len(out_bucket) > len(in_bucket) or len(in_bucket) > 0)
            for b in out_bucket:
                self.assertGreaterEqual(b, 10)

    def test_G_dry_run_bypasses_real_send_rollout_block(self):
        with patch.dict(os.environ, {
            "EXPO_PUSH_SENDING_ENABLED": "false",
            "PUSH_REAL_SEND_MODE": "allowlist_only",
        }):
            reset_cache_for_tests()
            allowed, reason = can_send_real_push("random_user", dry_run=True)
            self.assertTrue(allowed)
            self.assertEqual(reason, "dry_run")

    def test_H_invalid_missing_config_falls_back_conservatively(self):
        with patch.dict(os.environ, {}, clear=True):
            reset_cache_for_tests()
            mode = get_push_rollout_mode()
            self.assertEqual(mode, "disabled")
        with patch.dict(os.environ, {"EXPO_PUSH_SENDING_ENABLED": "true"}):
            reset_cache_for_tests()
            mode = get_push_rollout_mode()
            self.assertEqual(mode, "allowlist_only")

    def test_I_response_includes_rollout_fields(self):
        status = get_rollout_status()
        self.assertIn("sending_enabled", status)
        self.assertIn("rollout_mode", status)
        self.assertIn("rollout_percent", status)
        self.assertIn("active_user_days", status)
        self.assertIn("max_per_6h", status)
        self.assertIn("max_per_24h", status)
        self.assertIn("allowlist_count", status)

    def test_percentage_deterministic_same_user_same_bucket(self):
        bucket1 = get_user_percentage_bucket("user_123")
        bucket2 = get_user_percentage_bucket("user_123")
        self.assertEqual(bucket1, bucket2)

    def test_fatigue_limit_blocks_when_over_limit(self):
        with patch.dict(os.environ, {
            "EXPO_PUSH_SENDING_ENABLED": "true",
            "PUSH_REAL_SEND_MODE": "allowlist_only",
            "PUSH_TEST_USER_IDS": "u1",
        }):
            reset_cache_for_tests()
            eligibility = {
                "has_token": True,
                "active": True,
                "fatigue_6h_ok": False,
                "fatigue_24h_ok": True,
            }
            allowed, reason = can_send_real_push("u1", dry_run=False, user_activity=eligibility)
            self.assertFalse(allowed)
            self.assertEqual(reason, "fatigue_limit_6h")


if __name__ == "__main__":
    unittest.main()

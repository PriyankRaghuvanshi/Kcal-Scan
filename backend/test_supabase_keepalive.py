import os
import unittest
from unittest.mock import MagicMock, patch

import requests

import supabase_keepalive as ka


def _resp(status: int) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    return r


class KeepaliveIntervalTests(unittest.TestCase):
    @patch.dict(os.environ, {"SUPABASE_KEEPALIVE_INTERVAL_SECONDS": ""}, clear=False)
    def test_default_interval(self):
        self.assertEqual(ka.keepalive_interval_seconds(), 600)

    @patch.dict(os.environ, {"SUPABASE_KEEPALIVE_INTERVAL_SECONDS": "0"}, clear=False)
    def test_zero_disables(self):
        self.assertEqual(ka.keepalive_interval_seconds(), 0)

    @patch.dict(os.environ, {"SUPABASE_KEEPALIVE_INTERVAL_SECONDS": "5"}, clear=False)
    def test_floor_is_sixty_seconds(self):
        self.assertEqual(ka.keepalive_interval_seconds(), 60)

    @patch.dict(os.environ, {"SUPABASE_KEEPALIVE_INTERVAL_SECONDS": "abc"}, clear=False)
    def test_invalid_falls_back_to_default(self):
        self.assertEqual(ka.keepalive_interval_seconds(), 600)


class PingOnceTests(unittest.TestCase):
    def test_success_hits_rest_table_with_service_key(self):
        http_get = MagicMock(return_value=_resp(200))
        ok = ka.ping_once("https://x.supabase.co/", "svc", table="plan_limits", http_get=http_get)
        self.assertTrue(ok)
        args, kwargs = http_get.call_args
        self.assertEqual(args[0], "https://x.supabase.co/rest/v1/plan_limits")
        self.assertEqual(kwargs["headers"]["apikey"], "svc")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer svc")
        self.assertEqual(kwargs["params"]["limit"], "1")

    def test_hibernating_503_returns_false(self):
        http_get = MagicMock(return_value=_resp(503))
        self.assertFalse(ka.ping_once("https://x.supabase.co", "svc", http_get=http_get))

    def test_network_error_never_raises(self):
        http_get = MagicMock(side_effect=requests.ConnectionError("down"))
        self.assertFalse(ka.ping_once("https://x.supabase.co", "svc", http_get=http_get))

    def test_missing_config_skips_request(self):
        http_get = MagicMock()
        self.assertFalse(ka.ping_once("", "svc", http_get=http_get))
        self.assertFalse(ka.ping_once("https://x.supabase.co", "", http_get=http_get))
        http_get.assert_not_called()


class StartThreadTests(unittest.TestCase):
    def setUp(self):
        ka._started = False

    def tearDown(self):
        ka._started = False

    def test_not_started_without_config(self):
        self.assertIsNone(ka.start_keepalive_thread("", ""))

    @patch.dict(os.environ, {"SUPABASE_KEEPALIVE_INTERVAL_SECONDS": "0"}, clear=False)
    def test_not_started_when_disabled(self):
        self.assertIsNone(ka.start_keepalive_thread("https://x.supabase.co", "svc"))

    @patch.dict(os.environ, {"SUPABASE_KEEPALIVE_INTERVAL_SECONDS": "600"}, clear=False)
    def test_starts_once_and_pings_immediately(self):
        def _sleep(_secs):
            # SystemExit ends the worker thread quietly after its first ping.
            raise SystemExit()

        with patch.object(ka, "ping_once", return_value=True) as ping:
            t = ka.start_keepalive_thread("https://x.supabase.co", "svc", sleep=_sleep)
            self.assertIsNotNone(t)
            t.join(timeout=2)
            ping.assert_called_once_with("https://x.supabase.co", "svc")
            # Second call in the same process does not start another thread.
            self.assertIsNone(ka.start_keepalive_thread("https://x.supabase.co", "svc", sleep=_sleep))


if __name__ == "__main__":
    unittest.main()

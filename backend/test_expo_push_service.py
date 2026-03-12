"""Tests for Expo push service."""
from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    import requests  # noqa: F401
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from expo_push_service import (
    build_expo_push_message,
    send_expo_push_messages,
    fetch_expo_push_receipts,
    is_device_not_registered,
)


class TestBuildExpoPushMessage(unittest.TestCase):
    def test_build_message_includes_required_fields(self):
        candidate = {
            "title": "Protein rescue",
            "body": "Best nearby: Chipotle",
            "place_id": "ChIJ123",
            "place_name": "Chipotle",
            "best_item_name": "Chicken Bowl",
            "alert_type": "protein_rescue",
            "display_rank_score_100": 85,
            "context_mode": "default",
        }
        msg = build_expo_push_message(candidate, "ExponentPushToken[abc]")
        self.assertEqual(msg["to"], "ExponentPushToken[abc]")
        self.assertEqual(msg["title"], "Protein rescue")
        self.assertEqual(msg["body"], "Best nearby: Chipotle")
        self.assertEqual(msg["sound"], "default")
        self.assertIn("data", msg)
        self.assertEqual(msg["data"]["alert_type"], "protein_rescue")
        self.assertEqual(msg["data"]["place_id"], "ChIJ123")
        self.assertEqual(msg["data"]["place_name"], "Chipotle")
        self.assertEqual(msg["data"]["best_item_name"], "Chicken Bowl")
        self.assertEqual(msg["data"]["display_rank_score_100"], 85)

    def test_alert_id_format(self):
        candidate = {
            "alert_type": "protein_rescue",
            "place_id": "p1",
            "best_item_name": "Salad",
        }
        msg = build_expo_push_message(candidate, "ExponentPushToken[x]")
        self.assertEqual(msg["data"]["alert_id"], "protein_rescue::p1::Salad")

    def test_deep_link_and_route_target_in_data(self):
        candidate = {
            "alert_type": "protein_rescue",
            "place_id": "ChIJ123",
            "place_name": "Subway",
            "best_item_name": "6-inch Grilled Chicken",
            "place_lat": -33.8,
            "place_lng": 151.0,
        }
        msg = build_expo_push_message(candidate, "ExponentPushToken[x]")
        data = msg["data"]
        self.assertIn("deep_link", data)
        self.assertIn("calorieclick://smart-alert", data["deep_link"])
        self.assertIn("place_id=ChIJ123", data["deep_link"])
        self.assertEqual(data["route_target"], "smart_alert_place")
        self.assertEqual(data["place_lat"], -33.8)
        self.assertEqual(data["place_lng"], 151.0)


class TestSendExpoPushMessages(unittest.TestCase):
    def test_dry_run_returns_simulated_tickets(self):
        msgs = [
            {"to": "ExponentPushToken[a]", "title": "T", "body": "B"},
        ]
        result = send_expo_push_messages(msgs, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["sent_count"], 1)
        self.assertEqual(len(result["tickets"]), 1)
        self.assertEqual(result["tickets"][0]["status"], "ok")
        self.assertIn("id", result["tickets"][0])

    def test_empty_messages(self):
        result = send_expo_push_messages([], dry_run=False)
        self.assertEqual(result["sent_count"], 0)
        self.assertEqual(result["tickets"], [])

    @unittest.skipUnless(HAS_REQUESTS, "requests required for batching test")
    @patch("requests.post")
    def test_batching_splits_large_list(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "data": [{"status": "ok", "id": f"tid-{i}"} for i in range(55)],
        }
        msgs = [
            {"to": f"ExponentPushToken[{i}]", "title": "T", "body": "B"}
            for i in range(55)
        ]
        result = send_expo_push_messages(msgs, dry_run=False)
        self.assertGreaterEqual(mock_post.call_count, 2)
        self.assertEqual(result["sent_count"], 55)


class TestIsDeviceNotRegistered(unittest.TestCase):
    def test_detects_device_not_registered(self):
        self.assertTrue(
            is_device_not_registered({"details": {"error": "DeviceNotRegistered"}})
        )

    def test_other_errors_not_matched(self):
        self.assertFalse(
            is_device_not_registered({"details": {"error": "InvalidCredentials"}})
        )
        self.assertFalse(is_device_not_registered({"status": "ok"}))

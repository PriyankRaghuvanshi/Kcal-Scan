"""Tests for push send-smart-alerts: fallback when top candidate suppressed."""
from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    HAS_CLIENT = True
except ImportError:
    HAS_CLIENT = False

try:
    import main as appmod
except ImportError:
    appmod = None


PLACES_RESPONSE = {
    "items": [
        {
            "place_id": "p1",
            "name": "Subway",
            "lat": -33.87,
            "lng": 151.2,
            "display_rank_score_100": 82,
            "best_item_name": "Chicken Sub",
            "best_item_protein": 32,
            "distance_meters": 400,
            "confidence_label": "Verified",
        },
        {
            "place_id": "p2",
            "name": "Grill'd",
            "lat": -33.87,
            "lng": 151.21,
            "display_rank_score_100": 78,
            "best_item_name": "Burger",
            "best_item_protein": 28,
            "distance_meters": 500,
            "confidence_label": "Estimated",
        },
    ],
}


@unittest.skipIf(appmod is None, "main not importable")
@unittest.skipIf(not HAS_CLIENT, "TestClient not available")
class TestPushSendSmartAlertsFallback(unittest.TestCase):
    """Candidate #1 suppressed, #2 sent."""

    def test_candidate_1_suppressed_tries_candidate_2(self):
        """When top candidate is duplicate-suppressed for all tokens, try next eligible."""
        client = TestClient(appmod.app)
        payload = {
            "user_id": "test-user-123",
            "lat": -33.87,
            "lng": 151.2,
            "dry_run": True,
            "eligible_only": True,
            "context": {
                "remaining_protein_g": 30,
                "remaining_calories": 500,
                "local_hour": 18,
            },
            "fatigue": {"recent_alerts_count_6h": 0, "recent_alerts_count_24h": 0},
        }

        def mock_was_recently_sent(user_id, token, alert_id):
            if "p1" in alert_id:
                return True
            return False

        async def mock_healthy_places(*args, **kwargs):
            return PLACES_RESPONSE

        with patch.object(appmod, "was_recently_sent", side_effect=mock_was_recently_sent), \
             patch.object(appmod, "healthy_places", mock_healthy_places), \
             patch.object(appmod, "list_tokens_for_user") as mock_tokens:
            mock_tokens.return_value = [
                {"expo_push_token": "ExponentPushToken[test-token]"},
            ]
            res = client.post("/push/send-smart-alerts", json=payload)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("candidate_sent_rank"), 2)
        self.assertEqual(body.get("candidates_skipped_as_duplicate"), 1)
        self.assertIn("notifications_attempted", body)
        self.assertIsNone(body.get("final_suppressed_reason"))

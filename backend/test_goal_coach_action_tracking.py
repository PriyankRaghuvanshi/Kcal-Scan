"""Tests for Goal Coach action funnel tracking."""

import os
import unittest

from goal_coach_action_tracking import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_ACTION_TYPES,
    ALLOWED_SOURCE_SURFACES,
    log_goal_coach_event,
    list_goal_coach_events,
    _env_path,
    _empty_store,
    _save_store,
)


class GoalCoachActionTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_env = os.environ.get("GOAL_COACH_ACTION_TRACKING_PATH")
        self._test_path = _env_path().parent / "goal_coach_action_events_test.json"
        os.environ["GOAL_COACH_ACTION_TRACKING_PATH"] = str(self._test_path)
        _save_store(_empty_store())

    def tearDown(self) -> None:
        if self._orig_env is not None:
            os.environ["GOAL_COACH_ACTION_TRACKING_PATH"] = self._orig_env
        else:
            os.environ.pop("GOAL_COACH_ACTION_TRACKING_PATH", None)
        if self._test_path.exists():
            self._test_path.unlink()

    def test_daily_action_shown_includes_metadata(self) -> None:
        payload = {
            "event_type": "goal_coach_daily_action_shown",
            "user_id": "user-daily-shown",
            "source_surface": "daily_coach",
            "action_type": "open_healthy_nearby",
            "goal_type": "fat_loss",
            "reason": "Protein is behind today",
            "remaining_protein_g": 42,
            "remaining_calories": 780,
            "kickoff_active": True,
            "subscription_required": False,
        }
        row = log_goal_coach_event(payload)
        self.assertEqual(row["event_type"], "goal_coach_daily_action_shown")
        self.assertEqual(row["user_id"], "user-daily-shown")
        self.assertEqual(row["source_surface"], "daily_coach")
        self.assertEqual(row["action_type"], "open_healthy_nearby")
        self.assertEqual(row["goal_type"], "fat_loss")
        self.assertEqual(row["reason"], "Protein is behind today")
        self.assertEqual(row["remaining_protein_g"], 42)
        self.assertEqual(row["remaining_calories"], 780)
        self.assertTrue(row["kickoff_active"])
        self.assertFalse(row["subscription_required"])
        self.assertIn("event_id", row)
        self.assertIn("timestamp", row)

    def test_weekly_action_clicked_includes_metadata(self) -> None:
        payload = {
            "event_type": "goal_coach_weekly_action_clicked",
            "user_id": "user-weekly-clicked",
            "source_surface": "weekly_review",
            "action_type": "open_scan_camera",
            "goal_type": "fat_loss",
            "reason": "Log meals more consistently",
        }
        row = log_goal_coach_event(payload)
        self.assertEqual(row["event_type"], "goal_coach_weekly_action_clicked")
        self.assertEqual(row["user_id"], "user-weekly-clicked")
        self.assertEqual(row["source_surface"], "weekly_review")
        self.assertEqual(row["action_type"], "open_scan_camera")

    def test_destination_opened_and_completed(self) -> None:
        log_goal_coach_event({
            "event_type": "goal_coach_destination_opened",
            "user_id": "user-dest",
            "source_surface": "daily_coach",
            "action_type": "open_healthy_nearby",
            "remaining_protein_g": 35,
        })
        row = log_goal_coach_event({
            "event_type": "goal_coach_action_completed",
            "user_id": "user-dest",
            "action_type": "open_healthy_nearby",
            "completion_type": "place_selected",
            "place_id": "ChIJx",
            "place_name": "Test Cafe",
        })
        self.assertEqual(row["event_type"], "goal_coach_action_completed")
        self.assertEqual(row["completion_type"], "place_selected")
        self.assertEqual(row["place_id"], "ChIJx")
        self.assertEqual(row["place_name"], "Test Cafe")

    def test_invalid_event_type_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            log_goal_coach_event({"event_type": "invalid_event", "user_id": "u1"})
        self.assertIn("invalid_event_type", str(ctx.exception))

    def test_missing_user_id_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            log_goal_coach_event({"event_type": "goal_coach_daily_action_shown"})
        self.assertIn("user_id", str(ctx.exception))

    def test_list_events_filter_by_user_and_type(self) -> None:
        log_goal_coach_event({
            "event_type": "goal_coach_daily_action_shown",
            "user_id": "user-a",
            "source_surface": "daily_coach",
            "action_type": "open_healthy_nearby",
        })
        log_goal_coach_event({
            "event_type": "goal_coach_daily_action_clicked",
            "user_id": "user-a",
            "source_surface": "daily_coach",
            "action_type": "open_healthy_nearby",
        })
        log_goal_coach_event({
            "event_type": "goal_coach_daily_action_shown",
            "user_id": "user-b",
            "source_surface": "daily_coach",
            "action_type": "open_scan_camera",
        })
        shown_a = list_goal_coach_events(user_id="user-a", event_type="goal_coach_daily_action_shown", limit=10)
        self.assertEqual(len(shown_a), 1)
        self.assertEqual(shown_a[0]["user_id"], "user-a")
        self.assertEqual(shown_a[0]["event_type"], "goal_coach_daily_action_shown")
        all_a = list_goal_coach_events(user_id="user-a", limit=10)
        self.assertEqual(len(all_a), 2)
        all_b = list_goal_coach_events(user_id="user-b", limit=10)
        self.assertEqual(len(all_b), 1)


if __name__ == "__main__":
    unittest.main()

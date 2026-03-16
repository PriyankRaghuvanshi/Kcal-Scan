import unittest

from goal_coach import (
    GOAL_COACH_VERSION,
    ACTION_OPEN_HEALTHY_NEARBY,
    ACTION_OPEN_SCAN_CAMERA,
    ACTION_OPEN_DAILY_SUMMARY,
    build_daily_coach_state,
    build_daily_suggested_actions,
    build_starter_plan,
    build_weekly_review,
    build_weekly_next_step_action,
    compute_kickoff_status,
)


class GoalCoachTests(unittest.TestCase):
    def test_starter_plan_basic_fields(self) -> None:
        plan_input = {
            "goal_type": "fat_loss",
            "pace_mode": "balanced",
            "timeframe_weeks": 10,
            "training_days_per_week": 3,
            "diet_preference": "mediterranean",
            "current_weight": 80.0,
        }
        starter = build_starter_plan(plan_input)
        self.assertEqual(starter["goal_type"], "fat_loss")
        self.assertGreater(starter["target_calories"], 0)
        self.assertGreater(starter["target_protein_g"], 0)
        self.assertIn("weekly_focus", starter)
        self.assertIn("risk_note", starter)
        self.assertEqual(starter["version"], GOAL_COACH_VERSION)

    def test_daily_coach_state_progress_and_focus(self) -> None:
        plan = {
            "goal_type": "fat_loss",
            "target_calories": 2000,
            "target_protein_g": 140,
        }
        daily_metrics = {
            "date": "2026-03-10",
            "consumed_calories": 1300,
            "consumed_protein_g": 40,
        }
        mem = {"late_night_snacking": True}
        state = build_daily_coach_state(plan, daily_metrics, mem)
        self.assertEqual(state["goal_type"], "fat_loss")
        self.assertGreater(state["remaining"]["calories"], 0)
        self.assertIn("one_action_today", state)
        self.assertIn("late_night_snacking_pattern", state["risk_flags"])

    def test_weekly_review_scores_and_focus(self) -> None:
        plan = {"goal_type": "fat_loss"}
        days = [
            {
                "date": "2026-03-01",
                "consumed_calories": 1900,
                "target_calories": 2000,
                "consumed_protein_g": 130,
                "target_protein_g": 140,
            },
            {
                "date": "2026-03-02",
                "consumed_calories": 2100,
                "target_calories": 2000,
                "consumed_protein_g": 120,
                "target_protein_g": 140,
            },
            {
                "date": "2026-03-03",
                "consumed_calories": 2050,
                "target_calories": 2000,
                "consumed_protein_g": 110,
                "target_protein_g": 140,
            },
        ]
        mem = {"weekend_overeating": True}
        review = build_weekly_review(plan, days, mem)
        self.assertIn("adherence_score", review)
        self.assertIn("risk_score", review)
        self.assertIn("main_win", review)
        self.assertIn("main_bottleneck", review)
        self.assertIn("weekend_overeating", review.get("habit_memory_flags", []))

    def test_kickoff_status_free_period(self) -> None:
        plan = {"created_at": "2026-03-01T00:00:00Z"}
        status = compute_kickoff_status(plan)
        self.assertEqual(status["free_kickoff_days"], 7)
        self.assertIn("requires_subscription", status)

    def test_daily_suggested_actions_protein_behind_healthy_nearby(self) -> None:
        state = {
            "goal_type": "fat_loss",
            "remaining": {"calories": 780, "protein_g": 42},
            "consumed": {"calories": 820, "protein_g": 58},
            "risk_flags": ["protein_gap"],
            "coach_focus": "protein_first",
        }
        actions = build_daily_suggested_actions(state, current_hour_local=12)
        self.assertIn("primary_action", actions)
        primary = actions["primary_action"]
        self.assertIsNotNone(primary)
        self.assertEqual(primary["action_type"], ACTION_OPEN_HEALTHY_NEARBY)
        self.assertIn("high-protein", primary["label"].lower())
        self.assertIn("context", primary)
        self.assertEqual(primary["context"]["remaining_protein_g"], 42)

    def test_daily_suggested_actions_logging_needed_scan(self) -> None:
        state = {
            "goal_type": "fat_loss",
            "remaining": {"calories": 1800, "protein_g": 120},
            "consumed": {"calories": 200, "protein_g": 10},
            "risk_flags": [],
            "coach_focus": "calorie_drift",
        }
        actions = build_daily_suggested_actions(state, current_hour_local=10)
        self.assertIn("primary_action", actions)
        primary = actions["primary_action"]
        self.assertIsNotNone(primary)
        self.assertEqual(primary["action_type"], ACTION_OPEN_SCAN_CAMERA)
        self.assertIn("log", primary["label"].lower())

    def test_daily_suggested_actions_calories_tight_daily_summary(self) -> None:
        state = {
            "goal_type": "fat_loss",
            "remaining": {"calories": 280, "protein_g": 25},
            "consumed": {"calories": 1720, "protein_g": 100},
            "risk_flags": ["protein_behind_high_calories"],
            "coach_focus": "protein_first",
        }
        actions = build_daily_suggested_actions(state, current_hour_local=14)
        self.assertIn("primary_action", actions)
        primary = actions["primary_action"]
        self.assertIsNotNone(primary)
        self.assertEqual(primary["action_type"], ACTION_OPEN_DAILY_SUMMARY)

    def test_weekly_next_step_action_protein_focus(self) -> None:
        review = {
            "goal_type": "fat_loss",
            "main_bottleneck": "Protein dipped on too many days.",
            "next_week_focus": {"headline": "Focus on protein", "supporting_text": "Add one more protein meal."},
            "summary": {"days_tracked": 5, "days_under_protein": 3, "days_over_target": 1},
        }
        action = build_weekly_next_step_action(review)
        self.assertIsNotNone(action)
        self.assertEqual(action["action_type"], ACTION_OPEN_HEALTHY_NEARBY)
        self.assertIn("protein", action["label"].lower())

    def test_weekly_next_step_action_logging_focus(self) -> None:
        review = {
            "goal_type": "fat_loss",
            "main_bottleneck": "Drift on unplanned meals.",
            "next_week_focus": {"headline": "Focus on logging 5 days next week.", "supporting_text": "More consistent logging."},
            "summary": {"days_tracked": 3},
        }
        action = build_weekly_next_step_action(review)
        self.assertIsNotNone(action)
        self.assertEqual(action["action_type"], ACTION_OPEN_SCAN_CAMERA)


if __name__ == "__main__":
    unittest.main()


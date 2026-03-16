import os
import tempfile
import unittest

from goal_plan_store import (
    clear_goal_plan_store_for_tests,
    create_goal_plan,
    get_active_goal_plan,
    list_goal_plans_for_user,
    update_goal_plan_status,
)


class GoalPlanStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["GOAL_PLAN_STORE_PATH"] = os.path.join(self.tmpdir.name, "goal_plans.json")
        os.environ["GOAL_PLAN_ALLOW_CLEAR"] = "1"
        clear_goal_plan_store_for_tests()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        os.environ.pop("GOAL_PLAN_STORE_PATH", None)
        os.environ.pop("GOAL_PLAN_ALLOW_CLEAR", None)

    def test_create_and_get_active_plan(self) -> None:
        starter = {"target_calories": 2000}
        created = create_goal_plan(
            "user-1",
            {"goal_type": "fat_loss", "pace_mode": "balanced", "timeframe_weeks": 8},
            starter,
        )
        self.assertEqual(created["user_id"], "user-1")
        active = get_active_goal_plan("user-1")
        self.assertIsNotNone(active)
        self.assertEqual(active["plan_id"], created["plan_id"])
        self.assertEqual(active["starter_plan"]["target_calories"], 2000)

    def test_update_status_and_only_one_active(self) -> None:
        starter = {"target_calories": 2100}
        p1 = create_goal_plan("user-2", {"goal_type": "fat_loss"}, starter)
        p2 = create_goal_plan("user-2", {"goal_type": "muscle_gain"}, starter)
        self.assertNotEqual(p1["plan_id"], p2["plan_id"])

        # Pause all then resume latest.
        updated = update_goal_plan_status("user-2", "paused")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "paused")

        updated_active = update_goal_plan_status("user-2", "active")
        self.assertIsNotNone(updated_active)
        self.assertEqual(updated_active["status"], "active")

        plans = list_goal_plans_for_user("user-2")
        active_count = sum(1 for p in plans if p["status"] == "active")
        self.assertEqual(active_count, 1)

    def test_list_plans_respects_limit(self) -> None:
        starter = {"target_calories": 1900}
        for i in range(7):
            create_goal_plan("user-3", {"goal_type": "fat_loss", "timeframe_weeks": i + 4}, starter)
        plans_3 = list_goal_plans_for_user("user-3", limit=3)
        self.assertLessEqual(len(plans_3), 3)


if __name__ == "__main__":
    unittest.main()


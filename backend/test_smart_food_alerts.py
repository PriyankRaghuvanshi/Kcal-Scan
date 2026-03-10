"""
Tests for Smart Food Alerts: candidate generation, scoring, suppression.
"""
from __future__ import annotations

import unittest

from smart_food_alerts import (
    build_smart_food_alert_candidates,
    build_alert_audit_one_liner,
)


def _place(
    name: str = "Subway",
    place_id: str = "p1",
    display_rank_score_100: int = 78,
    best_item_name: str = "Grilled chicken sub",
    best_item_protein: int = 32,
    best_item_calories: int = 450,
    distance_meters: int = 320,
    confidence_label: str = "Verified",
    recommendation_label: str = "Best pick",
    personal_memory_label: str = "",
    worked_before: bool = False,
    **kwargs,
) -> dict:
    d = {
        "name": name,
        "place_name": name,
        "place_id": place_id,
        "display_rank_score_100": display_rank_score_100,
        "best_item_name": best_item_name,
        "best_item_protein": best_item_protein,
        "best_item_calories": best_item_calories,
        "estimated_protein_g": best_item_protein,
        "estimated_calories": best_item_calories,
        "distance_meters": distance_meters,
        "confidence_label": confidence_label,
        "recommendation_label": recommendation_label,
        "personal_memory_label": personal_memory_label,
        "worked_before": worked_before,
    }
    d.update(kwargs)
    return d


class TestProteinRescue(unittest.TestCase):
    """A. protein rescue: user short on protein, strong nearby option → eligible."""

    def test_protein_rescue_eligible(self):
        places = [
            _place("Subway", "p1", 82, "Grilled chicken sub", 35, 480, 400, "Verified", "Best pick"),
        ]
        user_ctx = {
            "remaining_protein_g": 40,
            "remaining_calories": 600,
            "local_hour": 18,
            "context_mode": "dinner_mode",
            "recent_alerts_count_6h": 0,
            "recent_alerts_count_24h": 0,
        }
        candidates = build_smart_food_alert_candidates(user_ctx, places, eligible_only=False)
        protein_rescue = [c for c in candidates if c["alert_type"] == "protein_rescue"]
        self.assertGreater(len(protein_rescue), 0, "should have protein_rescue candidate")
        c = protein_rescue[0]
        self.assertTrue(c["eligible_to_send"], "should be eligible when context fits")
        self.assertIn("protein", c["why_triggered"].lower())
        self.assertIn("Subway", c["place_name"])


class TestPostWorkoutRecovery(unittest.TestCase):
    """B. post-workout: post_workout true, strong recovery meal → positive candidate."""

    def test_post_workout_eligible(self):
        places = [
            _place("Indian Grill", "p2", 75, "Tandoori chicken + dal", 42, 520, 500, "Estimated", "Strong option"),
        ]
        user_ctx = {
            "remaining_protein_g": 35,
            "post_workout": True,
            "context_mode": "post_workout_recovery",
            "local_hour": 19,
        }
        candidates = build_smart_food_alert_candidates(user_ctx, places, eligible_only=False)
        pw = [c for c in candidates if c["alert_type"] == "post_workout_recovery"]
        self.assertGreater(len(pw), 0)
        self.assertGreater(pw[0]["alert_score"], 0)
        self.assertIn("recovery", pw[0]["body"].lower())


class TestLateNightDamageControl(unittest.TestCase):
    """C. late-night: local_hour >= 21, lighter meal → good candidate."""

    def test_late_night_eligible(self):
        places = [
            _place("Cafe", "p3", 70, "Grilled wrap", 28, 380, 600, "Estimated", "Strong option"),
        ]
        user_ctx = {
            "remaining_protein_g": 20,
            "local_hour": 22,
            "context_mode": "late_night_damage_control",
        }
        candidates = build_smart_food_alert_candidates(user_ctx, places, eligible_only=False)
        ln = [c for c in candidates if c["alert_type"] == "late_night_damage_control"]
        self.assertGreater(len(ln), 0)
        self.assertGreater(ln[0]["alert_score"], 0)


class TestWorkedBeforeRepeat(unittest.TestCase):
    """D. worked_before: strong personal memory label, place nearby, fits → candidate."""

    def test_worked_before_eligible(self):
        places = [
            _place(
                "Darbar",
                "p4",
                72,
                "Tandoori chicken",
                40,
                550,
                450,
                "Verified",
                "Best pick",
                personal_memory_label="Worked well before",
                worked_before=True,
            ),
        ]
        user_ctx = {
            "remaining_protein_g": 30,
            "local_hour": 12,
        }
        candidates = build_smart_food_alert_candidates(user_ctx, places, eligible_only=False)
        wb = [c for c in candidates if c["alert_type"] == "worked_before_repeat"]
        self.assertGreater(len(wb), 0)
        self.assertIn("Worked well before", wb[0].get("personal_memory_label", ""))


class TestHabitRescue(unittest.TestCase):
    """Habit rescue: poor_sleep or high_craving_risk, strong nearby → candidate."""

    def test_habit_rescue_eligible(self):
        places = [
            _place("Grill", "p1", 75, "Grilled chicken bowl", 35, 480, 400, "Estimated", "Strong option"),
        ]
        user_ctx = {
            "remaining_protein_g": 25,
            "local_hour": 14,
            "high_craving_risk_flag": True,
        }
        candidates = build_smart_food_alert_candidates(user_ctx, places, eligible_only=False)
        hr = [c for c in candidates if c["alert_type"] == "habit_rescue"]
        self.assertGreater(len(hr), 0)
        self.assertEqual(hr[0]["alert_type"], "habit_rescue")


class TestSuppressionRules(unittest.TestCase):
    """E. suppression: too many alerts, ignored streak → suppressed."""

    def test_too_many_recent_alerts_suppressed(self):
        places = [
            _place("Subway", "p1", 85, "Chicken sub", 35, 450, 300, "Verified", "Best pick"),
        ]
        user_ctx = {
            "remaining_protein_g": 40,
            "local_hour": 18,
            "recent_alerts_count_6h": 1,
            "recent_alerts_count_24h": 2,
            "weekly_alert_count": 5,
        }
        candidates = build_smart_food_alert_candidates(user_ctx, places, eligible_only=False)
        for c in candidates:
            self.assertIn("max_alerts_6h", c["suppression_reasons"], "should be suppressed")
            self.assertFalse(c["eligible_to_send"])

    def test_ignored_streak_suppressed(self):
        places = [
            _place("Subway", "p1", 80, "Chicken sub", 32, 450, 200, "Verified", "Best pick"),
        ]
        user_ctx = {
            "remaining_protein_g": 35,
            "local_hour": 18,
            "ignored_streak": 3,
        }
        candidates = build_smart_food_alert_candidates(user_ctx, places, eligible_only=False)
        for c in candidates:
            self.assertIn("ignored_streak", c["suppression_reasons"])
            self.assertFalse(c["eligible_to_send"])


class TestWeakConfidenceSuppression(unittest.TestCase):
    """F. weak confidence: Needs menu check → not eligible."""

    def test_needs_menu_check_suppressed(self):
        places = [
            _place("Unknown Cafe", "p1", 70, "Lighter option", 25, 400, 500, "Needs menu check", "Needs menu check"),
        ]
        user_ctx = {
            "remaining_protein_g": 40,
            "local_hour": 18,
        }
        candidates = build_smart_food_alert_candidates(user_ctx, places, eligible_only=False)
        eligible = [c for c in candidates if c["eligible_to_send"]]
        self.assertEqual(len(eligible), 0, "Needs menu check should not produce eligible alerts")


class TestNoStrongNearbyOptions(unittest.TestCase):
    """G. no strong options → no eligible candidates."""

    def test_weak_places_no_eligible(self):
        places = [
            _place("Low Score", "p1", 45, "Combo meal", 15, 800, 1000, "Estimated", "Suggested healthier pick"),
        ]
        user_ctx = {
            "remaining_protein_g": 40,
            "local_hour": 18,
        }
        candidates = build_smart_food_alert_candidates(user_ctx, places, eligible_only=True)
        self.assertEqual(len(candidates), 0)

    def test_empty_places_no_candidates(self):
        candidates = build_smart_food_alert_candidates({}, [])
        self.assertEqual(candidates, [])


class TestPayloadShape(unittest.TestCase):
    """H. API returns required fields."""

    def test_candidate_has_required_fields(self):
        places = [
            _place("Subway", "p1", 78, "Chicken sub", 32, 450, 300, "Verified", "Best pick"),
        ]
        user_ctx = {"remaining_protein_g": 35, "local_hour": 18}
        candidates = build_smart_food_alert_candidates(user_ctx, places)
        required = [
            "alert_type",
            "alert_score",
            "title",
            "body",
            "place_id",
            "place_name",
            "best_item_name",
            "display_rank_score_100",
            "distance_m",
            "estimated_calories",
            "estimated_protein_g",
            "confidence_label",
            "recommendation_label",
            "personal_memory_label",
            "context_mode",
            "why_triggered",
            "suppression_reasons",
            "eligible_to_send",
        ]
        for c in candidates:
            for k in required:
                self.assertIn(k, c, f"candidate missing field: {k}")


class TestAuditOneLiner(unittest.TestCase):
    def test_audit_one_liner_format(self):
        from smart_food_alerts import build_alert_audit_one_liner
        c = {
            "alert_type": "protein_rescue",
            "alert_score": 91,
            "place_name": "Subway",
            "estimated_protein_g": 30,
            "distance_m": 320,
            "eligible_to_send": True,
            "suppression_reasons": [],
        }
        line = build_alert_audit_one_liner(c)
        self.assertIn("protein_rescue", line)
        self.assertIn("91", line)
        self.assertIn("Subway", line)
        self.assertIn("eligible", line)


if __name__ == "__main__":
    unittest.main()

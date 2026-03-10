from __future__ import annotations

import unittest

from personal_response_summary import PersonalMemory, compute_personal_memory_modifier
from ranked_place_builder import build_ranked_place_profile


class TestPersonalMemoryModifier(unittest.TestCase):
    def test_below_threshold_no_memory(self):
        mem = PersonalMemory(
            worked_before=True,
            personal_memory_label="Worked well before",
            times_chosen=2,
            repeat_success_rate=0.8,
            swap_accept_rate=0.7,
            avg_fullness=4.0,
            avg_craving_score=1.5,
        )
        out = compute_personal_memory_modifier(
            mem,
            base_score_100=75,
            food_quality_score_100=70,
            protein_density_score_100=65,
        )
        self.assertFalse(out["memory_applied"])
        self.assertEqual(out["personal_history_net_100"], 0)
        self.assertEqual(out["personal_memory_reason"], "not_enough_data")

    def test_positive_memory_bounded(self):
        mem = PersonalMemory(
            worked_before=True,
            personal_memory_label="Worked well before",
            times_chosen=5,
            repeat_success_rate=0.9,
            swap_accept_rate=0.7,
            avg_fullness=4.5,
            avg_craving_score=1.0,
        )
        out = compute_personal_memory_modifier(
            mem,
            base_score_100=80,
            food_quality_score_100=80,
            protein_density_score_100=75,
        )
        self.assertTrue(out["memory_applied"])
        self.assertGreater(out["personal_history_net_100"], 0)
        self.assertLessEqual(out["personal_history_net_100"], 6)

    def test_negative_memory_bounded(self):
        mem = PersonalMemory(
            worked_before=False,
            personal_memory_label="Often followed by cravings",
            times_chosen=4,
            repeat_success_rate=0.2,
            swap_accept_rate=0.1,
            avg_fullness=2.0,
            avg_craving_score=4.5,
        )
        out = compute_personal_memory_modifier(
            mem,
            base_score_100=72,
            food_quality_score_100=70,
            protein_density_score_100=60,
        )
        self.assertTrue(out["memory_applied"])
        self.assertLess(out["personal_history_net_100"], 0)
        self.assertGreaterEqual(out["personal_history_net_100"], -6)


class TestPersonalMemoryIntegration(unittest.TestCase):
    def test_weak_meal_not_rescued_by_memory(self):
        """Weak processed meal should not get large boost from positive memory."""
        base_place = {
            "name": "Pizza Place",
            "recommended_order": "Loaded pizza combo",
            "estimated_calories": 900,
            "estimated_protein_g": 20,
            "menu_item_source": "heuristic",
            "menu_item_confidence": 0.7,
            "distance_meters": 500,
            "cuisine_hint": "pizza",
            "decision_today": "MAYBE",
            "fit_for_today": False,
            "health_score": 4.5,
        }
        user_ctx = {"remaining_protein_g": 40, "cut_mode": True, "goal": "fat_loss"}
        out_no_mem = build_ranked_place_profile(base_place, user_ctx)

        # Same place but with strong positive memory
        mem = PersonalMemory(
            worked_before=True,
            personal_memory_label="Worked well before",
            times_chosen=6,
            repeat_success_rate=0.9,
            swap_accept_rate=0.7,
            avg_fullness=4.5,
            avg_craving_score=1.0,
        )
        user_ctx_mem = {
            **user_ctx,
            "personal_memory": mem,
        }
        out_with_mem = build_ranked_place_profile(base_place, user_ctx_mem)
        # Either no change or very small (safeguard zeroes weak core scores).
        self.assertLessEqual(
            out_with_mem["display_rank_score_100"] - out_no_mem["display_rank_score_100"],
            3,
        )


if __name__ == "__main__":
    unittest.main()


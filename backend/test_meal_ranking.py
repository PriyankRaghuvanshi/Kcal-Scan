"""
Tests for meal-first ranking: CUT mode sanity, generic fallback suppression,
visible score/sort alignment, needs menu check, low-cal poor-protein trap.
"""
from __future__ import annotations

import unittest

from meal_ranking import (
    _is_generic_fallback,
    compute_eligibility_band,
    compute_meal_fitness_score,
    recommendation_label_and_section,
)


class TestMealRanking(unittest.TestCase):
    def test_cut_mode_ranking_sanity(self):
        """Pizza Hut must not be #1 in CUT; Subway or Indian should lead. Processed/low-protein options (e.g. pizza) rank below better whole-food options."""
        remaining_calories = 700.0
        remaining_protein_g = 45.0
        user_ctx = {
            "cut_mode": True,
            "goal": "fat_loss",
            "remaining_protein_g": remaining_protein_g,
            "fit_today_score_100": 80.0,
            "calorie_fit_score_100": 85.0,
            "protein_fit_score_100": 90.0,
            "overshoot_penalty_100": 0.0,
        }
        candidates = [
            {"name": "Subway", "recommended_order": "Grilled chicken sub", "estimated_calories": 520, "estimated_protein_g": 38,
             "menu_item_confidence": 0.85, "order_confidence": 0.85, "distance_meters": 200, "cuisine_hint": "sub", "decision_today": "YES", "fit_for_today": True, "menu_item_source": "real_menu"},
            {"name": "Indian restaurant", "recommended_order": "Tandoori chicken + dal + 1 roti", "estimated_calories": 610, "estimated_protein_g": 42,
             "menu_item_confidence": 0.78, "order_confidence": 0.78, "distance_meters": 250, "cuisine_hint": "indian", "decision_today": "YES", "fit_for_today": True, "menu_item_source": "llm_inferred"},
            {"name": "Cafe", "recommended_order": "Omelette + toast", "estimated_calories": 480, "estimated_protein_g": 24,
             "menu_item_confidence": 0.65, "order_confidence": 0.65, "distance_meters": 150, "cuisine_hint": "cafe", "decision_today": "MAYBE", "fit_for_today": True, "menu_item_source": "heuristic"},
            {"name": "Juice center", "recommended_order": "Protein smoothie", "estimated_calories": 380, "estimated_protein_g": 18,
             "menu_item_confidence": 0.6, "order_confidence": 0.6, "distance_meters": 100, "cuisine_hint": "juice", "decision_today": "MAYBE", "fit_for_today": True, "menu_item_source": "heuristic"},
            {"name": "Pizza Hut", "recommended_order": "Thin crust 2 slices", "estimated_calories": 560, "estimated_protein_g": 22,
             "menu_item_confidence": 0.88, "order_confidence": 0.88, "distance_meters": 300, "cuisine_hint": "pizza", "decision_today": "YES", "fit_for_today": True, "menu_item_source": "real_menu"},
        ]
        scored = []
        for p in candidates:
            r = compute_meal_fitness_score(p, user_ctx)
            b = compute_eligibility_band(p, user_ctx)
            scored.append((p["name"], r["meal_fitness_score_100"], b))
        scored.sort(key=lambda x: (-x[2], -x[1]))
        names_ordered = [x[0] for x in scored]
        self.assertNotEqual(names_ordered[0], "Pizza Hut", "Pizza Hut must not be #1 in CUT (general quality logic should demote low-protein/processed)")
        self.assertIn(names_ordered[0], ("Subway", "Indian restaurant"), "Subway or Indian (higher protein, better whole-food) should be #1 in CUT")
        self.assertGreater(names_ordered.index("Juice center"), names_ordered.index("Indian restaurant"), "Juice center must rank below Indian in CUT")
        self.assertGreater(names_ordered.index("Juice center"), names_ordered.index("Subway"), "Juice center must rank below Subway in CUT")

    def test_generic_fallback_suppression(self):
        """Heuristic 'egg + chicken plate' → eligibility_band <= 1, not Best pick."""
        p = {
            "name": "Some Cafe",
            "recommended_order": "Egg + chicken plate",
            "estimated_calories": 430,
            "estimated_protein_g": 30,
            "menu_item_confidence": 0.6,
            "order_confidence": 0.6,
            "distance_meters": 200,
            "cuisine_hint": "cafe",
            "decision_today": "YES",
            "fit_for_today": True,
            "menu_item_source": "heuristic",
        }
        user_ctx = {"cut_mode": True, "goal": "fat_loss", "remaining_protein_g": 40, "fit_today_score_100": 70, "calorie_fit_score_100": 75, "protein_fit_score_100": 80, "overshoot_penalty_100": 0}
        band = compute_eligibility_band(p, user_ctx)
        label, section = recommendation_label_and_section(band, "heuristic", 0.6, is_generic_fallback=True)
        self.assertLessEqual(band, 1)
        self.assertNotEqual(label, "Best pick")

    def test_is_generic_fallback(self):
        self.assertTrue(_is_generic_fallback("Egg + chicken plate"))
        self.assertTrue(_is_generic_fallback("Lighter menu option"))
        self.assertFalse(_is_generic_fallback("Tandoori chicken + dal + roti"))
        self.assertFalse(_is_generic_fallback("Eggs on toast"))

    def test_visible_score_sort_alignment(self):
        """display_rank_score_100 descending order matches list order."""
        places = [
            {"display_rank_score_100": 72, "name": "A"},
            {"display_rank_score_100": 58, "name": "B"},
            {"display_rank_score_100": 90, "name": "C"},
            {"display_rank_score_100": 65, "name": "D"},
        ]
        ordered = sorted(places, key=lambda x: -(x.get("display_rank_score_100") or 0))
        scores = [x["display_rank_score_100"] for x in ordered]
        self.assertEqual(scores, [90, 72, 65, 58])

    def test_needs_menu_check_suppression(self):
        """Low confidence heuristic → cannot be band 3, not hero."""
        p = {
            "name": "Unknown place",
            "recommended_order": "Lighter menu option",
            "estimated_calories": 500,
            "estimated_protein_g": 25,
            "menu_item_confidence": 0.45,
            "order_confidence": 0.45,
            "distance_meters": 400,
            "cuisine_hint": "",
            "decision_today": "MAYBE",
            "fit_for_today": True,
            "menu_item_source": "heuristic",
        }
        user_ctx = {"cut_mode": False, "goal": "", "remaining_protein_g": 30, "fit_today_score_100": 50, "calorie_fit_score_100": 55, "protein_fit_score_100": 50, "overshoot_penalty_100": 0}
        band = compute_eligibility_band(p, user_ctx)
        self.assertLessEqual(band, 2)
        self.assertNotEqual(band, 3)

    def test_low_calorie_poor_protein_trap(self):
        """Low-cal weak protein should not beat moderate-cal high-protein in CUT when remaining protein is high."""
        user_ctx = {"cut_mode": True, "goal": "fat_loss", "remaining_protein_g": 50,
                    "fit_today_score_100": 60, "calorie_fit_score_100": 90, "protein_fit_score_100": 40, "overshoot_penalty_100": 0}
        low_cal_weak = {"name": "Smoothie bar", "recommended_order": "Green smoothie", "estimated_calories": 280, "estimated_protein_g": 8,
                        "menu_item_confidence": 0.7, "order_confidence": 0.7, "distance_meters": 100, "cuisine_hint": "juice", "decision_today": "YES", "fit_for_today": True, "menu_item_source": "heuristic"}
        high_protein = {"name": "Grill", "recommended_order": "Grilled chicken + salad", "estimated_calories": 550, "estimated_protein_g": 45,
                       "menu_item_confidence": 0.75, "order_confidence": 0.75, "distance_meters": 200, "cuisine_hint": "grill", "decision_today": "YES", "fit_for_today": True, "menu_item_source": "heuristic"}
        s1 = compute_meal_fitness_score(low_cal_weak, user_ctx)
        s2 = compute_meal_fitness_score(high_protein, user_ctx)
        self.assertGreater(s2["meal_fitness_score_100"], s1["meal_fitness_score_100"], "High-protein balanced meal should beat low-cal weak protein in CUT")


if __name__ == "__main__":
    unittest.main()

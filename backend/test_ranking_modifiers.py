import unittest

from ranking_modifiers import apply_score_modifiers


class RankingModifiersTests(unittest.TestCase):
    def test_sparse_payload_keeps_modifier_near_neutral(self):
        out = apply_score_modifiers(
            base_score=72.0,
            payload={"name": "Unknown place"},
            context={"modifier_rollout_phase": "phase_1"},
        )
        self.assertAlmostEqual(out["base_score"], 72.0, places=2)
        self.assertAlmostEqual(out["modifier_breakdown"]["personal_response_history_modifier"]["raw"], 0.0, places=2)
        self.assertLessEqual(abs(float(out["modifier_score"])), 3.5)

    def test_upf_penalty_applies_but_is_capped(self):
        out = apply_score_modifiers(
            base_score=80.0,
            payload={
                "recommended_order": "Loaded crispy fried combo with shake",
                "top_menu_item": {
                    "item_name": "Loaded crispy fried combo with shake",
                    "item_score_breakdown": {
                        "processing_penalty": 88,
                        "fried_penalty": 85,
                        "sugar_penalty": 72,
                    },
                },
            },
            context={"modifier_rollout_phase": "phase_1"},
        )
        self.assertLess(float(out["modifier_breakdown"]["upf_penalty"]["raw"]), 0.0)
        self.assertGreaterEqual(float(out["final_score"]), 70.0)

    def test_positive_real_menu_item_gets_small_positive_bonus(self):
        out = apply_score_modifiers(
            base_score=78.0,
            payload={
                "menu_item_source": "real_menu",
                "top_menu_item": {
                    "item_name": "Chicken salad bowl with lentils and greens",
                    "menu_item_source": "real_menu",
                    "menu_item_confidence": 0.9,
                    "order_type": "exact",
                    "estimated_calories": 520,
                    "estimated_protein_g": 40,
                },
            },
            context={"modifier_rollout_phase": "phase_1"},
        )
        self.assertGreater(float(out["modifier_breakdown"]["bioavailability_bonus"]["raw"]), 0.0)
        self.assertGreater(float(out["modifier_breakdown"]["micronutrient_bonus"]["raw"]), 0.0)
        self.assertGreaterEqual(float(out["final_score"]), 78.0)
        self.assertLessEqual(float(out["modifier_score"]), 3.5)


if __name__ == "__main__":
    unittest.main()


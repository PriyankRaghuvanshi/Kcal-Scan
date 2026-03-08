import unittest

from coach_messages import build_place_coach_message


class CoachMessageTests(unittest.TestCase):
    def test_yes_fit_positive_message(self):
        msg = build_place_coach_message(
            place={"decision_today": "YES", "health_score": 8.5},
            top_menu_item={"item_name": "Chicken bowl", "estimated_protein_g": 42},
            today_fit={"decision": "YES", "decision_reason": "Fits today's calories and gives strong protein."},
            context={"goal": "fat_loss", "cut_mode": True},
        )
        self.assertIn("headline", msg)
        self.assertEqual(msg.get("tone"), "encouraging")
        self.assertTrue("fit" in msg["headline"].lower() or "protein" in msg["headline"].lower())

    def test_maybe_fit_caution_message(self):
        msg = build_place_coach_message(
            place={"decision_today": "MAYBE", "health_score": 6.9},
            top_menu_item={"item_name": "Wrap", "estimated_protein_g": 28},
            today_fit={"decision": "MAYBE"},
        )
        self.assertEqual(msg.get("tone"), "caution")
        self.assertTrue("possible" in msg["headline"].lower() or "work" in msg["headline"].lower())

    def test_no_fit_harder_message(self):
        msg = build_place_coach_message(
            place={"decision_today": "NO", "health_score": 4.8},
            top_menu_item={"item_name": "Combo", "estimated_protein_g": 20},
            today_fit={"decision": "NO"},
        )
        self.assertEqual(msg.get("tone"), "warning")
        self.assertIn("hard", msg["headline"].lower())

    def test_high_calorie_saving_message(self):
        msg = build_place_coach_message(
            place={"decision_today": "YES", "health_score": 8.1},
            top_menu_item={"item_name": "Lean bowl", "estimated_protein_g": 36},
            today_fit={"decision": "YES"},
            reality_check={"calories_saved": 360},
        )
        self.assertTrue("save" in msg["headline"].lower() or "swap" in msg["headline"].lower())

    def test_high_remaining_protein_need_message(self):
        msg = build_place_coach_message(
            place={"decision_today": "YES", "health_score": 7.9},
            top_menu_item={"item_name": "Protein bowl", "estimated_protein_g": 38},
            today_fit={"decision": "YES"},
            context={"remaining_protein_g": 60},
        )
        self.assertTrue(
            "protein" in msg["headline"].lower() or "protein" in msg.get("supporting_text", "").lower()
        )

    def test_sparse_data_fallback(self):
        msg = build_place_coach_message(place={"name": "Generic Place"})
        self.assertIsInstance(msg.get("headline"), str)
        self.assertTrue(msg["headline"].strip())
        self.assertIsInstance(msg.get("supporting_text"), str)
        self.assertIn(msg.get("tone"), {"encouraging", "caution", "warning"})
        self.assertGreaterEqual(float(msg.get("confidence", 0.0)), 0.45)
        self.assertIn(msg.get("phrasing_method"), {"deterministic", "llm"})
        self.assertEqual(msg.get("phrasing_version"), "v1")


if __name__ == "__main__":
    unittest.main()

import unittest

import main as main_mod


class AudioCoachTurnTests(unittest.TestCase):
    def test_audio_reply_builder_contains_question(self):
        out = main_mod._audio_turn_reply_text(
            user_text="I am very hungry and craving snacks",
            tone="supportive",
            protein_gap=42.0,
            fiber_gap=9.0,
            kcal_delta=120.0,
        )
        self.assertTrue(str(out.get("coach_reply") or "").strip())
        self.assertTrue(str(out.get("next_question") or "").strip())

    def test_audio_history_normalize_filters_roles(self):
        rows = main_mod._audio_history_normalize(
            [
                {"role": "user", "text": "hello"},
                {"role": "coach", "text": "hi"},
                {"role": "system", "text": "skip"},
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["role"], "user")
        self.assertEqual(rows[1]["role"], "coach")


if __name__ == "__main__":
    unittest.main()

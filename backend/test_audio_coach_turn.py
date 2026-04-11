import unittest

import main as main_mod


class AudioCoachTurnTests(unittest.TestCase):
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

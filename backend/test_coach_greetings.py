import datetime as dt
import unittest
from unittest.mock import patch

import main as main_mod


class CoachGreetingsTests(unittest.TestCase):
    def test_daypart_greetings(self):
        self.assertEqual(main_mod._coach_greeting_for_daypart(8), "Good morning")
        self.assertEqual(main_mod._coach_greeting_for_daypart(13), "Good afternoon")
        self.assertEqual(main_mod._coach_greeting_for_daypart(19), "Good evening")
        self.assertEqual(main_mod._coach_greeting_for_daypart(23), "Good night")

    def test_diwali_greeting_for_known_date(self):
        g = main_mod._festival_greeting_for_date(dt.date(2026, 11, 8), region="IN")
        self.assertIn("Diwali", g)

    def test_attach_temporal_greeting_prefixes_summary(self):
        with patch("main._event_local_context", return_value={
            "created_at_utc": "2026-03-27T00:00:00+00:00",
            "event_day_local": "2026-03-27",
            "event_hour_local": 9,
            "event_time_local": "2026-03-27T09:00:00+11:00",
            "tz": "Australia/Sydney",
            "tz_offset_min": 660,
        }):
            out = main_mod._attach_temporal_coach_greeting(
                {
                    "coach_summary": "Protein is your main lever today.",
                    "one_sentence_summary": "Protein gap is the top bottleneck.",
                },
                tz="Australia/Sydney",
                tz_offset_min=660,
                region="AU",
            )
        self.assertTrue(str(out.get("coach_summary") or "").lower().startswith("good morning"))
        self.assertTrue(str(out.get("one_sentence_summary") or "").lower().startswith("good morning"))
        self.assertEqual(out.get("opening_daypart"), "morning")
        self.assertEqual(out.get("opening_timezone"), "Australia/Sydney")


if __name__ == "__main__":
    unittest.main()

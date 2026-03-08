import unittest

from weekly_coach import build_weekly_coach_payload


class WeeklyCoachTests(unittest.TestCase):
    def test_strong_week_summary(self):
        rows = [
            {
                "date": "2026-03-02",
                "consumed_calories": 1900,
                "target_calories": 2000,
                "consumed_protein_g": 148,
                "target_protein_g": 150,
                "lunch_calories": 520,
                "dinner_calories": 680,
                "lunch_protein_g": 42,
                "dinner_protein_g": 38,
            },
            {
                "date": "2026-03-03",
                "consumed_calories": 1980,
                "target_calories": 2000,
                "consumed_protein_g": 152,
                "target_protein_g": 150,
                "lunch_calories": 540,
                "dinner_calories": 690,
                "lunch_protein_g": 44,
                "dinner_protein_g": 36,
            },
            {
                "date": "2026-03-04",
                "consumed_calories": 2040,
                "target_calories": 2000,
                "consumed_protein_g": 145,
                "target_protein_g": 150,
                "lunch_calories": 530,
                "dinner_calories": 700,
                "lunch_protein_g": 40,
                "dinner_protein_g": 35,
            },
            {
                "date": "2026-03-05",
                "consumed_calories": 1880,
                "target_calories": 2000,
                "consumed_protein_g": 150,
                "target_protein_g": 150,
                "lunch_calories": 510,
                "dinner_calories": 640,
                "lunch_protein_g": 41,
                "dinner_protein_g": 34,
            },
        ]
        out = build_weekly_coach_payload(days=rows, choices=[])
        self.assertTrue(str(out["headline"]).strip())
        self.assertEqual(out["week_summary"]["days_tracked"], 4)
        self.assertGreaterEqual(out["week_summary"]["days_on_track"], 3)
        self.assertIsInstance(out.get("habit_insights"), list)
        self.assertIsInstance(out.get("next_week_focus"), dict)

    def test_weak_protein_week(self):
        rows = [
            {
                "date": "2026-03-02",
                "consumed_calories": 1950,
                "target_calories": 2000,
                "consumed_protein_g": 85,
                "target_protein_g": 150,
            },
            {
                "date": "2026-03-03",
                "consumed_calories": 2020,
                "target_calories": 2000,
                "consumed_protein_g": 90,
                "target_protein_g": 150,
            },
            {
                "date": "2026-03-04",
                "consumed_calories": 1985,
                "target_calories": 2000,
                "consumed_protein_g": 95,
                "target_protein_g": 150,
            },
            {
                "date": "2026-03-05",
                "consumed_calories": 2100,
                "target_calories": 2000,
                "consumed_protein_g": 88,
                "target_protein_g": 150,
            },
        ]
        out = build_weekly_coach_payload(days=rows, choices=[], goal="fat_loss", cut_mode=True)
        self.assertGreaterEqual(out["week_summary"]["days_under_protein"], 3)
        insight_text = " ".join([str(x.get("text") or "") for x in out.get("habit_insights") or []]).lower()
        self.assertIn("protein", insight_text)
        self.assertIn("protein", str(out["next_week_focus"].get("headline") or "").lower())

    def test_sparse_history_fallback(self):
        out = build_weekly_coach_payload(days=[{"date": "2026-03-02", "consumed_calories": 650}], choices=[])
        self.assertEqual(out["week_summary"]["days_tracked"], 1)
        self.assertIn("learning", str(out["headline"]).lower())
        self.assertTrue(len(out["habit_insights"]) >= 1)

    def test_best_choice_extraction(self):
        rows = [
            {
                "date": "2026-03-02",
                "consumed_calories": 1900,
                "target_calories": 2000,
                "consumed_protein_g": 140,
                "target_protein_g": 150,
            },
            {
                "date": "2026-03-03",
                "consumed_calories": 2050,
                "target_calories": 2000,
                "consumed_protein_g": 132,
                "target_protein_g": 150,
            },
            {
                "date": "2026-03-04",
                "consumed_calories": 1940,
                "target_calories": 2000,
                "consumed_protein_g": 138,
                "target_protein_g": 150,
            },
        ]
        choices = [
            {
                "place_name": "Nando's",
                "recommended_order": "Quarter chicken + salad",
                "fit_for_today": True,
                "health_score": 88,
            },
            {
                "place_name": "Nando's",
                "recommended_order": "Quarter chicken + salad",
                "fit_for_today": True,
                "health_score": 86,
            },
            {
                "place_name": "Sushi Train",
                "recommended_order": "Salmon sashimi + rice",
                "fit_for_today": True,
                "health_score": 81,
            },
        ]

        out = build_weekly_coach_payload(days=rows, choices=choices)
        self.assertIsInstance(out.get("best_choices_this_week"), list)
        self.assertGreaterEqual(len(out["best_choices_this_week"]), 1)
        self.assertEqual(out["best_choices_this_week"][0]["place_name"], "Nando's")

    def test_next_week_focus_generation(self):
        rows = [
            {
                "date": "2026-03-02",
                "consumed_calories": 2350,
                "target_calories": 2000,
                "consumed_protein_g": 120,
                "target_protein_g": 150,
                "lunch_calories": 620,
                "dinner_calories": 1050,
            },
            {
                "date": "2026-03-03",
                "consumed_calories": 2280,
                "target_calories": 2000,
                "consumed_protein_g": 118,
                "target_protein_g": 150,
                "lunch_calories": 610,
                "dinner_calories": 980,
            },
            {
                "date": "2026-03-04",
                "consumed_calories": 2210,
                "target_calories": 2000,
                "consumed_protein_g": 122,
                "target_protein_g": 150,
                "lunch_calories": 600,
                "dinner_calories": 960,
            },
            {
                "date": "2026-03-05",
                "consumed_calories": 2180,
                "target_calories": 2000,
                "consumed_protein_g": 125,
                "target_protein_g": 150,
                "lunch_calories": 590,
                "dinner_calories": 940,
            },
        ]
        out = build_weekly_coach_payload(days=rows, choices=[])
        focus_headline = str(out["next_week_focus"].get("headline") or "").lower()
        self.assertTrue("dinner" in focus_headline or "protein" in focus_headline)

    def test_weekday_protein_habit_signal(self):
        rows = [
            {
                "date": "2026-03-02",
                "consumed_calories": 1920,
                "target_calories": 2000,
                "consumed_protein_g": 82,
                "target_protein_g": 150,
            },
            {
                "date": "2026-03-03",
                "consumed_calories": 1980,
                "target_calories": 2000,
                "consumed_protein_g": 90,
                "target_protein_g": 150,
            },
            {
                "date": "2026-03-04",
                "consumed_calories": 2010,
                "target_calories": 2000,
                "consumed_protein_g": 88,
                "target_protein_g": 150,
            },
            {
                "date": "2026-03-05",
                "consumed_calories": 1890,
                "target_calories": 2000,
                "consumed_protein_g": 94,
                "target_protein_g": 150,
            },
            {
                "date": "2026-03-07",
                "consumed_calories": 2050,
                "target_calories": 2000,
                "consumed_protein_g": 152,
                "target_protein_g": 150,
            },
        ]
        out = build_weekly_coach_payload(days=rows, choices=[], goal="fat_loss", cut_mode=True)
        insight_text = " ".join([str(x.get("title") or "") + " " + str(x.get("text") or "") for x in out.get("habit_insights") or []]).lower()
        self.assertIn("weekday", insight_text)


if __name__ == "__main__":
    unittest.main()

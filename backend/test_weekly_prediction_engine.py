import unittest

try:
    import main_1702 as engine
    _IMPORT_ERROR = None
except Exception as e:  # pragma: no cover - environment bootstrap fallback
    engine = None
    _IMPORT_ERROR = e


def _row(day, protein_hit, fiber_hit, gl, upf, late_pct, kcal_delta_pct, leucine_hit=2, leucine_target=3, biggest_meal="dinner", kcal_goal=2200, kcal_consumed=2000):
    return {
        "day": day,
        "protein_hit_pct": protein_hit,
        "fiber_hit_pct": fiber_hit,
        "avg_glycemic_load": gl,
        "ultra_processed_avg": upf,
        "late_calories_pct": late_pct,
        "kcal_delta_pct": kcal_delta_pct,
        "leucine_triggers_hit": leucine_hit,
        "leucine_triggers_target": leucine_target,
        "biggest_meal": biggest_meal,
        "kcal_goal": kcal_goal,
        "kcal_consumed": kcal_consumed,
    }


@unittest.skipIf(engine is None, f"main_1702 import unavailable: {_IMPORT_ERROR}")
class WeeklyPredictionEngineTests(unittest.TestCase):
    def test_prediction_payload_shape(self):
        rows = [
            _row("2026-02-16", 78, 42, 31, 7.0, 58, -10, leucine_hit=1, kcal_consumed=1950),
            _row("2026-02-17", 82, 48, 29, 6.8, 55, -8, leucine_hit=1, kcal_consumed=1980),
            _row("2026-02-18", 75, 40, 34, 7.5, 62, -12, leucine_hit=1, kcal_consumed=1920),
            _row("2026-02-19", 88, 52, 27, 6.2, 49, -6, leucine_hit=2, kcal_consumed=2010),
        ]
        payload = engine.build_weekly_prediction_payload("u1", "2026-02-16", rows)

        for k in (
            "protein_avg",
            "protein_consistency",
            "fiber_avg",
            "fiber_consistency",
            "timing_balance_avg",
            "timing_volatility",
            "upf_avg",
            "upf_volatility",
            "glycemic_avg",
            "glycemic_volatility",
            "readiness_score",
            "readiness_trend",
            "projection_7d_score",
            "fat_loss_velocity_score",
            "fat_loss_probability_7d",
            "projection_confidence_band",
            "days_with_data_7d",
            "scans_7d",
            "weight_change_projection_7d",
            "hunger_volatility_projection",
            "muscle_retention_risk",
            "payload_hash",
        ):
            self.assertIn(k, payload)

        self.assertGreaterEqual(payload["protein_consistency"], 0.0)
        self.assertLessEqual(payload["protein_consistency"], 100.0)
        self.assertGreaterEqual(payload["fat_loss_probability_7d"], 0.0)
        self.assertLessEqual(payload["fat_loss_probability_7d"], 1.0)
        self.assertGreaterEqual(payload["projection_7d_score"], 0.0)
        self.assertLessEqual(payload["projection_7d_score"], 100.0)

    def test_better_week_increases_projection_score(self):
        poor_rows = [
            _row("2026-02-16", 60, 30, 36, 8.5, 70, 18, leucine_hit=0, kcal_consumed=2600),
            _row("2026-02-17", 72, 35, 33, 8.1, 65, 14, leucine_hit=1, kcal_consumed=2500),
            _row("2026-02-18", 55, 28, 38, 8.8, 74, 20, leucine_hit=0, kcal_consumed=2700),
            _row("2026-02-19", 68, 32, 35, 8.0, 67, 16, leucine_hit=1, kcal_consumed=2550),
        ]
        good_rows = [
            _row("2026-02-16", 102, 96, 16, 2.4, 30, -8, leucine_hit=3, leucine_target=3, biggest_meal="lunch", kcal_consumed=2020),
            _row("2026-02-17", 98, 92, 15, 2.2, 28, -6, leucine_hit=3, leucine_target=3, biggest_meal="lunch", kcal_consumed=2050),
            _row("2026-02-18", 104, 100, 14, 2.0, 27, -7, leucine_hit=3, leucine_target=3, biggest_meal="lunch", kcal_consumed=2010),
            _row("2026-02-19", 101, 95, 13, 2.1, 29, -5, leucine_hit=3, leucine_target=3, biggest_meal="lunch", kcal_consumed=2060),
        ]

        poor = engine.build_weekly_prediction_payload("u1", "2026-02-16", poor_rows)
        good = engine.build_weekly_prediction_payload("u1", "2026-02-16", good_rows)

        self.assertGreater(good["projection_7d_score"], poor["projection_7d_score"])
        self.assertGreater(good["fat_loss_velocity_score"], poor["fat_loss_velocity_score"])
        self.assertLess(good["muscle_retention_risk"]["score"], poor["muscle_retention_risk"]["score"])


if __name__ == "__main__":
    unittest.main()


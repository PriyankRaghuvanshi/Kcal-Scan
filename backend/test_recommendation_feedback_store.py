import os
import tempfile
import unittest

from menu_item_scoring import rank_menu_items_for_place
from recommendation_feedback_store import (
    get_feedback_summary,
    get_place_item_feedback_signal,
    log_recommendation_feedback_event,
)


class RecommendationFeedbackStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._old_feedback_path = os.environ.get("RECOMMENDATION_FEEDBACK_STORE_PATH")
        self._old_menu_path = os.environ.get("MENU_INTELLIGENCE_STORE_PATH")
        os.environ["RECOMMENDATION_FEEDBACK_STORE_PATH"] = os.path.join(self._tmp_dir.name, "feedback_store.json")
        os.environ["MENU_INTELLIGENCE_STORE_PATH"] = os.path.join(self._tmp_dir.name, "menu_store.json")

    def tearDown(self):
        if self._old_feedback_path is None:
            os.environ.pop("RECOMMENDATION_FEEDBACK_STORE_PATH", None)
        else:
            os.environ["RECOMMENDATION_FEEDBACK_STORE_PATH"] = self._old_feedback_path

        if self._old_menu_path is None:
            os.environ.pop("MENU_INTELLIGENCE_STORE_PATH", None)
        else:
            os.environ["MENU_INTELLIGENCE_STORE_PATH"] = self._old_menu_path

        self._tmp_dir.cleanup()

    def _log_events(self, place_id: str, item: str, viewed: int, selected: int, scanned: int, followed: int):
        for _ in range(viewed):
            log_recommendation_feedback_event(event="recommendation_viewed", place_id=place_id, item=item)
        for _ in range(selected):
            log_recommendation_feedback_event(event="recommendation_selected", place_id=place_id, item=item)
        for _ in range(scanned):
            log_recommendation_feedback_event(event="meal_scanned", place_id=place_id, item=item)
        for _ in range(followed):
            log_recommendation_feedback_event(event="recommendation_followed", place_id=place_id, item=item)

    def test_event_logging_and_summary_by_place_id(self):
        self._log_events("abc123", "Chicken bowl", viewed=8, selected=4, scanned=3, followed=2)

        summary = get_feedback_summary(place_id="abc123", item="Chicken bowl")
        self.assertEqual(summary["summary_count"], 1)
        row = summary["rows"][0]

        self.assertEqual(row["place_id"], "abc123")
        self.assertEqual(row["item"], "Chicken bowl")
        self.assertEqual(row["counts"]["recommendation_viewed"], 8)
        self.assertEqual(row["counts"]["recommendation_selected"], 4)
        self.assertEqual(row["counts"]["meal_scanned"], 3)
        self.assertEqual(row["counts"]["recommendation_followed"], 2)

    def test_feedback_signal_returns_positive_adjustment_for_successful_item(self):
        self._log_events("fit-1", "Chicken Bowl", viewed=12, selected=6, scanned=5, followed=4)

        signal = get_place_item_feedback_signal("fit-1", "Chicken Bowl")
        self.assertGreater(signal["events_count"], 0)
        self.assertGreater(float(signal["follow_rate"]), 0.5)
        self.assertGreater(float(signal["score_adjustment"]), 0.0)

    def test_extended_funnel_events_are_accepted(self):
        ok1 = log_recommendation_feedback_event(event="recommendation_shown", place_id="extra-1", item="Chicken Bowl")
        ok2 = log_recommendation_feedback_event(event="recommendation_clicked", place_id="extra-1", item="Chicken Bowl")
        ok3 = log_recommendation_feedback_event(event="place_selected", place_id="extra-1", item="Chicken Bowl")
        ok4 = log_recommendation_feedback_event(event="share_card_opened", place_id="extra-1", item="Chicken Bowl")
        ok5 = log_recommendation_feedback_event(event="share_action_triggered", place_id="extra-1", item="Chicken Bowl")

        self.assertIsInstance(ok1, dict)
        self.assertIsInstance(ok2, dict)
        self.assertIsInstance(ok3, dict)
        self.assertIsInstance(ok4, dict)
        self.assertIsInstance(ok5, dict)

        summary = get_feedback_summary(place_id="extra-1", item="Chicken Bowl")
        self.assertEqual(summary["summary_count"], 1)
        row = summary["rows"][0]
        self.assertEqual(row["counts"]["recommendation_shown"], 1)
        self.assertEqual(row["counts"]["recommendation_clicked"], 1)
        self.assertEqual(row["counts"]["place_selected"], 1)
        self.assertEqual(row["counts"]["share_card_opened"], 1)
        self.assertEqual(row["counts"]["share_action_triggered"], 1)

    def test_scoring_uses_feedback_signal(self):
        place = {"name": "Feedback Grill", "place_id": "score-1", "types": ["restaurant", "grill"]}
        menu_items = [
            {"item_name": "Test Bowl Alpha", "estimated_calories": 520, "estimated_protein_g": 34, "estimated_satiety": "medium"},
            {"item_name": "Test Bowl Beta", "estimated_calories": 520, "estimated_protein_g": 34, "estimated_satiety": "medium"},
        ]

        self._log_events("score-1", "Test Bowl Alpha", viewed=12, selected=7, scanned=5, followed=5)
        self._log_events("score-1", "Test Bowl Beta", viewed=12, selected=1, scanned=0, followed=0)

        ranked = rank_menu_items_for_place(place, menu_items)
        self.assertEqual(ranked[0]["item_name"], "Test Bowl Alpha")
        self.assertGreater(
            float(ranked[0].get("feedback_score_adjustment", 0.0)),
            float(ranked[1].get("feedback_score_adjustment", 0.0)),
        )


if __name__ == "__main__":
    unittest.main()

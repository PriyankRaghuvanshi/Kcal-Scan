from __future__ import annotations

import os
import tempfile
import unittest

from meal_feedback_store import upsert_meal_feedback_event
from meal_decision_event_store import log_meal_decision_event
from personal_response_summary import get_personal_meal_memory


class TestMealFeedbackStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MEAL_FEEDBACK_STORE_PATH"] = os.path.join(self.tmp.name, "meal_feedback_store.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_feedback_accepts_partial(self):
        saved = upsert_meal_feedback_event(
            {"user_id": "u1", "place_id": "p1", "selected_item_name": "Eggs on toast"}
        )
        self.assertTrue(saved.get("feedback_id"))
        self.assertEqual(saved.get("user_id"), "u1")
        self.assertEqual(saved.get("place_id"), "p1")
        self.assertEqual(saved.get("selected_item_name"), "Eggs on toast")

    def test_feedback_upsert_updates_existing(self):
        first = upsert_meal_feedback_event(
            {"user_id": "u1", "place_id": "p1", "selected_item_name": "Eggs on toast"}
        )
        fid = first["feedback_id"]
        second = upsert_meal_feedback_event(
            {"user_id": "u1", "feedback_id": fid, "fullness_score": 4, "craving_score": 1, "repeat_intent": True}
        )
        self.assertEqual(second.get("feedback_id"), fid)
        self.assertEqual(second.get("fullness_score"), 4)
        self.assertEqual(second.get("craving_score"), 1)
        self.assertTrue(second.get("repeat_intent"))


class TestMealDecisionEventStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MEAL_DECISION_EVENT_STORE_PATH"] = os.path.join(self.tmp.name, "meal_decision_event_store.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_decision_event_validates_event_type(self):
        with self.assertRaises(ValueError):
            log_meal_decision_event({"user_id": "u1", "event_type": "invalid", "place_id": "p1"})
        ok = log_meal_decision_event({"user_id": "u1", "event_type": "swap_accepted", "place_id": "p1"})
        self.assertEqual(ok.get("event_type"), "swap_accepted")


class TestPersonalMemoryLabels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MEAL_FEEDBACK_STORE_PATH"] = os.path.join(self.tmp.name, "meal_feedback_store.json")
        os.environ["MEAL_DECISION_EVENT_STORE_PATH"] = os.path.join(self.tmp.name, "meal_decision_event_store.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_not_enough_data_label(self):
        upsert_meal_feedback_event({"user_id": "u1", "place_id": "p1", "place_name": "Darbar", "selected_item_name": "Tandoori chicken + dal", "fullness_score": 4})
        mem = get_personal_meal_memory(user_id="u1", place_id="p1", place_name="Darbar", item_name="Tandoori chicken + dal")
        self.assertEqual(mem.personal_memory_label, "Not enough data yet")
        self.assertFalse(mem.worked_before)

    def test_worked_well_before_label(self):
        for _ in range(4):
            upsert_meal_feedback_event(
                {
                    "user_id": "u1",
                    "place_id": "p1",
                    "place_name": "Darbar Indian",
                    "selected_item_name": "Tandoori chicken + dal",
                    "fullness_score": 4,
                    "craving_score": 1,
                    "repeat_intent": True,
                    "swap_accepted": True,
                }
            )
        mem = get_personal_meal_memory(user_id="u1", place_id="p1", place_name="Darbar Indian", item_name="Tandoori chicken + dal")
        self.assertTrue(mem.worked_before)
        self.assertIn(mem.personal_memory_label, {"Worked well before", "Usually keeps you fuller", "You often repeat this"})
        self.assertGreaterEqual(mem.times_chosen, 4)

    def test_cravings_label(self):
        for _ in range(3):
            upsert_meal_feedback_event(
                {
                    "user_id": "u1",
                    "place_id": "p2",
                    "place_name": "Pizza Hut",
                    "selected_item_name": "Pizza",
                    "fullness_score": 2,
                    "craving_score": 5,
                    "repeat_intent": False,
                }
            )
        mem = get_personal_meal_memory(user_id="u1", place_id="p2", place_name="Pizza Hut", item_name="Pizza")
        self.assertEqual(mem.personal_memory_label, "Often followed by cravings")

    def test_prefetched_event_lists_skip_store_reads(self):
        feedback = [
            {
                "user_id": "u1",
                "place_id": "p3",
                "place_name": "Subway",
                "selected_item_name": "Chicken sub",
                "fullness_score": 4,
                "craving_score": 1,
                "repeat_intent": True,
                "swap_accepted": True,
            }
            for _ in range(3)
        ]
        decision = [
            {"user_id": "u1", "place_id": "p3", "event_type": "swap_viewed"},
            {"user_id": "u1", "place_id": "p3", "event_type": "swap_accepted"},
        ]
        mem = get_personal_meal_memory(
            user_id="u1",
            place_id="p3",
            place_name="Subway",
            item_name="Chicken sub",
            _feedback_events=feedback,
            _decision_events=decision,
        )
        self.assertTrue(mem.worked_before)
        self.assertEqual(mem.times_chosen, 3)
        self.assertGreater(mem.swap_accept_rate, 0.0)


class TestApiEnrichment(unittest.TestCase):
    def test_audit_enrichment_when_user_id_provided(self):
        try:
            from fastapi.testclient import TestClient
            from main import app
        except Exception:
            self.skipTest("FastAPI TestClient or main.app not available")

        # Use temp feedback store for this test
        tmp = tempfile.TemporaryDirectory()
        os.environ["MEAL_FEEDBACK_STORE_PATH"] = os.path.join(tmp.name, "meal_feedback_store.json")
        os.environ["MEAL_DECISION_EVENT_STORE_PATH"] = os.path.join(tmp.name, "meal_decision_event_store.json")
        upsert_meal_feedback_event(
            {"user_id": "u1", "place_id": "pid", "place_name": "Darbar", "selected_item_name": "Tandoori chicken + dal", "fullness_score": 4, "craving_score": 1, "repeat_intent": True}
        )

        client = TestClient(app)
        # The endpoint may return zero results if Google Places key unavailable, but should not error.
        r = client.get("/places/healthy/audit", params={"lat": -33.8, "lng": 150.97, "user_id": "u1", "limit": 3})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        if body.get("results"):
            row = body["results"][0]
            # Optional fields should exist when enrichment succeeds
            self.assertIn("personal_memory_label", row)
            self.assertIn("times_chosen", row)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

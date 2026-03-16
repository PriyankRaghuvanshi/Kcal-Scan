"""
Unit tests for yieldpilot_case_workflow: case CRUD, from-recommendation, comments, status, memo, user isolation, filters.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Ensure backend is on path when run as pytest or python -m pytest from repo root or backend
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_BACKEND))

from yieldpilot_case_workflow import (
    add_comment,
    build_memo_payload,
    create_case,
    create_case_from_recommendation,
    delete_case,
    get_case,
    list_cases,
    list_comments,
    list_status_history,
    memo_as_csv,
    memo_as_json,
    memo_as_txt,
    set_status,
    update_case,
    init_schema,
    CASE_STATUSES,
)


class _TestCaseWorkflow(unittest.TestCase):
    """Use a temporary SQLite DB for each test."""

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="yp_case_test_")
        self._db = Path(self._dir) / "cases.sqlite"
        os.environ["YIELDPILOT_CASE_DB_PATH"] = str(self._db)
        init_schema()

    def tearDown(self):
        os.environ.pop("YIELDPILOT_CASE_DB_PATH", None)

    def test_create_case(self):
        case = create_case("user1", "AAPL", title="Test case", scenario_type="covered_call")
        self.assertIsNotNone(case)
        self.assertIn("id", case)
        self.assertEqual(case["user_id"], "user1")
        self.assertEqual(case["symbol"], "AAPL")
        self.assertEqual(case["title"], "Test case")
        self.assertEqual(case["scenario_type"], "covered_call")
        self.assertEqual(case["status"], "draft")

    def test_create_case_from_recommendation(self):
        rec = {
            "symbol": "SPY",
            "contract_symbol": "SPY250117C00450000",
            "scenario_type": "covered_call",
            "model_score": 78.5,
            "capital_required": 45000,
            "expected_monthly_income": 320,
        }
        case = create_case_from_recommendation("user1", "profile_1", rec, title="SPY CC")
        self.assertIsNotNone(case)
        self.assertEqual(case["symbol"], "SPY")
        self.assertEqual(case["scenario_type"], "covered_call")
        self.assertEqual(case["model_score"], 78.5)
        self.assertEqual(case["capital_required"], 45000)
        self.assertIsNotNone(case.get("recommendation_snapshot_json"))

    def test_list_cases_user_scoped(self):
        create_case("user1", "AAPL", title="A")
        create_case("user2", "AAPL", title="B")
        one = list_cases("user1")
        two = list_cases("user2")
        self.assertEqual(len(one), 1)
        self.assertEqual(len(two), 1)
        self.assertEqual(one[0]["title"], "A")
        self.assertEqual(two[0]["title"], "B")

    def test_get_case_user_isolation(self):
        case = create_case("user1", "MSFT", title="Only user1")
        cid = case["id"]
        self.assertIsNotNone(get_case("user1", cid))
        self.assertIsNone(get_case("user2", cid))

    def test_update_case(self):
        case = create_case("user1", "GOOG", title="Original")
        updated = update_case("user1", case["id"], title="Updated", rationale="Because")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["title"], "Updated")
        self.assertEqual(updated["rationale"], "Because")

    def test_add_and_list_comments(self):
        case = create_case("user1", "QQQ", title="With comments")
        add_comment("user1", case["id"], "First comment")
        add_comment("user1", case["id"], "Second comment")
        comments = list_comments("user1", case["id"])
        self.assertEqual(len(comments), 2)
        self.assertIn("First comment", [c["body"] for c in comments])

    def test_status_transitions(self):
        case = create_case("user1", "AAPL", title="Flow", status="draft")
        cid = case["id"]
        updated = set_status("user1", cid, "under_review", note="Sent for review")
        self.assertEqual(updated["status"], "under_review")
        updated = set_status("user1", cid, "approved", note="OK")
        self.assertEqual(updated["status"], "approved")
        history = list_status_history("user1", cid)
        self.assertGreaterEqual(len(history), 3)  # initial + under_review + approved

    def test_memo_export(self):
        case = create_case(
            "user1", "SPY",
            title="Memo case",
            rationale="Test rationale",
            model_score=80,
            capital_required=10000,
        )
        add_comment("user1", case["id"], "A comment")
        payload = build_memo_payload("user1", case["id"])
        self.assertIsNotNone(payload)
        self.assertEqual(payload["case_title"], "Memo case")
        self.assertEqual(payload["symbol"], "SPY")
        self.assertEqual(payload["rationale"], "Test rationale")
        self.assertEqual(payload["current_status"], "draft")
        self.assertEqual(len(payload["comments_summary"]), 1)
        js = memo_as_json("user1", case["id"])
        self.assertIn("Memo case", js)
        csv_out = memo_as_csv("user1", case["id"])
        self.assertIn("case_title", csv_out)
        txt_out = memo_as_txt("user1", case["id"])
        self.assertIn("Memo case", txt_out)

    def test_memo_not_found(self):
        self.assertIsNone(build_memo_payload("user1", 99999))
        self.assertIsNone(memo_as_json("user1", 99999))

    def test_list_filter_symbol(self):
        create_case("user1", "AAPL", title="A")
        create_case("user1", "MSFT", title="B")
        aapl = list_cases("user1", symbol="AAPL")
        self.assertEqual(len(aapl), 1)
        self.assertEqual(aapl[0]["symbol"], "AAPL")

    def test_list_filter_status(self):
        create_case("user1", "A", title="A", status="draft")
        create_case("user1", "B", title="B", status="approved")
        drafts = list_cases("user1", status="draft")
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["status"], "draft")

    def test_delete_case(self):
        case = create_case("user1", "DEL", title="To delete")
        cid = case["id"]
        self.assertTrue(delete_case("user1", cid))
        self.assertIsNone(get_case("user1", cid))

    def test_delete_other_user_case_returns_false(self):
        case = create_case("user1", "X", title="User1 case")
        self.assertFalse(delete_case("user2", case["id"]))
        self.assertIsNotNone(get_case("user1", case["id"]))

    def test_empty_list(self):
        cases = list_cases("new_user_with_no_cases")
        self.assertEqual(cases, [])


if __name__ == "__main__":
    unittest.main()

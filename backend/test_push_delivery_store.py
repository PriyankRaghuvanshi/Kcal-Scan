"""Tests for push delivery store."""
from __future__ import annotations

import os
import tempfile
import unittest

from push_delivery_store import (
    create_delivery_record,
    update_delivery_status,
    list_pending_receipt_ids,
    get_delivery_by_ticket_id,
    was_recently_sent,
)


class TestPushDeliveryStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PUSH_DELIVERY_STORE_PATH"] = os.path.join(
            self.tmp.name, "push_delivery_store.json"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_delivery_record(self):
        rec = create_delivery_record(
            user_id="u1",
            expo_push_token="ExponentPushToken[abc]",
            alert_id="protein_rescue::p1::Chicken",
            alert_type="protein_rescue",
            place_id="p1",
            place_name="Chipotle",
            best_item_name="Chicken Bowl",
            title="T",
            body="B",
            dry_run=False,
        )
        self.assertIn("delivery_id", rec)
        self.assertEqual(rec["user_id"], "u1")
        self.assertEqual(rec["status"], "queued")

    def test_create_dry_run_record(self):
        rec = create_delivery_record(
            user_id="u1",
            expo_push_token="ExponentPushToken[abc]",
            alert_id="a1",
            alert_type="protein_rescue",
            place_id="p1",
            place_name="P",
            best_item_name="B",
            title="T",
            body="B",
            dry_run=True,
        )
        self.assertEqual(rec["dry_run"], True)
        self.assertEqual(rec["status"], "dry_run")

    def test_update_delivery_status(self):
        rec = create_delivery_record(
            user_id="u1",
            expo_push_token="ExponentPushToken[abc]",
            alert_id="a1",
            alert_type="p",
            place_id="p1",
            place_name="P",
            best_item_name="B",
            title="T",
            body="B",
        )
        updated = update_delivery_status(
            rec["delivery_id"], status="sent", expo_ticket_id="tid-123"
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "sent")
        self.assertEqual(updated["expo_ticket_id"], "tid-123")

    def test_get_delivery_by_ticket_id(self):
        rec = create_delivery_record(
            user_id="u1",
            expo_push_token="ExponentPushToken[abc]",
            alert_id="a1",
            alert_type="p",
            place_id="p1",
            place_name="P",
            best_item_name="B",
            title="T",
            body="B",
        )
        update_delivery_status(rec["delivery_id"], status="sent", expo_ticket_id="tid-xyz")
        found = get_delivery_by_ticket_id("tid-xyz")
        self.assertIsNotNone(found)
        self.assertEqual(found["user_id"], "u1")
        self.assertEqual(found["expo_push_token"], "ExponentPushToken[abc]")

    def test_list_pending_receipt_ids(self):
        rec = create_delivery_record(
            user_id="u1",
            expo_push_token="ExponentPushToken[abc]",
            alert_id="a1",
            alert_type="p",
            place_id="p1",
            place_name="P",
            best_item_name="B",
            title="T",
            body="B",
        )
        update_delivery_status(rec["delivery_id"], status="sent", expo_ticket_id="pending-tid")
        pending = list_pending_receipt_ids()
        self.assertIn("pending-tid", pending)

    def test_was_recently_sent_initially_false(self):
        self.assertFalse(
            was_recently_sent("u1", "ExponentPushToken[x]", "a1")
        )

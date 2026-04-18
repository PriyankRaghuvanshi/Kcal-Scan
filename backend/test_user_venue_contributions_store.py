from __future__ import annotations

import unittest
from unittest.mock import patch

from user_venue_contributions import create_contribution


class TestUserVenueContributionsStore(unittest.TestCase):
    def test_create_contribution_sends_payload_as_json_object_to_supabase(self):
        captured = {}

        def _fake_insert(record):
            captured.update(record)
            return dict(record)

        with patch("user_venue_contributions._sb_available", return_value=True), patch(
            "user_venue_contributions._sb_insert", side_effect=_fake_insert
        ):
            row = create_contribution(
                place_name="Darbar",
                area_key="parramatta",
                contribution_type="better_order_suggestion",
                payload={"suggested_order": "Paneer tikka + dal"},
            )

        self.assertEqual(row["payload"], {"suggested_order": "Paneer tikka + dal"})
        self.assertIsInstance(captured["payload"], dict)

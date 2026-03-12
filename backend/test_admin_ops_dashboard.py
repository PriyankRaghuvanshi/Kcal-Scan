"""
Tests for admin ops dashboard aggregator.
Run with: cd backend && python -m unittest test_admin_ops_dashboard -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch


class TestAdminOpsDashboard(unittest.TestCase):
    def test_build_ops_dashboard_summary_includes_sections(self):
        from admin_ops_dashboard import build_ops_dashboard_summary

        async def fetcher(lat: float, lng: float):
            return {"items": [], "_debug": {"timings_ms": {"total_ms": 100}, "fetched_count": 0, "shortlisted_count": 0, "deeply_ranked_count": 0}}

        with patch("admin_ops_dashboard.build_enrichment_status_summary", return_value={"priority_suburbs": [], "weak_suburbs": [], "next_targets": [], "by_action": {}, "generic_fallback_percent_overview": []}):
            out = asyncio.run(build_ops_dashboard_summary(fetch_fn=fetcher))

        self.assertIn("enrichment", out)
        self.assertIn("push", out)
        self.assertIn("scan", out)
        self.assertIn("actions", out)
        self.assertIn("apply_next_targets_endpoint", out["actions"])

    def test_push_summary_includes_rollout_fields(self):
        from admin_ops_dashboard import build_push_rollout_summary
        with patch("push_rollout.get_rollout_status", return_value={"sending_enabled": False, "rollout_mode": "disabled", "rollout_percent": 0, "active_user_days": 7, "max_per_6h": 1, "max_per_24h": 2}), \
             patch("push_batch_sender.list_users_with_active_push_tokens", return_value=[]), \
             patch("user_last_location_store.list_user_ids_with_location", return_value=[]), \
             patch("push_delivery_store.list_deliveries", return_value=[]):
            out = build_push_rollout_summary()
        self.assertIn("rollout_mode", out)
        self.assertIn("rollout_percent", out)
        self.assertIn("sending_enabled", out)

    def test_scan_summary_includes_ttfr_metrics(self):
        from admin_ops_dashboard import build_scan_health_summary
        out = build_scan_health_summary(window_days=7)
        self.assertIn("total_scans", out)
        self.assertIn("median_time_to_first_result_ms", out)
        self.assertIn("p90_time_to_first_result_ms", out)


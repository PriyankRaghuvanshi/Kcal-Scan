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

    def test_build_ops_dashboard_summary_includes_goal_coach(self):
        from admin_ops_dashboard import build_ops_dashboard_summary

        async def fetcher(lat: float, lng: float):
            return {"items": [], "_debug": {}}

        with patch("admin_ops_dashboard.build_enrichment_status_summary", return_value={"priority_suburbs": [], "weak_suburbs": [], "next_targets": [], "by_action": {}, "generic_fallback_percent_overview": []}), \
             patch("admin_ops_dashboard.build_push_rollout_summary", return_value={"rollout_mode": "off"}), \
             patch("admin_ops_dashboard.build_scan_health_summary", return_value={"total_scans": 0, "median_time_to_first_result_ms": 0}), \
             patch("admin_ops_dashboard.build_goal_coach_funnel_summary", return_value={"window_days": 7, "totals": {}, "conversion_rates": {}}):
            out = asyncio.run(build_ops_dashboard_summary(fetch_fn=fetcher))
        self.assertIn("goal_coach", out)
        self.assertEqual(out["goal_coach"]["window_days"], 7)
        self.assertIn("totals", out["goal_coach"])
        self.assertIn("conversion_rates", out["goal_coach"])

    def test_summarize_goal_coach_events_aggregates_correctly(self):
        from admin_ops_dashboard import summarize_goal_coach_events

        events = [
            {"event_type": "goal_coach_daily_action_shown", "source_surface": "daily_coach", "action_type": "open_healthy_nearby"},
            {"event_type": "goal_coach_daily_action_clicked", "source_surface": "daily_coach", "action_type": "open_healthy_nearby"},
            {"event_type": "goal_coach_destination_opened", "source_surface": "daily_coach", "action_type": "open_healthy_nearby"},
            {"event_type": "goal_coach_action_completed", "source_surface": "daily_coach", "action_type": "open_healthy_nearby"},
            {"event_type": "goal_coach_weekly_action_shown", "source_surface": "weekly_review", "action_type": "open_scan_camera"},
        ]
        out = summarize_goal_coach_events(events)
        self.assertEqual(out["totals"]["actions_shown"], 2)
        self.assertEqual(out["totals"]["actions_clicked"], 1)
        self.assertEqual(out["totals"]["destinations_opened"], 1)
        self.assertEqual(out["totals"]["actions_completed"], 1)
        self.assertIn("daily_coach", out["by_source_surface"])
        self.assertEqual(out["by_source_surface"]["daily_coach"]["shown"], 1)
        self.assertEqual(out["by_source_surface"]["daily_coach"]["completed"], 1)
        self.assertIn("open_healthy_nearby", out["by_action_type"])
        self.assertEqual(out["by_action_type"]["open_healthy_nearby"]["shown"], 1)
        self.assertEqual(out["by_action_type"]["open_healthy_nearby"]["completed"], 1)

    def test_summarize_goal_coach_events_empty_returns_zeros(self):
        from admin_ops_dashboard import summarize_goal_coach_events
        out = summarize_goal_coach_events([])
        self.assertEqual(out["totals"]["actions_shown"], 0)
        self.assertEqual(out["totals"]["actions_clicked"], 0)
        self.assertEqual(out["totals"]["destinations_opened"], 0)
        self.assertEqual(out["totals"]["actions_completed"], 0)
        self.assertEqual(out["by_source_surface"], {})
        self.assertEqual(out["by_action_type"], {})

    def test_build_goal_coach_funnel_summary_conversion_rates(self):
        from admin_ops_dashboard import build_goal_coach_funnel_summary

        mock_events = [
            {"event_type": "goal_coach_daily_action_shown", "action_type": "open_healthy_nearby"},
            {"event_type": "goal_coach_daily_action_shown", "action_type": "open_healthy_nearby"},
            {"event_type": "goal_coach_daily_action_clicked", "action_type": "open_healthy_nearby"},
            {"event_type": "goal_coach_destination_opened", "action_type": "open_healthy_nearby"},
            {"event_type": "goal_coach_action_completed", "action_type": "open_healthy_nearby"},
        ]
        with patch("goal_coach_action_tracking.list_goal_coach_events", return_value=mock_events):
            out = build_goal_coach_funnel_summary(window_days=7)
        self.assertEqual(out["totals"]["actions_shown"], 2)
        self.assertEqual(out["totals"]["actions_clicked"], 1)
        self.assertEqual(out["totals"]["destinations_opened"], 1)
        self.assertEqual(out["totals"]["actions_completed"], 1)
        self.assertEqual(out["conversion_rates"]["shown_to_clicked_pct"], 50.0)
        self.assertEqual(out["conversion_rates"]["shown_to_completed_pct"], 50.0)
        self.assertIn("open_healthy_nearby", out["by_action_type"])
        self.assertIn("top_action_types", out)
        self.assertIn("dropoff_summary", out)
        self.assertIn("optimization_hint", out)
        self.assertIn("optimization_plan", out)

    def test_build_goal_coach_funnel_summary_empty_store_returns_safe_zeros(self):
        from admin_ops_dashboard import build_goal_coach_funnel_summary
        with patch("goal_coach_action_tracking.list_goal_coach_events", return_value=[]):
            out = build_goal_coach_funnel_summary(window_days=7)
        self.assertEqual(out["totals"]["actions_shown"], 0)
        self.assertEqual(out["totals"]["actions_clicked"], 0)
        self.assertEqual(out["totals"]["destinations_opened"], 0)
        self.assertEqual(out["totals"]["actions_completed"], 0)
        self.assertEqual(out["conversion_rates"]["shown_to_clicked_pct"], 0.0)
        self.assertEqual(out["conversion_rates"]["shown_to_completed_pct"], 0.0)
        self.assertEqual(out["top_action_types"], [])
        self.assertIn("largest_dropoff_step", out["dropoff_summary"])
        self.assertIn("largest_dropoff_action_type", out["dropoff_summary"])
        self.assertIn("weakest_action_type", out["optimization_hint"])
        self.assertIn("path_key", out["optimization_plan"])


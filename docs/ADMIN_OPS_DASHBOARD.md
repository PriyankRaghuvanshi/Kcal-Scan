# Admin Ops Dashboard

## Purpose

Weekly operator loop visibility without hopping across many endpoints.

One compact internal dashboard (mobile internal modal) backed by one aggregation endpoint:

- **Enrichment health**: weak suburbs + next enrichment targets + canonical sync context
- **Push rollout health**: rollout config + batch eligibility estimate + recent delivery snapshot
- **Scan performance health**: TTFR/TTFinal p50/p90 + cache hit rates + latency breakdown
- **Goal Coach funnel**: shown → clicked → opened → completed + conversion rates + top action types + drop-off summary
- **Actions**: safe, explicit operator buttons (apply targets, batch dry-run, check receipts, auto-promote)

Internal tool: compact, action-oriented, no extra auth, no ranking changes, no LLM, no live menu fetch on `/places/healthy`.

## Backend

### Main aggregation endpoint

- **GET ` /admin/ops-dashboard `**
  - Query params:
    - `limit_targets` (default 20)
    - `limit_areas` (default 5)
    - `scan_window_days` (default 7)
    - `goal_coach_window_days` (default 7) — window in days for Goal Coach funnel events

### Action endpoints (explicit mutations / operations)

- **POST ` /admin/ops-dashboard/apply-next-targets `**
  - Body: `{ "limit": 20, "area_keys": ["wentworthville", "parramatta"] }`
  - Applies next-enrichment targets into canonical Supabase local profiles.

- **POST ` /admin/ops-dashboard/run-batch-dry-run `**
  - Body: `{ "limit_users": 100 }`
  - Runs Smart Alert batch in **dry_run=true** mode only (safe).

- **POST ` /admin/ops-dashboard/check-receipts `**
  - Body: `{ "limit": 100 }`
  - Checks pending Expo receipts and updates push delivery statuses; deactivates invalid tokens.

- **POST ` /admin/ops-dashboard/run-auto-promote `**
  - Body: `{ "limit": 100, "area_key": "parramatta" }` (area_key optional)
  - Runs evidence-based auto-promotion of venue contributions.

### Source modules reused

- Enrichment:
  - `backend/post_sync_remediation_report.py`
  - `backend/apply_enrichment_targets.py`
  - `backend/local_profile_supabase_sync.py`
  - `backend/suburb_remediation.py`
- Push:
  - `backend/push_rollout.py`
  - `backend/push_batch_sender.py`
  - `backend/push_delivery_store.py`
  - `backend/expo_push_service.py`
- Scan:
  - `backend/scan_performance_analytics.py`
- Goal Coach funnel:
  - `backend/goal_coach_action_tracking.py` (event store)
  - `backend/admin_ops_dashboard.py` (`build_goal_coach_funnel_summary`, `summarize_goal_coach_events`)

## Dashboard summary JSON structure (high level)

```json
{
  "generated_at": "2026-03-12T00:00:00Z",
  "enrichment": {
    "priority_suburbs": ["wentworthville", "parramatta", "..."],
    "weak_suburbs": [
      {
        "area_key": "parramatta",
        "display_name": "Parramatta",
        "percent_top_5_generic_fallback": 60.0,
        "visible_results_using_local_profiles_percent": 12.5,
        "known_chain_hidden_rate": 0.33,
        "duplicate_score_cluster_rate_top_5": 20.0,
        "canonical_trusted_local_profiles_count": 42,
        "pack_seeded_profiles": 10,
        "auto_promoted_profiles": 6
      }
    ],
    "next_targets": [ { "area_key": "...", "place_name": "...", "recommended_enrichment_action": "...", "priority_score": 48.0 } ],
    "by_action": { "add_profile_now": [ ... ], "add_swaps": [ ... ] },
    "generic_fallback_percent_overview": [ { "area_key": "...", "percent_top_5_generic_fallback": 40.0 } ]
  },
  "push": {
    "sending_enabled": false,
    "rollout_mode": "allowlist_only",
    "rollout_percent": 10,
    "active_user_days": 7,
    "max_per_6h": 1,
    "max_per_24h": 2,
    "batch_eligible_estimate": 123,
    "recent_sent_count": 5,
    "recent_receipt_ok_count": 4,
    "recent_receipt_error_count": 1
  },
  "scan": {
    "total_scans": 200,
    "median_time_to_first_result_ms": 1400,
    "p90_time_to_first_result_ms": 2600,
    "median_time_to_final_result_ms": 3100,
    "p90_time_to_final_result_ms": 5200,
    "vision_cache_hit_rate": 0.42,
    "cache_hit_rate": 0.63,
    "median_vision_ms": 480,
    "median_nutrition_ms": 220,
    "vision_cache_skipped_reasons": { "image_changed": 12 }
  },
  "goal_coach": {
    "window_days": 7,
    "totals": {
      "actions_shown": 120,
      "actions_clicked": 48,
      "destinations_opened": 41,
      "actions_completed": 19
    },
    "conversion_rates": {
      "shown_to_clicked_pct": 40.0,
      "clicked_to_opened_pct": 85.4,
      "opened_to_completed_pct": 46.3,
      "shown_to_completed_pct": 15.8
    },
    "by_source_surface": {
      "daily_coach": { "shown": 80, "clicked": 32, "opened": 28, "completed": 14 },
      "weekly_review": { "shown": 40, "clicked": 16, "opened": 13, "completed": 5 }
    },
    "by_action_type": {
      "open_healthy_nearby": { "shown": 60, "clicked": 30, "opened": 28, "completed": 15, "shown_to_completed_pct": 25.0 },
      "open_scan_camera": { "shown": 40, "clicked": 12, "opened": 10, "completed": 3, "shown_to_completed_pct": 7.5 }
    },
    "top_action_types": [
      { "action_type": "open_healthy_nearby", "shown_to_completed_pct": 25.0, "completed": 15 }
    ],
    "dropoff_summary": {
      "largest_dropoff_step": "opened_to_completed",
      "largest_dropoff_action_type": "open_scan_camera",
      "best_action_type": "open_healthy_nearby"
    }
  },
  "actions": {
    "apply_next_targets_endpoint": "/admin/ops-dashboard/apply-next-targets",
    "batch_push_dry_run_endpoint": "/admin/ops-dashboard/run-batch-dry-run",
    "check_receipts_endpoint": "/admin/ops-dashboard/check-receipts",
    "auto_promote_endpoint": "/admin/ops-dashboard/run-auto-promote"
  }
}
```

## Mobile internal UI

- Component: `mobile/components/AdminOpsDashboard.js`
- API helper: `mobile/adminOpsApi.js`
- Wired into app via the **internal coach debug panel**:
  - Tap the coach title **7 times quickly** to toggle debug.
  - In debug, tap **Ops Dashboard** to open the modal.

## Goal Coach funnel section

The dashboard includes a **Goal Coach** block when the backend returns `goal_coach`:

- **Summary cards**: Actions shown, click rate (shown→clicked %), completion rate (shown→completed %), best action type.
- **Funnel row**: shown → clicked → opened → completed counts.
- **Top action types**: action type label, shown→completed %, completed count.
- **Drop-off note**: Largest drop-off step (e.g. opened→completed), weakest action type, best action type.

Use this to answer: how often actions are shown, clicked, opened, and completed; which action types convert best; where the biggest drop-offs are. See **GOAL_COACH_ACTION_FUNNEL.md** for event definitions and how to interpret funnel drop-off.

**Recommended weekly addition:** Review Goal Coach funnel → compare best vs weakest action types → inspect largest drop-off step → improve CTA copy or destination UX accordingly.

## Recommended weekly operator workflow

1. Open **Admin Ops Dashboard**
2. Review **Weak suburbs** (generic fallback %, local profile usage, hidden chain rate)
3. Review **Next enrichment targets**
4. Click **Apply next 20 targets** (repeatable / idempotent)
5. Refresh dashboard; then re-run:
   - `GET /launch-readiness/post-sync-report/all?limit_areas=5`
6. Check **Push rollout** health + optionally run **batch dry-run**
7. Check **Receipts** and address token churn
8. Check **Scan health** (TTFR p50/p90, cache hit rates)
9. **Review Goal Coach funnel** (shown → clicked → opened → completed; top action types; drop-off note)
10. Repeat weekly


# Goal Coach Funnel Optimization (weekly loop)

Goal: make Goal Coach measurably stronger using the existing funnel events and Ops Dashboard aggregation.

## Inputs (no new analytics system)

- **Event store**: `backend/goal_coach_action_tracking.py`
- **Ops Dashboard**: `GET /admin/ops-dashboard?goal_coach_window_days=7`
  - `goal_coach.totals` (shown/clicked/opened/completed)
  - `goal_coach.conversion_rates` (shown→clicked, clicked→opened, opened→completed, shown→completed)
  - `goal_coach.by_action_type`
  - `goal_coach.by_source_surface`
  - `goal_coach.dropoff_summary`
  - `goal_coach.optimization_hint` + `goal_coach.optimization_plan` (deterministic interpretation)

## How weakest path is identified

Backend helper: `identify_weakest_goal_coach_path(summary)` in `backend/admin_ops_dashboard.py`.

Outputs:

- **weakest_action_type**: lowest shown→completed % among action types with enough volume (min shown threshold).
- **weakest_step**: lowest of shown→clicked, clicked→opened, opened→completed (prefers steps with enough volume).
- **weakest_source_surface**: lowest surface shown→completed % (daily_coach vs weekly_review) with enough volume.
- **likely_issue_type** (rule-of-thumb):
  - low **shown→clicked** → CTA/copy/context issue
  - low **clicked→opened** → routing/navigation issue
  - low **opened→completed** → destination friction issue

## How we choose one focused optimization

Backend helper: `get_goal_coach_path_optimization(weakest_hint)` maps the weakest path to a **single** recommended change set:

- **recommended_copy_change**
- **recommended_destination_change**
- **recommended_ui_change**
- **measurable_target_step** (the step to improve)
- optional: suggested success threshold

We intentionally optimize only the weakest path each week to keep changes measurable.

## Before/after measurability

1. Record baseline from Ops Dashboard:
   - `goal_coach.optimization_hint.baseline`
   - plus the path key from `goal_coach.optimization_plan.path_key`
2. Ship one focused change
3. Re-check the same window in the next weekly review:
   - Compare the **target step** conversion (e.g. opened→completed) and the weakest action’s shown→completed rate.

No experimentation platform required—this is a deterministic operator loop using the same event stream.

## Current focused optimization implemented

For the common weak path **`open_scan_camera:opened_to_completed`** (destination friction):

- **Copy**: scan CTAs changed to more immediate language (“Scan your meal now” / “Scan your next meal now”).\n+- **Destination behavior**: when a user opens scan from Goal Coach and takes a meal photo, the app **auto-starts Analyze** (best-effort) to reduce completion friction.\n+- **UI hint**: camera modal shows a one-line Goal Coach instruction (“take a meal photo — we’ll analyze it automatically.”).

Success is measured by a lift in **opened→completed** for `open_scan_camera` and overall scan completions in the Goal Coach funnel.


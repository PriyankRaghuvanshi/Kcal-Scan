# Goal Coach Action Funnel

Lightweight tracking for the Goal Coach CTA funnel: **shown → clicked → destination opened → completed**. No LLM; no analytics warehouse. Events are stored in a JSON-backed log and used to measure drop-off and completion.

## Event types

| Event | When |
|-------|------|
| `goal_coach_daily_action_shown` | Daily coach card renders with a primary action (once per action identity per session). |
| `goal_coach_daily_action_clicked` | User taps primary or secondary CTA on the daily card. |
| `goal_coach_weekly_action_shown` | Weekly review card renders with a next-step action. |
| `goal_coach_weekly_action_clicked` | User taps the next-step CTA on the weekly card. |
| `goal_coach_destination_opened` | App navigates to the target screen (Healthy Nearby, camera, supplement, home). |
| `goal_coach_action_completed` | User completes the intended action (see completion definitions below). |

## Metadata (per event)

Non-sensitive fields included where available:

- **user_id** (required)
- **source_surface**: `daily_coach` | `weekly_review` | `goal_plan`
- **action_type**: `open_healthy_nearby` | `open_scan_camera` | `open_supplement_scan` | `open_daily_summary` | `open_goal_plan`
- **goal_type**, **reason**
- **remaining_protein_g**, **remaining_calories**
- **kickoff_active**, **subscription_required**
- **preferred_mode** (for Healthy Nearby preselection)
- **completion_type** (for `goal_coach_action_completed`)
- **place_id**, **place_name** (when relevant)
- **timestamp**

## Completion definitions

| Destination | Completed when |
|-------------|----------------|
| **open_scan_camera** | Scan analysis result returned successfully (meal logged). |
| **open_supplement_scan** | Supplement scan/barcode flow completes successfully (result received). |
| **open_healthy_nearby** | User selects a place, opens map/directions, taps scan menu, submits recommendation feedback, or records a meal-decision event from that flow. |
| **open_daily_summary** | Summary screen viewed (lightweight; optional to implement). |

Completion is attributed using the same **action_type** and **source_surface** as the originating CTA (via `goalCoachContext` on the client).

## Backend

- **Module**: `backend/goal_coach_action_tracking.py`
  - `log_goal_coach_event(payload)` — append one event; payload must include `event_type` and `user_id`.
  - `list_goal_coach_events(user_id=..., event_type=..., start_date=..., end_date=..., limit=...)` — query events (newest first).
- **Endpoint**: `POST /goal-coach/events` — body: `{ "event_type", "user_id", ...metadata }`. Returns `{ "ok": true, "event": <row> }`.
- **Storage**: JSON file under `backend/data/goal_coach_action_events.json` (or `GOAL_COACH_ACTION_TRACKING_PATH`). Cap: 50k events; oldest dropped.

## Mobile helpers

In `mobile/utils/goalCoachUtils.js`:

- `trackGoalCoachActionShown(apiBase, userId, meta)` — daily or weekly shown (event type chosen from `source_surface`).
- `trackGoalCoachActionClicked(apiBase, userId, meta)` — CTA tapped.
- `trackGoalCoachDestinationOpened(apiBase, userId, meta)` — destination screen opened.
- `trackGoalCoachActionCompleted(apiBase, userId, meta)` — intended action completed.

All are fire-and-forget (no await in UI path). Failures must not block the product flow.

## Healthy Nearby preselection from Goal Coach

When Healthy Nearby is opened from a Goal Coach CTA:

1. **Extended context** is set: `goalCoachContext` includes `preferred_mode`, `action_reason`, `action_type`, `source_surface`, and existing fields (`remaining_protein_g`, `remaining_calories`, etc.).
2. **Preferred mode** is derived deterministically (no new ranking):
   - High remaining protein + calories available → **protein_rescue** → filter: High Protein.
   - Calories tight + still need protein → **lighter_option** → filter: Under 600 kcal.
   - Evening/dinner focus → **dinner_recovery** → filter: High Protein.
   - Logging/track focus → **logging_support** → filter: Best Right Now.
   - Default → **best_fit_today** → filter: Fits Today.
3. **Initial filter** is set from `preferredModeToFilterKey(preferred_mode)` so the list/map shows the biased subset of the *same* ranked list (no second ranking).
4. **Banner and card copy** use `getGoalCoachBannerText(ctx)` and `getGoalCoachHeroLabel(preferred_mode)` so the screen explains why the user is there (e.g. “You still need ~42g protein today”, “Lighter option that still helps your target”).

See **GOAL_COACH_ACTIONS.md** for action types and **GOAL_COACH_V1.md** for overall feature context.

## Ops Dashboard

The **Admin Ops Dashboard** (`GET /admin/ops-dashboard`) includes a **goal_coach** section that aggregates funnel events over a configurable window (default 7 days; query param `goal_coach_window_days`).

- **totals**: actions_shown, actions_clicked, destinations_opened, actions_completed
- **conversion_rates**: shown_to_clicked_pct, clicked_to_opened_pct, opened_to_completed_pct, shown_to_completed_pct
- **by_source_surface**: daily_coach, weekly_review (and goal_plan if present) with shown/clicked/opened/completed per surface
- **by_action_type**: per action_type (open_healthy_nearby, open_scan_camera, etc.) with counts and shown_to_completed_pct
- **top_action_types**: action types ordered by completed count and conversion (for “best” actions)
- **dropoff_summary**: largest_dropoff_step (e.g. opened_to_completed), largest_dropoff_action_type (weakest), best_action_type

The internal mobile **Admin Ops Dashboard** UI shows a compact Goal Coach block: summary cards (shown, click rate, completion rate, best action), funnel row (shown → clicked → opened → completed), top action types table, and a drop-off note. Use this in the **weekly operator workflow** to review Goal Coach performance, compare best vs weakest action types, and improve CTA copy or destination UX. See **ADMIN_OPS_DASHBOARD.md**.

## Interpreting funnel drop-off

- **Shown but not clicked**: Surfaces or copy may need tuning; check by `source_surface` and `action_type`.
- **Clicked but no destination_opened**: Navigation or errors; check client/network.
- **Destination opened but no completed**: User left before completing (e.g. opened Healthy Nearby but didn’t select a place or open directions). Use completion rate by `action_type` to prioritize flows.
- **Completed**: Full conversion; segment by `source_surface` and `goal_type` for cohort analysis.

Query events with `list_goal_coach_events()` (or a thin admin/analytics endpoint) filtered by `user_id`, `event_type`, and optional date range. No PII beyond `user_id`; no free-text in required fields.

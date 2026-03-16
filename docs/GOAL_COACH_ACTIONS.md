# Goal Coach — Action Mapping and CTAs

Goal Coach daily and weekly recommendations are mapped to **deterministic in-app actions** so users can act on guidance immediately. No LLM on the hot path; no separate recommendation engine. Existing flows (Healthy Nearby, Scan, Supplement scanner, Daily summary) are reused with optional context from the plan.

## Action types

| `action_type` | Destination | When used |
|---------------|-------------|-----------|
| `open_healthy_nearby` | Healthy Nearby screen | Protein behind + daytime; find high-protein meal or lighter option |
| `open_scan_camera` | Meal scan camera | Little logged so far (meal time); or default “log next meal”; weekly “log more consistently” |
| `open_supplement_scan` | Barcode modal in supplement mode | Protein gap + optional quick add-on (e.g. shake) |
| `open_daily_summary` | Home, scroll to top (Scans left / goals) | Calories tight; late-night risk; check totals |
| `open_goal_plan` | Home (Goal Coach section) | Weekly “plan next week” generic |

## Action object shape

```json
{
  "action_type": "open_healthy_nearby",
  "label": "Find a high-protein meal nearby",
  "reason": "Protein is behind today",
  "context": {
    "goal": "fat_loss",
    "remaining_protein_g": 42,
    "remaining_calories": 780
  }
}
```

- **Backend** (`goal_coach.py`): `build_daily_suggested_actions(state, current_hour_local)` returns `{ "primary_action", "secondary_action?" }`. `build_weekly_next_step_action(review)` returns one action or `null`.
- **Mobile** (`goalCoachUtils.js`): `getDailyActions(daily)` uses server `suggested_actions` when present, else `deriveDailyActions(daily)`. `getWeeklyNextStepAction(weeklyResponse)` uses server `next_step_action` or derives from `review`.

## Daily coach CTA logic (backend)

- **Protein behind + daytime (6–18)** → primary: `open_healthy_nearby` (“Find a high-protein meal nearby”); optional secondary: `open_supplement_scan` if remaining protein ≥ 40.
- **Calories high + protein still low** (or remaining cal ≤ 350 for fat_loss) → primary: `open_daily_summary` (“Check today's totals”); optional secondary: `open_healthy_nearby` (“Find a lighter high-protein option”).
- **Very little logged (consumed &lt; 400) + meal time (7–21)** → primary: `open_scan_camera` (“Log your meal”).
- **Late-night risk / late_night_snacking_pattern** → primary: `open_daily_summary`.
- **Default** → primary: `open_scan_camera` (“Log your next meal”); optional secondary: `open_healthy_nearby` if daytime and remaining protein ≥ 30.

`current_hour_local` is optional query param on `GET /goal-coach/daily`; if omitted, hour is treated as 12 (daytime).

## Weekly review CTA logic (backend)

- **Logging consistency** (days_tracked &lt; 5 or “logging”/“log” in next_week_focus) → `open_scan_camera` (“Log meals more consistently this week”).
- **Protein focus** (days_under_protein ≥ 2 or “protein” in headline/bottleneck) → `open_healthy_nearby` (“Improve protein choices nearby”).
- **Calorie/dinner focus** (days_over_target ≥ 2 or “dinner”/“calories” in headline/bottleneck) → `open_healthy_nearby` (“Plan lighter dinner options nearby”).
- **Generic next week** (headline/supporting from next_week_focus) → `open_goal_plan`.
- **Fallback** → `open_scan_camera` (“Log meals more consistently this week”).

## UI cards and CTAs

- **DailyCoachCard**: Primary CTA button (from `primary_action.label`) and optional secondary CTA. Both call `onPrimaryAction` / `onSecondaryAction` with the action object.
- **WeeklyPlanReviewCard**: One “next step” button from `next_step_action.label`; `onNextStepAction(action)`.
- **GoalPlanCard**: Optional “View today's action” when there is a daily primary action; triggers that primary action (or scroll to daily card).

## Navigation integration (App.js)

- `handleGoalCoachAction(action)` switches on `action.action_type`:
  - `open_healthy_nearby` → `setActiveScreen("healthy_nearby")`; stores **extended** `goalCoachContext` (includes `preferred_mode`, `action_reason`, `source_surface`); preselects Healthy Nearby filter from context; calls `loadHealthyPlacesNearby({ preserveFilter: true })`.
  - `open_scan_camera` → `setCamOpen(true)`.
  - `open_supplement_scan` → `setBarcodeMode("supplement")`; `setBarcodeOpen(true)`.
  - `open_daily_summary` → `setActiveScreen("home")`; scroll to top.
  - `open_goal_plan` → `setActiveScreen("home")`.
- **Healthy Nearby**: Receives `goalCoachContext`. When set, shows a **context-aware banner** (e.g. “Goal Coach: you still need ~42g protein today” for protein_rescue; “calories are tighter now — lighter protein option recommended” for lighter_option) and **preselects the filter** (High Protein, Under 600 kcal, Fits Today, Best Right Now) from `preferred_mode`. Bottom card hero copy matches the coach intent (e.g. “Best protein-focused next move”, “Lighter option that still helps your target”). Same ranked list; no second ranking.
- **Action funnel**: Shown/clicked/destination_opened/action_completed events are logged via `POST /goal-coach/events`. See **GOAL_COACH_ACTION_FUNNEL.md**.

## API response shapes

- **GET /goal-coach/daily**: Adds `suggested_actions: { primary_action, secondary_action? }`. Optional query: `current_hour` (0–23, local).
- **GET /goal-coach/weekly**: Adds `next_step_action: { action_type, label, reason, context? }`.

## Tests

- **Backend** (`test_goal_coach.py`): `test_daily_suggested_actions_protein_behind_healthy_nearby`, `test_daily_suggested_actions_logging_needed_scan`, `test_daily_suggested_actions_calories_tight_daily_summary`, `test_weekly_next_step_action_protein_focus`, `test_weekly_next_step_action_logging_focus`.
- **Mobile**: Actions come from API or client-side derivation; CTAs render when `primary_action` / `next_step_action` exist and handlers are passed.

## Summary

- Coach state (daily + optional weekly) is mapped deterministically to one primary and optionally one secondary action.
- CTAs on Daily and Weekly cards lead to Healthy Nearby, Scan camera, Supplement scanner, or Daily summary.
- Context (goal, remaining protein/calories, **preferred_mode**) is passed so Healthy Nearby can show a context-aware banner, preselect the right filter, and use coach-aligned card copy.
- **Funnel tracking**: Shown → clicked → destination opened → completed is logged; see **GOAL_COACH_ACTION_FUNNEL.md** for events, metadata, and completion definitions.

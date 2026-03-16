# Let's Go Goal Coach — v1

Lean v1 of the **Let's Go Goal Coach** premium feature in CalorieClick. Users choose a goal (fat loss, muscle gain, recomp, maintain), set a timeframe and preferences, and get a deterministic starter plan plus daily and weekly coaching. No LLM on the hot path; optional richer language can be layered later.

## Scope (v1)

- **Plan setup**: Goal type, timeframe, pace, training days, diet preference, optional weight.
- **Starter plan**: Deterministic targets (calories, protein, carbs, fat), weekly focus, risk note, first 3 actions.
- **Daily coach**: Today's targets, consumed so far, one best action, short coach summary, risk flags.
- **Weekly review**: Adherence/resilience/risk scores, main win, main bottleneck, next week focus.
- **Kickoff**: 7-day free guided coaching; after that, plan remains visible but adaptive daily/weekly coach is gated; paywall card prompts subscription.
- **Persistence**: JSON-backed `goal_plan_store`; plan is never hard-deleted on gating.

## Backend

### Modules

- **`goal_plan_store.py`**: Create/get/update goal plans (JSON file under `backend/data/goal_plans.json`). One active plan per user; pause/resume by status.
- **`goal_coach.py`**: Deterministic logic only:
  - `build_starter_plan(plan_input)` → targets, weekly_focus, risk_note, first_actions.
  - `compute_kickoff_status(plan)` → kickoff_days_used, in_kickoff, requires_subscription.
  - `build_daily_coach_state(plan, daily_metrics, memory_signals)` → targets, consumed, remaining, coach_focus, one_action_today, headline, risk_flags.
  - **`build_daily_suggested_actions(state, current_hour_local)`** → primary_action, optional secondary_action (open_healthy_nearby, open_scan_camera, open_supplement_scan, open_daily_summary).
  - `build_weekly_review(plan, days, memory_signals)` → adherence_score, resilience_score, risk_score, main_win, main_bottleneck, next_week_focus, goal_type.
  - **`build_weekly_next_step_action(review)`** → one next-step action for the app.

### Endpoints (`main.py`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/goal-coach/plan/create` | Create plan; body: goal_type, timeframe_weeks?, pace_mode?, training_days_per_week?, diet_preference?, current_weight?, target_weight?. Returns plan + kickoff_day, kickoff_days_total, kickoff_active, subscription_required. |
| GET | `/goal-coach/plan` | Get active plan + kickoff status. |
| GET | `/goal-coach/daily` | Daily coach state: today_targets, consumed_so_far, coach_focus, best_action_today, coach_summary, risk_flags, **suggested_actions** (primary_action, secondary_action?), subscription_required, kickoff_*. Optional query: `current_hour` (0–23). |
| GET | `/goal-coach/weekly` | Weekly review: week_start, week_end, review, **next_step_action**, subscription_required. |
| POST | `/goal-coach/plan/pause` | Pause active plan. |
| POST | `/goal-coach/plan/resume` | Resume (most recent) plan. |

Daily consumed data comes from existing `daily_metrics` (Supabase) when available; weekly uses `get_daily_metrics_window` and maps rows to day shape for `weekly_coach.build_weekly_coach_payload` and goal_coach `build_weekly_review`.

### Subscription gating

- **Free kickoff**: First 7 days after plan creation (`kickoff_started_at`) are `in_kickoff`; `subscription_required` is false.
- After kickoff: `subscription_required` is true; plan and progress remain; daily/weekly endpoints still return data but client can show paywall card and optionally limit or gate adaptive copy.

## Mobile

- **Entry**: "Goal Coach" section with "Let's Go" button when no plan; when plan exists, show Goal Plan card, Daily Coach card, Weekly Review card, and (after kickoff) Plan Paywall card.
- **`LetsGoSetupModal`**: Collects goal_type, pace_mode, timeframe_weeks, training_days_per_week, diet_preference, optional current_weight/target_weight; submits to `POST /goal-coach/plan/create`.
- **`GoalPlanCard`**: Shows goal label, targets, timeframe, weekly focus, first actions; optional "View today's action" CTA when daily has an action.
- **`DailyCoachCard`**: Progress bars, best action, coach summary, risk chips; **primary and optional secondary CTA buttons** from suggested_actions (e.g. "Find a high-protein meal nearby", "Log your meal").
- **`WeeklyPlanReviewCard`**: Headline, adherence %, main win, bottleneck, next week focus; **one next-step CTA** (e.g. "Improve protein choices nearby", "Log meals more consistently").
- **`PlanPaywallCard`**: "Unlock your ongoing adaptive coach" and View subscription (onUnlock can open in-app purchase / subscription screen).
- **`utils/goalCoachUtils.js`**: API helpers for create, get plan, get daily, get weekly, pause, resume; **`getDailyActions(daily)`**, **`getWeeklyNextStepAction(weeklyResponse)`**; action-type constants.

App loads plan on login; when plan exists, fetches daily (with `current_hour`) and weekly. **CTAs** on daily and weekly cards call `handleGoalCoachAction(action)`, which navigates to Healthy Nearby, Scan camera, Supplement scanner, or Daily summary. **Healthy Nearby** receives extended `goalCoachContext` (including `preferred_mode`) and shows a context-aware banner, preselects the most relevant filter (High Protein, Under 600 kcal, Fits Today, Best Right Now), and uses coach-aligned card copy (e.g. "Best protein-focused next move") — all without a second ranking engine. **Action funnel** (shown → clicked → destination opened → completed) is tracked via `POST /goal-coach/events`; see **docs/GOAL_COACH_ACTION_FUNNEL.md**.

See **docs/GOAL_COACH_ACTIONS.md** for action-mapping rules, CTA destinations, and context integration.

## Tests

- **`test_goal_plan_store.py`**: Create/get active plan, update status (pause/resume), only one active per user, list limit.
- **`test_goal_coach.py`**: Starter plan fields, daily coach state, weekly review, kickoff status; **daily suggested_actions** (protein-behind → Healthy Nearby, logging-needed → Scan, calories-tight → Daily summary); **weekly next_step_action** (protein focus → Healthy Nearby, logging focus → Scan).
- **`test_goal_coach_action_tracking.py`**: Funnel event logging (daily/weekly shown and clicked, destination opened, action completed), metadata shape, validation (invalid event type, missing user_id), list filtering by user and event type.
- **Mobile** (`goalCoachUtils.test.js`, `healthyNearbyUtils.test.js`): `derivePreferredModeFromContext` (protein_rescue, lighter_option, dinner_recovery, logging_support, best_fit_today), `preferredModeToFilterKey`; `getGoalCoachBannerText`, `getGoalCoachHeroLabel`.

## Definition of done (v1)

- User can start a goal plan via Let's Go → setup modal → create.
- App generates a real deterministic starter plan.
- Daily coach shows targets, consumed, one best action, and short summary (deterministic).
- Weekly review shows adherence, win, bottleneck, next focus.
- Kickoff period (7 days) is tracked; after that, subscription_required is true and paywall card is shown.
- Plan is never deleted; pause/resume work on the correct plan.
- Feature is lean, deterministic, and shippable; no LLM required for core experience.
- **Actions**: Daily and weekly coach recommendations map to in-app CTAs (Healthy Nearby, Scan, Supplement, Daily summary); see GOAL_COACH_ACTIONS.md.

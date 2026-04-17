# CalorieClick Family Habits MVP Implementation Plan

## Discovery Summary

- The real product repo is `/Users/priyankraghuvanshi/projects/kcal-photo-app`.
- The mobile app is an Expo app with a large single-shell entrypoint in `mobile/App.js`.
- Supabase is already used for:
  - auth in mobile via `supabase.auth`
  - plan / entitlement helpers
  - backend canonical stores and queue-like tables through direct REST calls with `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
- Existing backend product logic is primarily served from `backend/main.py`, not the smaller `backend/app/` FastAPI sub-app.
- Existing deterministic patterns already exist for:
  - coach flows: `goal_coach.py`, `weekly_coach.py`, `day_coach.py`
  - meal / decision learning: `meal_feedback_store.py`, `meal_decision_event_store.py`, `recipe_suggestions.py`
  - Supabase integration: `supabase_intelligence_store.py`, SQL files in `backend/*.sql`
- Existing repo does not use a formal `supabase/migrations` directory. The current migration pattern is checked-in SQL files plus backend table checks.

## Reuse Strategy

- Reuse Supabase auth user id as the ownership boundary for all CalorieClick Family Habits data.
- Reuse the backend `main.py` API style with `X-User-Id` / `user_id` request patterns.
- Reuse existing deterministic coach architecture:
  - compute data first
  - optional LLM phrasing second
- Reuse current mobile shell and styling tokens/components instead of adding a new navigation framework.

## MVP Architecture

### Backend

- Add SQL migration file(s) in `backend/` for CalorieClick Family Habits tables and RLS policies.
- Add new deterministic service modules:
  - `backend/family_meal_recommendation_service.py`
  - `backend/family_exposure_service.py`
  - `backend/family_rescue_service.py`
  - `backend/family_weekly_reset_service.py`
  - `backend/family_memory_service.py`
- Add prompt helper module:
  - `backend/family_habits_prompting.py`
- Extend `backend/main.py` with CalorieClick Family Habits endpoints only.

### Data model

- Add Supabase tables:
  - `households`
  - `household_members`
  - `children`
  - `child_safe_foods`
  - `child_target_foods`
  - `meals_served`
  - `meal_components`
  - `child_meal_outcomes`
  - `food_exposures`
  - `routine_signals`
  - `rescue_sessions`
  - `weekly_resets`
  - `family_meal_memory`
- Use `auth.users(id)` for ownership where possible.
- Add RLS policies scoped to household owner / member access.

### Mobile

- Add CalorieClick Family Habits API helpers in `mobile/utils/`.
- Add focused components in `mobile/components/`.
- Add a lightweight CalorieClick Family Habits surface inside `mobile/App.js` using the existing app shell, not a full navigation rewrite.
- Build screens/sections for:
  - Routine Setup
  - CalorieClick Family Habits Overview
  - One Meal Tonight
  - Exposure Tracker
  - Parent Rescue Mode
  - Weekly Family Reset
  - Lunchbox support can stay future-facing and is not required for MVP

## Deterministic vs LLM

- Deterministic:
  - meal recommendation ranking
  - exposure summary derivation
  - rescue template selection
  - weekly drift detection
  - memory updates
- LLM only for final calm phrasing of:
  - meal explanation copy
  - rescue wording
  - weekly reset summary text
  - exposure next-step recommendation wording
- Guardrails:
  - no calorie targets for children
  - no child weight-loss framing
  - no medical or diagnostic advice
  - no preventive-health, monitoring, or whole-family-wellbeing framing

## Delivery Sequence

1. Add CalorieClick Family Habits SQL schema + policies.
2. Add deterministic backend services and seed data.
3. Add backend endpoints in `main.py`.
4. Add mobile API helpers + CalorieClick Family Habits UI shell.
5. Add deterministic tests.
6. Add `IMPLEMENTATION_NOTES.md` after implementation.

## Assumptions

- Supabase is the right persistence layer for CalorieClick Family Habits because the repo already depends on Supabase auth and production tables.
- SQL migration files are the repo-native schema delivery mechanism.
- Mobile auth already provides the stable user id needed to scope CalorieClick Family Habits records.

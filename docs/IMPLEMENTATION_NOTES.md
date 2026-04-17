# CalorieClick Family Habits MVP Implementation Notes

## Schema added
- Added `/Users/priyankraghuvanshi/projects/kcal-photo-app/backend/family_habits_schema.sql`
- New tables:
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
- Added RLS policies based on `households.owner_user_id = auth.uid()`.

## Routes added
- `GET /family-habits/household`
- `POST /family-habits/household`
- `GET /family-habits/children`
- `POST /family-habits/children`
- `PUT /family-habits/children/{child_id}`
- `POST /family-habits/children/{child_id}/safe-foods`
- `POST /family-habits/children/{child_id}/target-foods`
- `POST /family-habits/meal-tonight/generate`
- `POST /family-habits/meals/served`
- `POST /family-habits/meals/outcome`
- `POST /family-habits/exposures`
- `GET /family-habits/exposures/summary`
- `POST /family-habits/rescue`
- `GET /family-habits/weekly-reset/latest`
- `POST /family-habits/weekly-reset/generate`
- `GET /family-habits/dashboard`
  - used as the CalorieClick Family Habits overview payload inside the main app shell, not a broad family-health dashboard

## Services added
- `/Users/priyankraghuvanshi/projects/kcal-photo-app/backend/family_habits_logic.py`
  - deterministic meal recommendation ranking
  - exposure summary builder
  - rescue mapping
  - weekly reset selector
  - family memory snapshot builder
- `/Users/priyankraghuvanshi/projects/kcal-photo-app/backend/family_habits_prompts.py`
  - guardrailed prompt templates for future LLM wording
- `/Users/priyankraghuvanshi/projects/kcal-photo-app/backend/family_habits_store.py`
  - JSON fallback store for local/dev resilience when Supabase tables are unavailable

## Frontend added
- `/Users/priyankraghuvanshi/projects/kcal-photo-app/mobile/utils/familyHabitsApi.js`
- `/Users/priyankraghuvanshi/projects/kcal-photo-app/mobile/components/FamilyHabitsScreen.js`
- `/Users/priyankraghuvanshi/projects/kcal-photo-app/mobile/App.js` updated to expose a `CalorieClick Family Habits` screen entry inside the existing CalorieClick shell.

## Deterministic vs LLM-driven
- Deterministic now:
  - meal ranking
  - exposure state classification
  - rescue template selection
  - weekly drift detection
  - family meal memory rollup
- LLM-ready but not required for core logic:
  - One Meal Tonight calm wording
  - Parent Rescue Mode phrasing
  - Weekly Family Reset summary tone pass
  - Exposure Tracker next-step phrasing

## Still pending / future work
- Apply the SQL schema to Supabase for production persistence.
- Add analytics events for CalorieClick Family Habits surfaces.
- Add richer child editing and multi-child safe/target food management in the mobile UI.
- Add dedicated endpoint tests once the production Supabase tables are migrated.
- Replace prompt previews with actual guarded LLM rewrite calls if/when desired.

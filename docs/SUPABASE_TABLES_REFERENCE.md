# Supabase Tables Reference (Build & Deploy)

## No new Supabase tables from recent features

The following features **do not** use Supabase; they use **file-backed storage** on the backend server:

- **Let's Go / Goal Coach / Journey** (weight, check-ins, progress photos) → `backend/data/journey_entries.json` (via `journey_store.py`)
- **Goal plans** (fat loss 90d, comp prep, etc.) → `backend/data/goal_plans.json` (via `goal_plan_store.py`)
- **Goal coach action events** (analytics) → `backend/data/goal_coach_action_events.json` (via `goal_coach_action_tracking.py`)

So you **do not** need to create any new Supabase tables for those. Ensure the backend has write access to `backend/data/` (or set `JOURNEY_STORE_PATH` / env overrides if you use a different path).

---

## All Supabase tables used by the backend

The **main** backend (`main.py`) and related modules expect these Supabase tables. If you already have a working deploy, you likely have most of them. Before a **new** or **clean** deploy, ensure the following exist.

### Tables that have SQL in this repo (run these in Supabase SQL Editor)

| Table | SQL file | Notes |
|-------|----------|--------|
| `analysis_jobs` | `backend/create_analysis_jobs.sql` | Job queue for async meal analysis |
| `user_weekly_metrics` | `backend/phase_3_2_prediction_engine.sql` | Weekly consistency / prediction metrics |
| `chain_menu_profiles` | `backend/supabase_chain_menu_tables.sql` | Optional; for chain menu enrichment |
| `chain_menu_items` | `backend/supabase_chain_menu_tables.sql` | Optional; for chain menu enrichment |

### Core tables (no SQL file in repo – create if missing)

These are required for scan limits, goals, and daily summary. If your project already has them, skip. Otherwise use the SQL below.

#### 1. `plan_limits`

Used for scan quotas per plan (free, elite, advanced, pro, infinite).

```sql
create table if not exists public.plan_limits (
  plan text primary key,
  daily_limit int not null,
  monthly_limit int not null
);

-- Seed default limits (adjust as needed)
insert into public.plan_limits (plan, daily_limit, monthly_limit) values
  ('free', 25, 25),
  ('elite', 15, 50),
  ('advanced', 20, 100),
  ('pro', 25, 1000),
  ('infinite', 30, 10000)
on conflict (plan) do update set
  daily_limit = excluded.daily_limit,
  monthly_limit = excluded.monthly_limit;
```

#### 2. `user_usage`

Used for per-user plan and remaining scan counts (daily/monthly).

```sql
create table if not exists public.user_usage (
  user_id uuid primary key references auth.users(id) on delete cascade,
  plan text not null default 'free',
  remaining_day int not null default 0,
  remaining_month int not null default 0,
  day_reset date not null default current_date,
  month_reset date not null default (date_trunc('month', now())::date),
  updated_at timestamptz not null default now()
);

create index if not exists idx_user_usage_plan on public.user_usage(plan);
```

### Other tables referenced by main.py (create as needed for your features)

The backend can tolerate **missing** tables for some features (it disables or skips them). The following are used when present:

| Table | Purpose |
|-------|---------|
| `barcode_products` | Barcode lookup cache |
| `user_goals` | User daily goals (kcal, protein, etc.) |
| `daily_totals` | Daily nutrition totals |
| `daily_summary` | Daily summary + remaining |
| `meal_events` | Meal event log |
| `daily_metrics` | Daily metrics for coach |
| `weekly_insights` | Weekly insights cache |
| `meal_analyses` | Meal analysis results (async pipeline) |
| `analysis_memory` | Analysis memory / learning |
| `meal_edits` | User edits to meals |
| `user_calibration` | Calibration settings |
| `coach_memory` | Coach context memory |
| `coach_feedback` | Coach feedback queue |
| `user_food_priors` | Food priors |
| `coach_voice_cache` | Coach voice cache |
| `coach_events` | Coach events |
| `weekly_reports` | Weekly report cache |
| `program_status` | Program status |
| `confidence_audit` | Confidence audit log |
| `confidence_calibration_settings` | Calibration settings |
| `user_ai_consent` | AI processing consent |
| `supplement_scans` | Supplement scan results |
| `supplement_brand_profiles` | Supplement brand data |
| `supplement_batch_patterns` | Supplement batch patterns |
| `supplement_user_flags` | Supplement user flags |

**Intelligence store** (optional, for Healthy Nearby / chain menus):

| Table | Purpose |
|-------|---------|
| `venue_intelligence_cache` | Venue intelligence cache |
| `local_venue_profiles` | Local venue profiles |
| `local_venue_templates` | Venue templates |
| `local_venue_swaps` | Venue swaps |
| `enrichment_queue` | Enrichment queue |
| `chain_menu_items` | See SQL above |
| `chain_menu_profiles` | See SQL above |

---

## Minimum for “build and deploy” (scan limits + analyze)

For the app to run with **scan limits**, **paywall**, and **meal analyze** (including UPF scanner), you need at least:

1. **`plan_limits`** – create and seed (SQL above).
2. **`user_usage`** – create (SQL above).
3. **`analysis_jobs`** – run `backend/create_analysis_jobs.sql` if you use async analyze.

If you already have `user_usage` and `plan_limits` from a previous deploy, you do **not** need to add any new Supabase tables for the recent features (Let's Go, Journey, UPF scanner, conversion tweaks).

---

## Build and deploy (high level)

1. **Supabase**  
   - Run the SQL for any of the tables above that you don’t already have (at minimum `plan_limits`, `user_usage`, and optionally `analysis_jobs`).
2. **Backend**  
   - Ensure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set in the environment.  
   - Ensure `backend/data/` exists and is writable (for journey and goal_plan JSON files).
3. **Mobile**  
   - Configure EAS (or your build pipeline), env vars, and RevenueCat if needed.  
   - Build: e.g. `eas build --platform ios` / `--platform android`.  
   - Submit to stores or deploy via your usual process.

If you want, the next step can be a short **deploy checklist** (env vars, EAS config, and exact build commands) tailored to your repo.

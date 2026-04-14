-- goal_plans: durable storage for Let's Go Goal Coach plans.
-- Previously stored in backend/data/goal_plans.json, which Railway wipes on every deploy.

create table if not exists public.goal_plans (
    plan_id uuid primary key,
    user_id text not null,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    goal_type text,
    goal_preset text,
    pace_mode text,
    timeframe_weeks int,
    timeline_days int,
    target_date text,
    training_days_per_week int,
    diet_preference text,
    current_weight numeric,
    target_weight numeric,
    kickoff_started_at timestamptz,
    starter_plan jsonb default '{}'::jsonb
);

create index if not exists idx_goal_plans_user_id on public.goal_plans(user_id);
create index if not exists idx_goal_plans_user_status_updated
    on public.goal_plans(user_id, status, updated_at desc);

-- Service role bypasses RLS, but enable + permissive policy for safety if anon ever touches it.
alter table public.goal_plans enable row level security;

drop policy if exists goal_plans_service_all on public.goal_plans;
create policy goal_plans_service_all
    on public.goal_plans
    for all
    to public
    using (true)
    with check (true);

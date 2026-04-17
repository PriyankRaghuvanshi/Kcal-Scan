create extension if not exists pgcrypto;

create table if not exists public.households (
  household_id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null,
  household_name text,
  goal text,
  meal_style text,
  timezone text,
  routine_pain_points jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (owner_user_id)
);

create table if not exists public.household_members (
  member_id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(household_id) on delete cascade,
  member_name text not null,
  member_role text not null default 'parent',
  created_at timestamptz not null default now()
);

create table if not exists public.children (
  child_id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(household_id) on delete cascade,
  display_name text not null,
  age_band text,
  allergies jsonb not null default '[]'::jsonb,
  restrictions jsonb not null default '[]'::jsonb,
  sensory_notes text,
  friction_points jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.child_safe_foods (
  safe_food_id uuid primary key default gen_random_uuid(),
  child_id uuid not null references public.children(child_id) on delete cascade,
  food_name text not null,
  notes text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.child_target_foods (
  target_food_id uuid primary key default gen_random_uuid(),
  child_id uuid not null references public.children(child_id) on delete cascade,
  food_name text not null,
  notes text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.meals_served (
  meal_id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(household_id) on delete cascade,
  meal_name text not null,
  date_served timestamptz not null default now(),
  time_available_min int,
  parent_energy_level text,
  dinner_goal text,
  separate_meals_needed boolean not null default false,
  is_takeaway boolean not null default false,
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists public.meal_components (
  component_id uuid primary key default gen_random_uuid(),
  meal_id uuid not null references public.meals_served(meal_id) on delete cascade,
  component_type text not null,
  component_name text not null,
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists public.child_meal_outcomes (
  outcome_id uuid primary key default gen_random_uuid(),
  child_id uuid not null references public.children(child_id) on delete cascade,
  meal_id uuid not null references public.meals_served(meal_id) on delete cascade,
  response_stage text,
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists public.food_exposures (
  exposure_id uuid primary key default gen_random_uuid(),
  child_id uuid not null references public.children(child_id) on delete cascade,
  meal_id uuid references public.meals_served(meal_id) on delete set null,
  food_name text not null,
  food_format text,
  paired_safe_food text,
  response_stage text not null,
  context_tags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.routine_signals (
  signal_id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(household_id) on delete cascade,
  signal_date date not null default current_date,
  signal_type text not null,
  signal_value text,
  created_at timestamptz not null default now()
);

create table if not exists public.rescue_sessions (
  rescue_session_id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(household_id) on delete cascade,
  issue_type text not null,
  response_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.weekly_resets (
  weekly_reset_id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(household_id) on delete cascade,
  week_start date not null,
  payload_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.family_meal_memory (
  memory_id uuid primary key default gen_random_uuid(),
  household_id uuid not null references public.households(household_id) on delete cascade,
  memory_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (household_id)
);

alter table public.households enable row level security;
alter table public.household_members enable row level security;
alter table public.children enable row level security;
alter table public.child_safe_foods enable row level security;
alter table public.child_target_foods enable row level security;
alter table public.meals_served enable row level security;
alter table public.meal_components enable row level security;
alter table public.child_meal_outcomes enable row level security;
alter table public.food_exposures enable row level security;
alter table public.routine_signals enable row level security;
alter table public.rescue_sessions enable row level security;
alter table public.weekly_resets enable row level security;
alter table public.family_meal_memory enable row level security;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='households' and policyname='households_own_all') then
    create policy households_own_all on public.households for all using (auth.uid() = owner_user_id) with check (auth.uid() = owner_user_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='children' and policyname='children_household_owner_all') then
    create policy children_household_owner_all on public.children for all using (
      exists (select 1 from public.households h where h.household_id = children.household_id and h.owner_user_id = auth.uid())
    ) with check (
      exists (select 1 from public.households h where h.household_id = children.household_id and h.owner_user_id = auth.uid())
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='household_members' and policyname='household_members_owner_all') then
    create policy household_members_owner_all on public.household_members for all using (
      exists (select 1 from public.households h where h.household_id = household_members.household_id and h.owner_user_id = auth.uid())
    ) with check (
      exists (select 1 from public.households h where h.household_id = household_members.household_id and h.owner_user_id = auth.uid())
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='child_safe_foods' and policyname='child_safe_foods_owner_all') then
    create policy child_safe_foods_owner_all on public.child_safe_foods for all using (
      exists (
        select 1 from public.children c join public.households h on h.household_id = c.household_id
        where c.child_id = child_safe_foods.child_id and h.owner_user_id = auth.uid()
      )
    ) with check (
      exists (
        select 1 from public.children c join public.households h on h.household_id = c.household_id
        where c.child_id = child_safe_foods.child_id and h.owner_user_id = auth.uid()
      )
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='child_target_foods' and policyname='child_target_foods_owner_all') then
    create policy child_target_foods_owner_all on public.child_target_foods for all using (
      exists (
        select 1 from public.children c join public.households h on h.household_id = c.household_id
        where c.child_id = child_target_foods.child_id and h.owner_user_id = auth.uid()
      )
    ) with check (
      exists (
        select 1 from public.children c join public.households h on h.household_id = c.household_id
        where c.child_id = child_target_foods.child_id and h.owner_user_id = auth.uid()
      )
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='meals_served' and policyname='meals_served_owner_all') then
    create policy meals_served_owner_all on public.meals_served for all using (
      exists (select 1 from public.households h where h.household_id = meals_served.household_id and h.owner_user_id = auth.uid())
    ) with check (
      exists (select 1 from public.households h where h.household_id = meals_served.household_id and h.owner_user_id = auth.uid())
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='meal_components' and policyname='meal_components_owner_all') then
    create policy meal_components_owner_all on public.meal_components for all using (
      exists (
        select 1 from public.meals_served m join public.households h on h.household_id = m.household_id
        where m.meal_id = meal_components.meal_id and h.owner_user_id = auth.uid()
      )
    ) with check (
      exists (
        select 1 from public.meals_served m join public.households h on h.household_id = m.household_id
        where m.meal_id = meal_components.meal_id and h.owner_user_id = auth.uid()
      )
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='child_meal_outcomes' and policyname='child_meal_outcomes_owner_all') then
    create policy child_meal_outcomes_owner_all on public.child_meal_outcomes for all using (
      exists (
        select 1 from public.children c join public.households h on h.household_id = c.household_id
        where c.child_id = child_meal_outcomes.child_id and h.owner_user_id = auth.uid()
      )
    ) with check (
      exists (
        select 1 from public.children c join public.households h on h.household_id = c.household_id
        where c.child_id = child_meal_outcomes.child_id and h.owner_user_id = auth.uid()
      )
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='food_exposures' and policyname='food_exposures_owner_all') then
    create policy food_exposures_owner_all on public.food_exposures for all using (
      exists (
        select 1 from public.children c join public.households h on h.household_id = c.household_id
        where c.child_id = food_exposures.child_id and h.owner_user_id = auth.uid()
      )
    ) with check (
      exists (
        select 1 from public.children c join public.households h on h.household_id = c.household_id
        where c.child_id = food_exposures.child_id and h.owner_user_id = auth.uid()
      )
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='routine_signals' and policyname='routine_signals_owner_all') then
    create policy routine_signals_owner_all on public.routine_signals for all using (
      exists (select 1 from public.households h where h.household_id = routine_signals.household_id and h.owner_user_id = auth.uid())
    ) with check (
      exists (select 1 from public.households h where h.household_id = routine_signals.household_id and h.owner_user_id = auth.uid())
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='rescue_sessions' and policyname='rescue_sessions_owner_all') then
    create policy rescue_sessions_owner_all on public.rescue_sessions for all using (
      exists (select 1 from public.households h where h.household_id = rescue_sessions.household_id and h.owner_user_id = auth.uid())
    ) with check (
      exists (select 1 from public.households h where h.household_id = rescue_sessions.household_id and h.owner_user_id = auth.uid())
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='weekly_resets' and policyname='weekly_resets_owner_all') then
    create policy weekly_resets_owner_all on public.weekly_resets for all using (
      exists (select 1 from public.households h where h.household_id = weekly_resets.household_id and h.owner_user_id = auth.uid())
    ) with check (
      exists (select 1 from public.households h where h.household_id = weekly_resets.household_id and h.owner_user_id = auth.uid())
    );
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='family_meal_memory' and policyname='family_meal_memory_owner_all') then
    create policy family_meal_memory_owner_all on public.family_meal_memory for all using (
      exists (select 1 from public.households h where h.household_id = family_meal_memory.household_id and h.owner_user_id = auth.uid())
    ) with check (
      exists (select 1 from public.households h where h.household_id = family_meal_memory.household_id and h.owner_user_id = auth.uid())
    );
  end if;
end $$;

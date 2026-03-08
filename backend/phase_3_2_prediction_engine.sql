-- Phase 3.2 Prediction + Consistency Engine
-- Run in Supabase SQL editor (once)

create extension if not exists pgcrypto;

create table if not exists user_weekly_metrics (
  user_id uuid not null,
  week_start date not null,
  week_end date,
  tz_used text,
  days_tracked int not null default 0,
  days_with_data_7d int not null default 0,
  scans_7d int not null default 0,
  projection_confidence_band text,

  -- Core consistency metrics
  protein_avg numeric,
  protein_consistency numeric,
  fiber_avg numeric,
  fiber_consistency numeric,
  timing_balance_avg numeric,
  timing_volatility numeric,
  upf_avg numeric,
  upf_volatility numeric,
  glycemic_avg numeric,
  glycemic_volatility numeric,
  readiness_score numeric,
  readiness_trend numeric,
  fat_loss_velocity_score numeric,
  fat_loss_probability_7d numeric,
  projection_7d_score numeric,

  -- Full deterministic payload cache (includes internal-only fields)
  payload_hash text,
  metrics_json jsonb,
  engine_version text,
  updated_at timestamptz not null default now(),

  primary key (user_id, week_start)
);

-- Safe upgrades for existing installations
alter table if exists user_weekly_metrics add column if not exists tz_used text;
alter table if exists user_weekly_metrics add column if not exists days_with_data_7d int not null default 0;
alter table if exists user_weekly_metrics add column if not exists scans_7d int not null default 0;
alter table if exists user_weekly_metrics add column if not exists projection_confidence_band text;
alter table if exists user_weekly_metrics add column if not exists fat_loss_velocity_score numeric;
alter table if exists user_weekly_metrics add column if not exists fat_loss_probability_7d numeric;

create index if not exists idx_user_weekly_metrics_user_week
  on user_weekly_metrics(user_id, week_start desc);

create index if not exists idx_user_weekly_metrics_week_start
  on user_weekly_metrics(week_start desc);

-- RLS hardening
alter table if exists user_weekly_metrics enable row level security;

-- Keep service-role backend fully functional.
do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'user_weekly_metrics'
      and policyname = 'own_user_weekly_metrics_read'
  ) then
    create policy own_user_weekly_metrics_read
      on public.user_weekly_metrics
      for select
      using (auth.uid() = user_id);
  end if;
end $$;


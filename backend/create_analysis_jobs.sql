create table if not exists public.analysis_jobs (
  id uuid primary key,
  user_id uuid not null,
  status text not null default 'queued',
  stage text not null default 'queued',
  progress_pct int not null default 0,
  input_path text,
  result_json jsonb,
  error text,
  request_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_analysis_jobs_user_created
  on public.analysis_jobs(user_id, created_at desc);

create index if not exists idx_analysis_jobs_status_updated
  on public.analysis_jobs(status, updated_at desc);

alter table public.analysis_jobs enable row level security;

do $$ begin
  if not exists (
    select 1 from pg_policies where schemaname='public' and tablename='analysis_jobs' and policyname='analysis_jobs_read_own'
  ) then
    create policy analysis_jobs_read_own on public.analysis_jobs for select using (auth.uid() = user_id);
  end if;
end $$;

do $$ begin
  if not exists (
    select 1 from pg_policies where schemaname='public' and tablename='analysis_jobs' and policyname='analysis_jobs_insert_own'
  ) then
    create policy analysis_jobs_insert_own on public.analysis_jobs for insert with check (auth.uid() = user_id);
  end if;
end $$;

do $$ begin
  if not exists (
    select 1 from pg_policies where schemaname='public' and tablename='analysis_jobs' and policyname='analysis_jobs_update_own'
  ) then
    create policy analysis_jobs_update_own on public.analysis_jobs for update using (auth.uid() = user_id);
  end if;
end $$;

create extension if not exists pgcrypto;

create table if not exists public.alpha_system_status (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  source_as_of timestamptz,
  mode text not null,
  data_quality jsonb not null default '{}'::jsonb,
  status text not null,
  provider_health jsonb not null default '{}'::jsonb
);

create table if not exists public.alpha_market_state (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  source_as_of timestamptz,
  mode text not null,
  data_quality jsonb not null default '{}'::jsonb,
  market_status text not null,
  market_regime text not null,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists public.alpha_candidates (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  source_as_of timestamptz,
  mode text not null,
  data_quality jsonb not null default '{}'::jsonb,
  ticker text not null,
  company text,
  score numeric,
  risk_category text,
  status text,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists public.alpha_signals (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  source_as_of timestamptz,
  mode text not null,
  data_quality jsonb not null default '{}'::jsonb,
  ticker text not null,
  setup text not null,
  status text not null,
  score numeric,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists public.alpha_signal_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  source_as_of timestamptz,
  mode text not null,
  data_quality jsonb not null default '{}'::jsonb,
  signal_id uuid references public.alpha_signals(id),
  event_type text not null,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists public.alpha_daily_stats (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  source_as_of timestamptz,
  mode text not null,
  data_quality jsonb not null default '{}'::jsonb,
  trading_date date not null,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists public.alpha_paper_observations (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  source_as_of timestamptz,
  mode text not null,
  data_quality jsonb not null default '{}'::jsonb,
  ticker text not null,
  setup text,
  theoretical_entry numeric,
  stop numeric,
  target1 numeric,
  target2 numeric,
  result text,
  payload jsonb not null default '{}'::jsonb
);

alter table public.alpha_system_status enable row level security;
alter table public.alpha_market_state enable row level security;
alter table public.alpha_candidates enable row level security;
alter table public.alpha_signals enable row level security;
alter table public.alpha_signal_events enable row level security;
alter table public.alpha_daily_stats enable row level security;
alter table public.alpha_paper_observations enable row level security;

create policy "anon can read alpha system status" on public.alpha_system_status for select using (true);
create policy "anon can read alpha market state" on public.alpha_market_state for select using (true);
create policy "anon can read alpha candidates" on public.alpha_candidates for select using (true);
create policy "anon can read alpha signals" on public.alpha_signals for select using (true);
create policy "anon can read alpha signal events" on public.alpha_signal_events for select using (true);
create policy "anon can read alpha daily stats" on public.alpha_daily_stats for select using (true);
create policy "anon can read alpha paper observations" on public.alpha_paper_observations for select using (true);

-- No public INSERT/UPDATE/DELETE policies are created. GitHub Actions must use
-- a backend secret/service role key. Never expose that key in GitHub Pages.

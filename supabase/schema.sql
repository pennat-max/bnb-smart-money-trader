create extension if not exists pgcrypto;

create table if not exists public.trade_signals (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  symbol text not null default 'BNBUSDT',
  mode text not null default 'signal_only',
  signal text not null check (signal in ('LONG', 'SHORT', 'WAIT', 'CANCEL')),
  confidence integer not null check (confidence between 0 and 100),
  risk_score integer not null check (risk_score between 0 and 100),
  price numeric,
  btc_price numeric,
  entry numeric,
  take_profit numeric,
  stop_loss numeric,
  position_size numeric,
  daily_pnl_pct numeric not null default 0,
  indicators jsonb not null default '{}'::jsonb,
  detections jsonb not null default '{}'::jsonb,
  reasoning_th text not null default '',
  reasoning_en text not null default '',
  personality_log text not null default '',
  raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists trade_signals_created_at_idx
  on public.trade_signals (created_at desc);

create index if not exists trade_signals_symbol_idx
  on public.trade_signals (symbol);

alter table public.trade_signals enable row level security;

drop policy if exists "Allow signal inserts" on public.trade_signals;
create policy "Allow signal inserts"
  on public.trade_signals
  for insert
  to anon, authenticated
  with check (true);

drop policy if exists "Allow signal history reads" on public.trade_signals;
create policy "Allow signal history reads"
  on public.trade_signals
  for select
  to anon, authenticated
  using (true);

create table if not exists public.paper_trades (
  id text primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  symbol text not null default 'BNBUSDT',
  side text not null check (side in ('LONG', 'SHORT')),
  status text not null check (status in ('OPEN', 'CLOSED')),
  entry numeric not null,
  take_profit numeric not null,
  stop_loss numeric not null,
  size numeric not null default 0,
  confidence integer not null check (confidence between 0 and 100),
  opened_price numeric not null,
  current_price numeric not null,
  exit_price numeric,
  pnl_pct numeric not null default 0,
  pnl_usdt numeric not null default 0,
  outcome text not null default 'OPEN',
  reasoning_th text not null default '',
  raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists paper_trades_created_at_idx
  on public.paper_trades (created_at desc);

alter table public.paper_trades enable row level security;

drop policy if exists "Allow paper trade inserts" on public.paper_trades;
create policy "Allow paper trade inserts"
  on public.paper_trades
  for insert
  to anon, authenticated
  with check (true);

drop policy if exists "Allow paper trade reads" on public.paper_trades;
create policy "Allow paper trade reads"
  on public.paper_trades
  for select
  to anon, authenticated
  using (true);

drop policy if exists "Allow paper trade updates" on public.paper_trades;
create policy "Allow paper trade updates"
  on public.paper_trades
  for update
  to anon, authenticated
  using (true)
  with check (true);

create table if not exists public.market_snapshots (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  symbol text not null default 'BNBUSDT',
  price numeric not null,
  btc_price numeric not null,
  funding_rate numeric not null default 0,
  open_interest numeric not null default 0,
  open_interest_change_pct numeric not null default 0,
  long_short_ratio numeric not null default 1,
  taker_buy_sell_ratio numeric not null default 1,
  taker_buy_volume_ratio numeric not null default 0.5,
  bid_ask_imbalance numeric not null default 0,
  liquidation_imbalance numeric not null default 0,
  mtf_alignment_score integer not null default 0,
  detections jsonb not null default '{}'::jsonb,
  market_context jsonb not null default '{}'::jsonb,
  source text not null default 'collector'
);

alter table public.market_snapshots
  add column if not exists bid_ask_imbalance numeric not null default 0,
  add column if not exists liquidation_imbalance numeric not null default 0,
  add column if not exists mtf_alignment_score integer not null default 0,
  add column if not exists market_context jsonb not null default '{}'::jsonb;

create index if not exists market_snapshots_created_at_idx
  on public.market_snapshots (created_at desc);

create index if not exists market_snapshots_symbol_idx
  on public.market_snapshots (symbol);

alter table public.market_snapshots enable row level security;

drop policy if exists "Allow market snapshot inserts" on public.market_snapshots;
create policy "Allow market snapshot inserts"
  on public.market_snapshots
  for insert
  to anon, authenticated
  with check (true);

drop policy if exists "Allow market snapshot reads" on public.market_snapshots;
create policy "Allow market snapshot reads"
  on public.market_snapshots
  for select
  to anon, authenticated
  using (true);

create table if not exists public.candles (
  id uuid default gen_random_uuid(),
  symbol text not null,
  timeframe text not null check (timeframe in ('1m', '5m', '15m', '1h')),
  open_time bigint not null,
  close_time bigint,
  open numeric not null,
  high numeric not null,
  low numeric not null,
  close numeric not null,
  volume numeric not null,
  quote_volume numeric,
  trades_count integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (symbol, timeframe, open_time)
);

alter table public.candles
  add column if not exists id uuid default gen_random_uuid(),
  add column if not exists close_time bigint,
  add column if not exists quote_volume numeric,
  add column if not exists trades_count integer;

update public.candles
  set id = gen_random_uuid()
  where id is null;

alter table public.candles
  alter column id set not null;

create unique index if not exists candles_id_idx
  on public.candles (id);

create index if not exists candles_backtest_idx
  on public.candles (symbol, timeframe, open_time);

create index if not exists candles_backtest_desc_idx
  on public.candles (symbol, timeframe, open_time desc);

create index if not exists candles_symbol_timeframe_close_time_idx
  on public.candles (symbol, timeframe, close_time);

create or replace function public.set_candles_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists candles_set_updated_at on public.candles;
create trigger candles_set_updated_at
  before update on public.candles
  for each row
  execute function public.set_candles_updated_at();

alter table public.candles enable row level security;

drop policy if exists "Allow candle reads" on public.candles;
drop policy if exists "Allow candle upserts" on public.candles;
drop policy if exists "Allow candle updates" on public.candles;

-- Candle writes should go through the backend with SUPABASE_SERVICE_ROLE_KEY.
-- No anon insert/update policy is added so clients cannot poison backtest data.

create table if not exists public.collector_runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  collector text not null,
  status text not null check (status in ('success', 'partial', 'failed')),
  symbol text,
  timeframe text,
  rows_fetched integer not null default 0,
  rows_saved integer not null default 0,
  duration_ms integer,
  error text,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists collector_runs_created_at_idx
  on public.collector_runs (created_at desc);

create index if not exists collector_runs_collector_idx
  on public.collector_runs (collector, created_at desc);

create index if not exists collector_runs_symbol_timeframe_idx
  on public.collector_runs (symbol, timeframe, created_at desc);

alter table public.collector_runs enable row level security;

-- Collector run writes should go through the backend with SUPABASE_SERVICE_ROLE_KEY.

create table if not exists public.data_quality_checks (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  check_name text not null,
  status text not null check (status in ('pass', 'warn', 'fail')),
  symbol text,
  timeframe text,
  observed_value numeric,
  expected_value numeric,
  details jsonb not null default '{}'::jsonb
);

create index if not exists data_quality_checks_created_at_idx
  on public.data_quality_checks (created_at desc);

create index if not exists data_quality_checks_name_idx
  on public.data_quality_checks (check_name, created_at desc);

create index if not exists data_quality_checks_symbol_timeframe_idx
  on public.data_quality_checks (symbol, timeframe, created_at desc);

alter table public.data_quality_checks enable row level security;

-- Data quality check writes should go through the backend with SUPABASE_SERVICE_ROLE_KEY.

create table if not exists public.research_jobs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  status text not null check (status in ('planned', 'running', 'done', 'blocked', 'failed')) default 'planned',
  mode text not null default 'research_only',
  goal text not null,
  symbols text[] not null default array['BNBUSDT', 'BTCUSDT'],
  timeframes text[] not null default array['1m', '5m', '15m', '1h'],
  max_days integer not null default 30,
  real_trading boolean not null default false,
  auto_strategy_changes boolean not null default false,
  recommended_plan jsonb not null default '{}'::jsonb,
  summary_th text not null default '',
  error text
);

create index if not exists research_jobs_created_at_idx
  on public.research_jobs (created_at desc);

create index if not exists research_jobs_status_idx
  on public.research_jobs (status, created_at desc);

alter table public.research_jobs enable row level security;

create table if not exists public.research_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  job_id uuid references public.research_jobs(id) on delete cascade,
  step text not null,
  status text not null check (status in ('queued', 'running', 'done', 'blocked', 'warning')),
  title_th text not null,
  detail_th text not null,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists research_events_job_created_at_idx
  on public.research_events (job_id, created_at asc);

create index if not exists research_events_created_at_idx
  on public.research_events (created_at desc);

alter table public.research_events enable row level security;

-- Research writes should go through the backend with SUPABASE_SERVICE_ROLE_KEY.

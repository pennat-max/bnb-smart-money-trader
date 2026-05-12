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

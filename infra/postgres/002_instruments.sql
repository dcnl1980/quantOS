create table if not exists instruments(
  symbol text primary key,
  base text not null,
  quote text not null,
  underlying text not null,
  settlement text not null,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists instrument_listings(
  symbol text not null references instruments(symbol) on delete cascade,
  venue text not null,
  venue_symbol text not null,
  tick_size double precision not null default 0.01,
  lot_size double precision not null default 0.0001,
  min_notional double precision not null default 10,
  primary key (symbol, venue)
);

create table if not exists shadow_decisions(
  id bigserial primary key,
  opportunity_id uuid,
  symbol text not null,
  allowed boolean not null,
  reason text not null,
  approved_notional double precision not null default 0,
  execution_mode text not null default 'shadow',
  payload jsonb not null default '{}'::jsonb,
  ts timestamptz not null default now()
);

insert into instruments(symbol, base, quote, underlying, settlement) values
  ('BTCUSDT','BTC','USDT','BTC','USDT'),
  ('ETHUSDT','ETH','USDT','ETH','USDT'),
  ('SOLUSDT','SOL','USDT','SOL','USDT')
on conflict (symbol) do nothing;

insert into instrument_listings(symbol, venue, venue_symbol) values
  ('BTCUSDT','binance','BTCUSDT'),
  ('BTCUSDT','coinbase','BTC-USD'),
  ('ETHUSDT','binance','ETHUSDT'),
  ('ETHUSDT','coinbase','ETH-USD'),
  ('SOLUSDT','binance','SOLUSDT'),
  ('SOLUSDT','coinbase','SOL-USD')
on conflict do nothing;

create table if not exists experiments(
  id uuid primary key,
  name text not null,
  strategy_id text not null,
  hypothesis text not null,
  status text not null,
  params jsonb not null default '{}'::jsonb,
  dataset jsonb not null default '{}'::jsonb,
  metrics jsonb not null default '{}'::jsonb,
  artifacts jsonb not null default '{}'::jsonb,
  notes jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists experiments_status_idx on experiments(status);
create index if not exists experiments_created_idx on experiments(created_at desc);

create table if not exists feature_values(
  id bigserial primary key,
  name text not null,
  symbol text not null,
  value double precision not null,
  tags jsonb not null default '{}'::jsonb,
  ts timestamptz not null default now()
);
create index if not exists feature_values_name_symbol_ts_idx on feature_values(name, symbol, ts desc);

create table if not exists promotion_decisions(
  id bigserial primary key,
  strategy_id text not null,
  experiment_id uuid,
  stage text not null,
  approved boolean not null,
  score double precision not null,
  payload jsonb not null default '{}'::jsonb,
  ts timestamptz not null default now()
);
create index if not exists promotion_decisions_strategy_idx on promotion_decisions(strategy_id, ts desc);

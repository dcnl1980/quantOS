create table if not exists orders(
  client_order_id text primary key,
  venue_order_id text,
  venue text not null,
  symbol text not null,
  side text not null,
  quantity double precision not null,
  price double precision not null,
  filled_qty double precision not null default 0,
  avg_fill_price double precision not null default 0,
  fee double precision not null default 0,
  state text not null,
  strategy text not null,
  opportunity_id uuid,
  replaces_client_order_id text,
  replaced_by_client_order_id text,
  reject_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);
create index if not exists orders_venue_state_idx on orders(venue, state);
create index if not exists orders_updated_idx on orders(updated_at desc);

create table if not exists reconciliation_events(
  id bigserial primary key,
  ts timestamptz not null default now(),
  mismatch_count int not null default 0,
  critical_count int not null default 0,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists inventory_snapshots(
  id bigserial primary key,
  ts timestamptz not null default now(),
  venue text not null,
  symbol text not null,
  qty double precision not null,
  reserved_notional double precision not null default 0
);

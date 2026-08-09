create table if not exists opportunities(
 id uuid primary key,symbol text not null,type text not null,buy_venue text not null,sell_venue text not null,
 buy_price double precision not null,sell_price double precision not null,gross_edge_bps double precision not null,
 net_edge_bps double precision not null,confidence double precision not null,max_notional double precision not null,
 observed_at timestamptz not null,metadata jsonb not null default '{}'::jsonb
);
create index if not exists opportunities_time_idx on opportunities(observed_at desc);
create table if not exists fills(
 id uuid primary key,order_id uuid not null,venue text not null,symbol text not null,side text not null,
 quantity double precision not null,price double precision not null,fee double precision not null,
 strategy text not null,opportunity_id uuid,ts timestamptz not null
);
create index if not exists fills_time_idx on fills(ts desc);
create table if not exists audit_log(
 id bigserial primary key,ts timestamptz not null default now(),actor text not null,action text not null,
 object_type text not null,object_id text,payload jsonb not null default '{}'::jsonb
);

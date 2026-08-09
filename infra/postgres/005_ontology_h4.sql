create table if not exists ontology_nodes(
  id text primary key,
  node_type text not null,
  label text not null,
  attrs jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
create index if not exists ontology_nodes_type_idx on ontology_nodes(node_type);

create table if not exists ontology_edges(
  id bigserial primary key,
  source_id text not null,
  target_id text not null,
  edge_type text not null,
  attrs jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
create index if not exists ontology_edges_type_idx on ontology_edges(edge_type);
create index if not exists ontology_edges_source_idx on ontology_edges(source_id);
create index if not exists ontology_edges_target_idx on ontology_edges(target_id);

create table if not exists prediction_markets(
  market_id text primary key,
  question text not null,
  venue text not null,
  settlement_source text not null,
  underlying text not null,
  status text not null default 'open',
  outcomes jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists prediction_markets_venue_idx on prediction_markets(venue);
create index if not exists prediction_markets_underlying_idx on prediction_markets(underlying);

create table if not exists ontology_contradictions(
  id text primary key,
  kind text not null,
  severity text not null,
  message text not null,
  nodes jsonb not null default '[]'::jsonb,
  edges jsonb not null default '[]'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  resolved boolean not null default false,
  ts timestamptz not null default now()
);
create index if not exists ontology_contradictions_severity_idx on ontology_contradictions(severity, ts desc);
create index if not exists ontology_contradictions_kind_idx on ontology_contradictions(kind, ts desc);

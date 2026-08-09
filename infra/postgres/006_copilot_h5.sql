create table if not exists copilot_interactions(
  id bigserial primary key,
  action text not null,
  intent text,
  question text,
  payload jsonb not null default '{}'::jsonb,
  policy_allowed boolean not null default true,
  policy_reason text,
  ts timestamptz not null default now()
);
create index if not exists copilot_interactions_action_ts_idx on copilot_interactions(action, ts desc);
create index if not exists copilot_interactions_policy_idx on copilot_interactions(policy_allowed, ts desc);

create table if not exists copilot_strategy_stubs(
  stub_id text primary key,
  name text not null,
  kind text not null,
  hypothesis text not null default '',
  code text not null,
  constraints jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists copilot_strategy_stubs_kind_idx on copilot_strategy_stubs(kind);

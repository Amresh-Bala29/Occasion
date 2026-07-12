-- 0003_runtime: background run registry, webhook audit log, executable approvals.
--
-- agent_runs makes long agent work non-blocking: POST /chat and approved bookings
-- insert a `running` row, execute in the background, and settle it — clients poll
-- the row instead of holding an HTTP request open for minutes. webhook_events is a
-- durable audit of every inbound webhook (objective 19), ahead of any processor.
-- approvals.action carries the machine-readable action an approval authorizes, so
-- approving in the dashboard can trigger real execution (propose -> approve -> execute).

create table agent_runs (
    id text primary key,
    event_id text references events(id) on delete cascade,
    kind text not null,
    title text not null,
    status text not null,
    agent text,
    reason text,
    result jsonb,
    created_at timestamptz not null default now(),
    finished_at timestamptz
);

create index on agent_runs (event_id, created_at);

create table webhook_events (
    id bigint generated always as identity primary key,
    source text not null,
    payload jsonb not null default '{}',
    received_at timestamptz not null default now()
);

alter table approvals add column action jsonb;

-- Backend-internal tables, like the memory set: RLS with no policies keeps them
-- off the public PostgREST API while the postgres role bypasses it.
alter table agent_runs enable row level security;
alter table webhook_events enable row level security;

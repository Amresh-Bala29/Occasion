-- 0001_init: event workspace schema.
--
-- Mirrors services/agent/database/models.py. One `events` aggregate; every other
-- table hangs off an event (or off a task group / conversation). Child lists carry
-- an `ordinal` so reads restore the exact display order. Slugs are text primary keys
-- because the frontend routes and localStorage keys depend on them; id-less display
-- rows use a synthetic identity key that never reaches the API.

create table events (
    id text primary key,
    kind text not null,
    name text not null,
    short_name text not null,
    status_label text not null,
    event_date text not null,
    location text not null,
    headcount text not null,
    days_to_go text not null,
    percent_complete integer not null,
    total_usd integer not null,
    paid_usd integer not null,
    pending_usd integer not null,
    vendors_confirmed integer not null,
    vendors_total integer not null,
    vendors_in_progress integer not null,
    auto_approve_limit text not null,
    savings_footnote text not null
);

create table approvals (
    id text primary key,
    event_id text not null references events(id) on delete cascade,
    kind text not null,
    agent text not null,
    agent_tone text not null,
    tag text not null,
    title text not null,
    description text not null,
    amount text not null,
    vendor text not null,
    thread_id text,
    resolved boolean not null default false,
    ordinal integer not null
);

create table agent_status (
    id bigint generated always as identity primary key,
    event_id text not null references events(id) on delete cascade,
    name text not null,
    tone text not null,
    status text not null,
    ordinal integer not null
);

create table activity_items (
    id text primary key,
    event_id text not null references events(id) on delete cascade,
    agent text not null,
    tone text not null,
    time_ago text not null,
    description text not null,
    pool boolean not null default false,
    ordinal integer not null
);

create table vendors (
    id text primary key,
    event_id text not null references events(id) on delete cascade,
    initials text not null,
    name text not null,
    category text not null,
    status text not null,
    quotes integer not null,
    last_activity text not null,
    cost text not null,
    ordinal integer not null
);

create table plan_phases (
    id bigint generated always as identity primary key,
    event_id text not null references events(id) on delete cascade,
    name text not null,
    percent integer not null,
    note text not null,
    ordinal integer not null
);

create table plan_task_groups (
    id bigint generated always as identity primary key,
    event_id text not null references events(id) on delete cascade,
    name text not null,
    owner text not null,
    tone text not null,
    ordinal integer not null
);

create table plan_tasks (
    id text primary key,
    group_id bigint not null references plan_task_groups(id) on delete cascade,
    label text not null,
    done boolean not null,
    ordinal integer not null
);

create table risks (
    id bigint generated always as identity primary key,
    event_id text not null references events(id) on delete cascade,
    level text not null,
    title text not null,
    mitigation text not null,
    ordinal integer not null
);

create table milestones (
    id bigint generated always as identity primary key,
    event_id text not null references events(id) on delete cascade,
    title text not null,
    when_label text not null,
    done boolean not null,
    ordinal integer not null
);

create table budget_categories (
    id bigint generated always as identity primary key,
    event_id text not null references events(id) on delete cascade,
    name text not null,
    committed_usd integer not null,
    paid_usd integer not null,
    estimate boolean,
    ordinal integer not null
);

create table saving_suggestions (
    id bigint generated always as identity primary key,
    event_id text not null references events(id) on delete cascade,
    title text not null,
    amount text not null,
    note text not null,
    ordinal integer not null
);

create table calendar_events (
    id bigint generated always as identity primary key,
    event_id text not null references events(id) on delete cascade,
    event_date text not null,
    title text not null,
    kind text not null,
    ordinal integer not null
);

create table deadline_items (
    id text primary key,
    event_id text not null references events(id) on delete cascade,
    list_kind text not null,
    month text not null,
    day text not null,
    title text not null,
    meta text not null,
    emphasis text,
    ordinal integer not null
);

create table decisions (
    id text primary key,
    event_id text not null references events(id) on delete cascade,
    title text not null,
    amount text not null,
    when_label text not null,
    approved boolean not null,
    ordinal integer not null
);

create table spending_rules (
    id text primary key,
    event_id text not null references events(id) on delete cascade,
    label text not null,
    value text not null,
    ordinal integer not null
);

create table post_event_tasks (
    id text primary key,
    event_id text not null references events(id) on delete cascade,
    glyph text not null,
    title text not null,
    description text not null,
    state text not null,
    ordinal integer not null
);

create table conversations (
    id text primary key,
    event_id text not null references events(id) on delete cascade,
    name text not null,
    subtitle text not null,
    channel text not null,
    avatar_initials text not null,
    time_label text not null,
    preview text not null,
    unread boolean not null,
    archived boolean not null,
    quick_replies jsonb not null,
    ordinal integer not null
);

create table inbox_messages (
    id text primary key,
    conversation_id text not null references conversations(id) on delete cascade,
    author text not null,
    from_me boolean,
    day text not null,
    time_label text not null,
    body text not null,
    ordinal integer not null
);

-- Foreign-key lookup indexes for the event-scoped reads.
create index on approvals (event_id);
create index on agent_status (event_id);
create index on activity_items (event_id);
create index on vendors (event_id);
create index on plan_phases (event_id);
create index on plan_task_groups (event_id);
create index on plan_tasks (group_id);
create index on risks (event_id);
create index on milestones (event_id);
create index on budget_categories (event_id);
create index on saving_suggestions (event_id);
create index on calendar_events (event_id);
create index on deadline_items (event_id);
create index on decisions (event_id);
create index on spending_rules (event_id);
create index on post_event_tasks (event_id);
create index on conversations (event_id);
create index on inbox_messages (conversation_id);

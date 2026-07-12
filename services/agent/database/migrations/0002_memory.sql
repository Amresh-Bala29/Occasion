-- 0002_memory: agent memory schema.
--
-- Mirrors the memory rows in services/agent/database/models.py. These tables back the
-- agent fleet's memory, not the dashboard: cross-event user preferences and vendor
-- reputation, per-event working memory for resumability, and a full-text document store
-- for semantic recall. No `create extension` — semantic search uses built-in Postgres
-- full-text (to_tsvector/plainto_tsquery), so there is nothing to enable and no embeddings.

create table user_preferences (
    user_id text primary key,
    dietary_restrictions jsonb not null default '[]',
    food_preferences jsonb not null default '[]',
    entertainment_preferences jsonb not null default '[]',
    accessibility_needs jsonb not null default '[]',
    priorities jsonb not null default '[]',
    preferred_vendors jsonb not null default '[]',
    blocked_vendors jsonb not null default '[]',
    branding_notes text
);

create table vendor_reputation (
    vendor_key text primary key,
    name text not null,
    category text,
    url text,
    times_contacted integer not null default 0,
    times_quoted integer not null default 0,
    times_booked integer not null default 0,
    reliability_rating integer,
    quality_rating integer,
    history jsonb not null default '[]',
    notes text
);

create table event_memory (
    event_id text not null references events(id) on delete cascade,
    key text not null,
    value jsonb not null,
    primary key (event_id, key)
);

create table memory_documents (
    id bigint generated always as identity primary key,
    scope text not null,
    event_id text references events(id) on delete cascade,
    kind text not null,
    content text not null,
    metadata jsonb not null default '{}'
);

-- Full-text recall over document content, and a scope filter for narrowing to one event
-- or vendor. The search query builds the same to_tsvector('english', content) expression,
-- so this GIN index serves it.
create index on memory_documents using gin (to_tsvector('english', content));
create index on memory_documents (scope);
create index on vendor_reputation (category);

-- Backend-internal tables: the FastAPI service connects as the `postgres` role, which
-- bypasses RLS, so enabling RLS with no policies keeps these off the public PostgREST API
-- (matching the event-workspace tables) without affecting the backend.
alter table user_preferences enable row level security;
alter table vendor_reputation enable row level security;
alter table event_memory enable row level security;
alter table memory_documents enable row level security;

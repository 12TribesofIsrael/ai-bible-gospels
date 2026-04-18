-- AI Bible Gospels — initial Supabase schema.
-- Paste this into Supabase → SQL Editor → Run. Idempotent: safe to re-run.
--
-- What this creates:
--   profiles        — per-user profile extending auth.users (credits, name)
--   renders         — one row per paid render attempt (source of truth for billing)
--   usage_events    — raw event log (replaces usage_log.json)
--
-- Auth is handled by Supabase's built-in auth.users table — we just reference it.
-- Row-Level Security is NOT enabled yet. Service-role key (server-side) bypasses
-- RLS anyway, and until we wire up auth on the client, public reads would be blocked.
-- We'll enable RLS when user-facing auth ships.

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
    id          uuid primary key references auth.users on delete cascade,
    email       text,
    name        text,
    credits     integer not null default 5,
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- renders — canonical record of every expensive API hit
-- ---------------------------------------------------------------------------
create table if not exists public.renders (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid references auth.users on delete set null,
    ip            text,
    pipeline      text not null,                        -- 'biblical' | 'custom' | 'app'
    event         text not null,                        -- 'generate_video' | 'retry' | 'fix_scene' | ...
    model         text,
    scenes        integer,
    words         integer,
    book          text,
    chapter       integer,
    status        text not null default 'started',      -- 'started' | 'completed' | 'failed' | 'stopped'
    video_url     text,
    error         text,
    cost_usd      numeric(10,2),
    extra         jsonb,
    started_at    timestamptz not null default now(),
    completed_at  timestamptz
);

create index if not exists renders_user_started_idx on public.renders (user_id, started_at desc);
create index if not exists renders_ip_started_idx   on public.renders (ip, started_at desc);
create index if not exists renders_status_idx       on public.renders (status);

-- ---------------------------------------------------------------------------
-- usage_events — raw append-only log, replaces usage_log.json
-- ---------------------------------------------------------------------------
create table if not exists public.usage_events (
    id          bigserial primary key,
    user_id     uuid references auth.users on delete set null,
    ip          text,
    event       text not null,
    model       text,
    scenes      integer,
    words       integer,
    extra       jsonb,
    created_at  timestamptz not null default now()
);

create index if not exists usage_events_ip_created_idx   on public.usage_events (ip, created_at desc);
create index if not exists usage_events_user_created_idx on public.usage_events (user_id, created_at desc);
create index if not exists usage_events_event_idx        on public.usage_events (event);

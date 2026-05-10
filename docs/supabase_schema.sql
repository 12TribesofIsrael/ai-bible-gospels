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

-- ---------------------------------------------------------------------------
-- waitlist — beta signup capture from the marketing landing page
-- ---------------------------------------------------------------------------
create table if not exists public.waitlist (
    id          uuid primary key default gen_random_uuid(),
    email       text not null unique,
    source      text not null default 'landing-page',  -- where the signup came from
    ip          text,
    user_agent  text,
    invited_at  timestamptz,                            -- set when access link is sent
    created_at  timestamptz not null default now()
);

create index if not exists waitlist_created_at_idx on public.waitlist (created_at desc);

-- ---------------------------------------------------------------------------
-- Beta invite flow extensions (Step 4 invite + Step 5 monetize)
-- Lightweight: keeps invite redemption + paid credits on the waitlist row so
-- we don't need auth.users until full SaaS multi-tenancy ships.
-- ---------------------------------------------------------------------------
alter table public.waitlist
    add column if not exists invite_token   text unique,
    add column if not exists redeemed_at    timestamptz,
    add column if not exists chapter_picked text,
    add column if not exists render_id      uuid references public.renders(id) on delete set null,
    add column if not exists paid_credits   int     not null default 0,
    add column if not exists free_used      boolean not null default false;

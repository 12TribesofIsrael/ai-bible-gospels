# Multi-Tenant SaaS Refactor — Plan

**Status:** Not started. Deferred per user decision on 2026-04-19.
**Goal:** Turn `ai-bible-gospels` from a single-user tool into a real SaaS where 5, 50, or 500 paying users can render concurrently, each seeing only their own state, history, credits, and invoices.

This doc is a roadmap — not a spec. When we start, each phase should get its own plan file with exact file changes.

---

## Current state (what we have today)

Confirmed as of 2026-04-19 after the stop-flag fix shipped:

- **Auth** — global HTTP Basic Auth via `APP_USERNAME` + `APP_PASSWORD`. One shared login for everyone.
- **State** — module-level `pipeline_state` dict + `threading.Lock` in both [biblical_pipeline.py](../workflows/biblical-cinematic/server/biblical_pipeline.py) and [custom-script/router.py](../workflows/custom-script/router.py). One render in flight per container. Concurrent users collide.
- **Persistence** — biblical persists to `/data/pipeline_state.json`; custom-script is RAM-only. Neither is keyed by user.
- **Supabase** — schema exists in [supabase_schema.sql](./supabase_schema.sql) with `profiles`, `renders`, `usage_events`. Only `usage_events` is wired (dual-writes with JSON fallback in [usage.py](../workflows/biblical-cinematic/server/usage.py)). `profiles.credits` and the `renders` table are dead columns right now.
- **Usage tracking** — IP-keyed, not user-keyed. `user_id` param exists in `db.insert_usage_event()` but no caller supplies it.
- **Billing** — none. No Stripe, no webhooks, no checkout, no customer portal.
- **Rate limiting** — [rate_limit.py](../workflows/biblical-cinematic/server/rate_limit.py) via slowapi, scoped to IP. 5/hour on render endpoints, 30/hour on Claude-only.
- **Modal deployment** — single web function, no `max_containers` cap. Can scale horizontally under load — which today makes things *worse* because in-memory state doesn't cross container boundaries.

### Why concurrency is the gating problem

Two users clicking **Generate Video** at the same moment in the current system:

1. User A's request lands on container X, spawns a thread, writes `pipeline_state["scenes"] = [...A's scenes]`.
2. 200ms later User B's request lands on container Y (or even X). Either way, their thread writes `pipeline_state["scenes"] = [...B's scenes]`.
3. A polls `/api/status` — may hit container Y, sees B's state. Or hits container X but the dict has already been overwritten by B's thread.
4. A clicks Stop — may set the flag on a container not running any worker; A's render (on a different container) keeps going until it finishes.

Fix for stop crossed container boundaries (disk-backed flag on `/data`). Fix for pipeline_state itself was NOT done. That's Phase 1 below.

---

## Target state (what "SaaS" means here)

- Anyone can sign up with email + password. Account has its own dashboard.
- Each user sees only their own renders and history. Two users rendering at the same time don't know the other exists.
- Each user has a credit balance. Render fails fast with 402 if they're out. Usage is deducted per API call.
- Stripe checkout to top up credits or subscribe. Webhook syncs payment state. Past-due accounts auto-suspend.
- Admin can see per-user usage, revoke credits, issue refunds.
- Rate limits are per-user, not per-IP — corporate NAT doesn't throttle the whole company.

---

## Roadmap — 5 phases

Hard dependency: **1 → 2 → 3 → 4 → 5.** Don't skip or reorder. Concurrency first because auth bolted onto a single-tenant state machine still collapses under two concurrent renders.

### Phase 1 — Concurrency (per-render state) — 3-5 days

**Goal:** Multiple renders run side by side, each with its own state. No shared globals.

**Key changes:**

1. Replace module-level `pipeline_state = {...}` with a **dict keyed by `render_id`**: `pipeline_states: dict[str, dict]` — or better, a Supabase `renders` row read/written every state transition.
2. Replace module-level `stop_requested = threading.Event()` with per-render flag. Easiest: a `stopped_at` column on `renders`, checked from inside the FLUX/Kling/JSON2Video poll loops. The `/data/<kind>_stop.flag` file goes away.
3. Add `render_id` to every endpoint:
   - `POST /v9/api/generate-video` returns `{render_id: "..."}` instead of starting the One True Render
   - `GET /v9/api/status/{render_id}` (was `/api/status`)
   - `POST /v9/api/stop/{render_id}` (was `/api/stop`)
   - Same pattern for `/custom/*`
4. Move the background thread worker to **Modal `@app.function()`** jobs, one call per render. Modal already parallelizes these — no need for us to manage threads per container. The web container just enqueues, the function container runs the render.
5. Add `max_containers=10` (or whatever) to the web function in [modal_app.py](../modal_app.py) — now safe because no in-memory state is shared.

**Files to touch:** [biblical_pipeline.py](../workflows/biblical-cinematic/server/biblical_pipeline.py), [custom-script/router.py](../workflows/custom-script/router.py), [modal_app.py](../modal_app.py), HTML/JS inside [app.py](../workflows/biblical-cinematic/server/app.py) to pass `render_id` back and forth, [db.py](../workflows/biblical-cinematic/server/db.py) (new helpers for `renders` table).

**Gate to proceed:** two browsers, two accounts (or even two IPs pre-auth), both click Generate simultaneously — both see their own progress bar through to completion. No crosstalk.

### Phase 2 — Auth (Supabase Auth + JWT) — 1 week

**Goal:** Identify who's making each request. Replace Basic Auth.

**Key changes:**

1. Strip the global Basic Auth middleware in [app.py](../workflows/biblical-cinematic/server/app.py) (lines ~59-82).
2. Add Supabase Auth client-side — use `@supabase/supabase-js` in a signup/login page. Tokens go in `localStorage` or httpOnly cookie.
3. Add FastAPI dependency: `async def get_current_user(request) -> dict` — reads `Authorization: Bearer <jwt>`, verifies signature using Supabase JWT secret, returns `{user_id, email, ...}`.
4. Every `/v9/*` and `/custom/*` endpoint gets `user: dict = Depends(get_current_user)`. 401 if missing/invalid.
5. Every `renders` row gets `user_id` column. Every query scopes to `WHERE user_id = :current_user`.
6. Endpoints: `POST /auth/signup`, `POST /auth/login` (really just passthrough to Supabase), `GET /auth/me`, `POST /auth/logout`.
7. Rate limiter key changes from IP to `user_id`.

**New files:** `workflows/biblical-cinematic/server/auth.py` (the FastAPI dep), HTML signup/login pages.

**Gate to proceed:** Two distinct accounts. User A's `/history` does not show user B's renders. Unauthenticated requests return 401 on every protected endpoint.

### Phase 3 — Credits & quotas — 3-5 days

**Goal:** Enforce per-user spending limits. Start freemium tier.

**Key changes:**

1. Activate `profiles.credits` — default 100 on signup (enough for ~2 test renders).
2. Before starting a render: compute cost = `len(scenes) * $(per-scene cost for model)` + `$1.50` (JSON2Video). If `credits < cost`, return 402 Payment Required.
3. After each successful scene: atomic `UPDATE profiles SET credits = credits - <scene_cost> WHERE user_id = :u AND credits >= <scene_cost>`. If the UPDATE affects 0 rows, user was rate-limited or zeroed — abort render.
4. After JSON2Video completes: same atomic deduct.
5. Update [usage.py](../workflows/biblical-cinematic/server/usage.py) callers to pass `user_id`. Usage events become the source of truth for billing reconciliation.
6. Admin endpoint: `POST /admin/credits/{user_id}` to grant/revoke.

**Gate to proceed:** A user with 0 credits can't start a render (gets 402). Admin can grant credits. Usage events include `user_id` in every row.

### Phase 4 — Stripe billing — 1-2 weeks

**Goal:** Actually charge money.

**Key changes:**

1. Pick model: **pay-as-you-go credit packs** (simpler, matches actual cost) OR **subscription tiers** (recurring MRR, more complex). Decision needed — see "Open questions" below.
2. `POST /billing/create-checkout-session` — creates a Stripe Checkout URL for a credit pack (e.g. $10 = 500 credits, $50 = 3000 credits).
3. `POST /billing/webhook` — listens for `checkout.session.completed` and `invoice.payment_failed`. Updates `profiles.credits` and `profiles.stripe_customer_id`.
4. `GET /billing/portal` — opens Stripe Customer Portal for the logged-in user (manage cards, cancel, invoices).
5. On payment failure: flag account, block new renders until resolved.

**New files:** `workflows/biblical-cinematic/server/billing.py`.

**Gate to proceed:** Test with Stripe test mode — checkout works end-to-end, credits land in Supabase via webhook, failed payment blocks rendering.

### Phase 5 — Polish — 1 week

**Goal:** Ship-ready.

- Per-user usage dashboard (`GET /dashboard` — current credits, spend graph, render count)
- Admin panel (list users, revoke access, issue refunds)
- GDPR compliance — `POST /account/delete` purges user + renders + usage_events
- Email notifications (render complete, credits low, payment failed) via Resend or Postmark
- Terms of Service / Privacy Policy pages
- Analytics (PostHog or simple event table)

---

## Open questions (need user decisions before Phase 4)

1. **Pricing model** — credit packs vs subscription tiers vs both? Subscriptions mean MRR but require clear tier differentiation (e.g. Starter $20/mo = 10 videos, Pro $100/mo = 80 videos). Credit packs are simpler and match cost directly.
2. **Free tier** — how much free usage on signup? 1 render? 5? None (requires credit top-up first)? Affects signup friction vs abuse risk.
3. **Per-scene cost markup** — v1.6 clips cost us $0.15, v3.0 costs $0.50, o3-pro costs $2.00. Markup 2-3x? Flat markup or tiered? Determines unit economics.
4. **Branding / subdomain** — keep `tribesofisrael--ai-bible-gospels-web.modal.run` or buy a proper domain before launch? Affects Stripe setup (domain needs to be whitelisted) and Supabase redirect URLs.
5. **Admin identity** — hardcode admin email(s) in env, or add a `profiles.is_admin` flag? Env is simpler, flag scales.

---

## Non-goals (explicitly out of scope)

- **Team accounts** (multiple users sharing credits) — v2. Start with single-seat.
- **API access for programmatic use** — v2. Web UI only.
- **Self-hosted / on-prem** — not a SaaS concern.
- **Internationalization** — English only for now.
- **Advanced render features** (custom voices, custom templates, etc.) — orthogonal to SaaS plumbing.

---

## Effort estimate

| Phase | Days | Risk |
|---|---|---|
| 1. Concurrency | 3-5 | Medium — touches hot path |
| 2. Auth | 5-7 | Low — Supabase does the heavy lifting |
| 3. Credits | 3-5 | Medium — atomic deducts + race conditions |
| 4. Stripe | 7-10 | High — payment bugs are expensive |
| 5. Polish | 5-7 | Low |
| **Total** | **~4-6 weeks** | — |

Assumes one engineer full-time. Real-world with context switches: 6-8 weeks.

---

## How to start

When the user says "start phase 1":

1. Make a new plan file describing the exact file-by-file changes for Phase 1 (per-render state + Modal function worker).
2. Branch off `main` — don't do this on main. Call it `saas-phase1-concurrency`.
3. Write migration SQL for the `renders` table additions (probably needs a `status` enum, `scenes` JSON, `user_id` FK, `created_at`, `updated_at`, `stopped_at`).
4. Ship behind a feature flag at first — `ENABLE_MULTI_TENANT=false` falls through to the current single-user code. Flip the flag when Phase 1 is verified.
5. Each phase gets its own PR. Don't merge the flag-flip until the phase after it is ready — otherwise users see half-built features.

---

## Related memory

Cross-session context from past work:
- `modal_multi_container_state.md` — the in-memory-state-doesn't-cross-containers trap (stop-flag bug 2026-04-19)
- `custom_script_state_volatility.md` — custom-script doesn't persist at all; this goes away once Phase 1 moves state to Supabase
- `saas_status.md` — high-level "where are we on SaaS" snapshot; update when phases land

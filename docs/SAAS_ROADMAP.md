# SaaS Roadmap — AI Bible Gospels

Turn AI Bible Gospels from a personal tool into a paid SaaS product. Tasks ordered **smallest to biggest**.

---

## Phase 1: Quick Wins (1-2 hours each)

### 1. Rate Limiting ✓ (done 2026-04-17)
**Effort:** Small | **Why:** Prevents abuse — someone running 100 renders on your dime
- ~~Add request rate limiting to FastAPI (e.g. `slowapi` or simple in-memory counter)~~
- ~~Limit: X renders per IP per hour~~
- ~~Return 429 Too Many Requests when exceeded~~

**Shipped:** `slowapi` with IP from `X-Forwarded-For` (Modal proxy-aware).
- **5/hour** on render endpoints: `generate-video`, `retry`, `fix-scene`, `fix-scenes`, `preview-scenes`, `approve-fixes`, `/api/render/start`, `/api/generate`
- **30/hour** on Claude-only endpoints: `/api/clean`, `generate-scenes`
- Status, history, stop, and Bible-data GETs are unlimited (polled every 2s)
- 429 returns `{"error": "Rate limit exceeded (5 per 1 hour). Try again later."}`
- Shared singleton in [server/rate_limit.py](../workflows/biblical-cinematic/server/rate_limit.py)

### 2. Environment-Based API Key Isolation
**Effort:** Small | **Why:** Stop exposing your personal API keys
- Move all API keys to Modal secrets (already done for some)
- Add support for user-provided API keys (BYOK model) as an alternative to credits
- Input fields in settings: "Use your own fal.ai key", "Use your own Anthropic key"

### 3. Usage Tracking / Analytics
**Effort:** Small | **Why:** Know what's being used before you charge for it
- Log each render: timestamp, user (IP or session), model used, scene count, word count, status
- Save to a JSON file or simple SQLite on the Modal Volume
- Admin endpoint: `GET /admin/usage` to view stats

---

## Phase 2: Foundation (half day each)

### 4. Database (replace JSON files)
**Effort:** Medium | **Why:** JSON files don't scale, no queries, no concurrent access
- Options: **Supabase** (free tier, Postgres, auth built in) or **Turso** (SQLite edge)
- Tables: `users`, `renders`, `scenes`, `credits`
- Migrate `render_history.json` and `pipeline_state.json` to DB
- Supabase recommended — gives you auth + DB + realtime in one

### 5. User Accounts & Authentication
**Effort:** Medium | **Why:** Can't charge people without knowing who they are
- **Supabase Auth** (email/password + Google OAuth) or **Clerk**
- Add login/signup page
- Protect all `/api/*` endpoints with auth middleware
- Each user gets their own render history, pipeline state
- Session token stored in browser, sent with every API call

### 6. Multi-Tenancy (per-user pipeline state)
**Effort:** Medium | **Why:** Currently one global `pipeline_state` — two users overwrite each other
- Replace global `pipeline_state` dict with per-user state keyed by `user_id`
- Store in DB (not in-memory dict)
- Each user can run/stop/retry their own render independently
- This is the #1 blocker for multiple simultaneous users

---

## Phase 3: Monetization (1-2 days)

### 7. Credit System
**Effort:** Medium-Large | **Why:** Users need to pay for what they use
- Each user gets X free credits on signup (trial)
- Credits deducted per render based on: scene count x model tier
- Credit balance shown in UI header
- Pricing tiers:
  - **Free:** 1-2 test renders
  - **Basic ($X/mo):** N credits/month
  - **Pro ($X/mo):** More credits + priority rendering
  - **Pay-as-you-go:** Buy credit packs

### 8. Stripe Billing Integration
**Effort:** Large | **Why:** Accept payments
- Stripe Checkout for one-time credit packs
- Stripe Subscriptions for monthly plans
- Webhook handler: payment confirmed → add credits to user account
- Billing portal: user can manage subscription, see invoices
- Use `stripe` Python SDK

---

## Phase 4: Scale & Polish (1-2 days each)

### 9. Render Queue System
**Effort:** Large | **Why:** One render at a time doesn't work for multiple users
- Options: **Modal Queue**, **Redis + Celery**, or **simple DB-based queue**
- Each render request goes into a queue with priority
- Worker processes renders sequentially (or parallel with multiple Modal containers)
- User sees queue position: "Your render is #3 in queue"
- Paid users get priority

### 10. Landing Page & Marketing Site
**Effort:** Medium | **Why:** Need a front door before the app
- Landing page with demo video, pricing, CTA
- Separate from the app (could be a simple static site or Next.js)
- SEO: target "AI Bible video generator", "KJV scripture video maker"
- Show sample output videos

### 11. Custom Domain & Branding
**Effort:** Small-Medium | **Why:** `tribesofisrael--ai-bible-gospels-web.modal.run` isn't a brand
- Get a domain (e.g. `aibiblegospels.com`)
- Point to Modal via custom domain config
- SSL auto-handled by Modal

---

## Recommended Order to Build

| # | Task | Effort | Unlocks |
|---|---|---|---|
| 1 | Rate Limiting | 1 hr | Safe to share URL publicly |
| 2 | Usage Tracking | 1 hr | Know your costs per user |
| 3 | Supabase DB | 3 hrs | Foundation for everything else |
| 4 | User Auth | 3 hrs | Know who's who |
| 5 | Multi-Tenancy | 4 hrs | Multiple users at once |
| 6 | Credit System | 6 hrs | Usage limits |
| 7 | Stripe Billing | 8 hrs | **Revenue** |
| 8 | Render Queue | 8 hrs | Scale beyond 1 concurrent user |
| 9 | Landing Page | 4 hrs | Marketing & signups |
| 10 | Custom Domain | 1 hr | Professional look |

**Start with 1-5 (foundation), then 6-7 (money), then 8-10 (scale).**

---

## Tech Stack Recommendation

| Layer | Current | SaaS |
|---|---|---|
| Frontend | Inline HTML in FastAPI | Keep (works fine) or migrate to Next.js later |
| Backend | FastAPI + threads | Keep FastAPI, add auth middleware |
| Database | JSON files | **Supabase** (Postgres + Auth + Realtime) |
| Payments | None | **Stripe** |
| Queue | None | Modal Queue or Redis |
| Hosting | Modal | Keep Modal |
| Domain | Modal subdomain | Custom domain |

---

*Created: 2026-04-05 | Version: v12*

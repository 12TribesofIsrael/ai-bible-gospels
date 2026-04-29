# Cloudflare Worker — anointed.app proxy

Reverse proxy that fronts the Modal app (`tribesofisrael--ai-bible-gospels-web.modal.run`) at `https://anointed.app` and `https://www.anointed.app`.

## Why this exists

Modal's Custom Domains feature is gated behind a paid plan. This account is on Starter. Cloudflare Workers Free tier handles the same job at $0 — TLS termination at the edge with Cloudflare's cert for `anointed.app`, then forwards to Modal over HTTPS.

A direct DNS CNAME from `anointed.app` to `*.modal.run` would fail the browser SSL handshake (Modal's cert is `*.modal.run`, not `anointed.app`), which is why a Worker is needed instead of a plain DNS record.

## Architecture

```
Browser → anointed.app (Cloudflare edge, TLS terminated)
       → anointed-proxy Worker (rewrites Host)
       → tribesofisrael--ai-bible-gospels-web.modal.run (Modal origin)
```

DNS records on the `anointed.app` zone (both Proxied / orange cloud):
- `A anointed.app → 192.0.2.1` — placeholder; the Worker route intercepts before any origin hit
- `CNAME www → anointed.app`

Worker routes:
- `anointed.app/*`
- `www.anointed.app/*`

## Redeploy

```bash
cd ops/cloudflare-proxy
npx wrangler deploy
```

First time on a machine: `npx wrangler login` (OAuth, opens browser).

## Files

- `worker.js` — the proxy itself, ~12 lines
- `wrangler.toml` — worker name, routes, compatibility date

## Smoke test

```bash
curl -v --ssl-no-revoke https://anointed.app/
# Expect: 200 OK with Modal app HTML, or 401 Basic Auth challenge if APP_USERNAME/APP_PASSWORD set
```

## Notes for future you

- `redirect: 'manual'` in `worker.js` is deliberate — passes Modal's 3xx Basic Auth challenges through to the browser instead of the Worker following them internally.
- The `workers.dev` URL (`anointed-proxy.ai-bible-gospels.workers.dev`) was disabled when routes were added. Add `workers_dev = true` to `wrangler.toml` and redeploy if you want it back as a fallback.
- Basic auth, the `/v9/api/status` polling at 2s intervals, and the JSON2Video/fal.ai download URLs all pass through cleanly — no special handling needed.

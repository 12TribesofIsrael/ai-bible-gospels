"""
Supabase integration — singleton client + helper queries.

Gated by SUPABASE_URL + SUPABASE_SECRET_KEY env vars. If either is missing,
is_enabled() returns False and every helper becomes a no-op. This lets the
app run identically to pre-Supabase state when DB is unconfigured.

All helpers swallow exceptions — a DB outage must never break a render.
"""
import os
import secrets
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

_client = None
_client_init_tried = False


def is_enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SECRET_KEY"))


print(f"[db] is_enabled={is_enabled()}")


def _get_client():
    """Lazy-init singleton. Returns None if not configured or import fails."""
    global _client, _client_init_tried
    if _client is not None:
        return _client
    if _client_init_tried:
        return None
    _client_init_tried = True

    if not is_enabled():
        return None

    try:
        from supabase import create_client
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SECRET_KEY"],
        )
        return _client
    except Exception as e:
        print(f"[db] Supabase init failed: {e}")
        return None


def insert_usage_event(ip: str, event: str, user_id: Optional[str] = None, **fields) -> None:
    """Best-effort insert into usage_events. Swallows all errors."""
    client = _get_client()
    if client is None:
        return
    try:
        row = {"ip": ip, "event": event}
        if user_id:
            row["user_id"] = user_id
        for key in ("model", "scenes", "words"):
            if fields.get(key) is not None:
                row[key] = fields.pop(key)
        if fields:
            row["extra"] = fields
        client.table("usage_events").insert(row).execute()
    except Exception as e:
        print(f"[db] insert_usage_event failed: {e}")


def insert_waitlist(email: str, ip: Optional[str] = None, user_agent: Optional[str] = None,
                     source: str = "landing-page") -> str:
    """Insert a waitlist signup. Returns 'inserted', 'duplicate', 'unconfigured', or 'error'.

    Idempotent on email — duplicate inserts are detected and reported, not raised.
    """
    client = _get_client()
    if client is None:
        return "unconfigured"
    try:
        row = {"email": email.lower().strip(), "source": source}
        if ip:
            row["ip"] = ip
        if user_agent:
            row["user_agent"] = user_agent
        client.table("waitlist").insert(row).execute()
        return "inserted"
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "23505" in msg or "unique" in msg:
            return "duplicate"
        print(f"[db] insert_waitlist failed: {e}")
        return "error"


def list_waitlist(limit: int = 500) -> Optional[list]:
    """Return all waitlist signups (newest first). None if DB unreachable."""
    client = _get_client()
    if client is None:
        return None
    try:
        resp = (client.table("waitlist")
                .select("email,source,created_at,invited_at,ip")
                .order("created_at", desc=True)
                .limit(limit)
                .execute())
        return resp.data or []
    except Exception as e:
        print(f"[db] list_waitlist failed: {e}")
        return None


def issue_invite(email: str) -> Optional[str]:
    """Generate a one-time invite_token for the waitlist row matching email.

    Idempotent: if the row already has an unredeemed token, return that one
    instead of regenerating — prevents accidental double-emails. Returns None
    if Supabase is not configured or no waitlist row exists for the email.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        normalized = email.lower().strip()
        resp = (client.table("waitlist")
                .select("invite_token,redeemed_at")
                .eq("email", normalized)
                .limit(1)
                .execute())
        rows = resp.data or []
        if not rows:
            print(f"[db] issue_invite: no waitlist row for {email}")
            return None
        existing = rows[0]
        if existing.get("invite_token") and not existing.get("redeemed_at"):
            return existing["invite_token"]
        token = secrets.token_urlsafe(24)
        (client.table("waitlist")
         .update({
             "invite_token": token,
             "invited_at": datetime.now(timezone.utc).isoformat(),
         })
         .eq("email", normalized)
         .execute())
        return token
    except Exception as e:
        print(f"[db] issue_invite failed: {e}")
        return None


def get_invite(token: str) -> Optional[dict]:
    """Look up the waitlist row by invite_token. Returns the full row dict
    (email, redeemed_at, chapter_picked, free_used, paid_credits, render_id, ...)
    or None if no match / not configured."""
    client = _get_client()
    if client is None:
        return None
    try:
        resp = (client.table("waitlist")
                .select("*")
                .eq("invite_token", token)
                .limit(1)
                .execute())
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[db] get_invite failed: {e}")
        return None


def redeem_invite(token: str, chapter_picked: str) -> str:
    """Mark the invite redeemed + store the chapter pick.

    Returns 'redeemed' (first-time, ok to start render),
            'already'  (token redeemed before; existing render_id can be reused),
            'invalid'  (no row with that token),
            'unconfigured' (Supabase not wired up).
    """
    client = _get_client()
    if client is None:
        return "unconfigured"
    try:
        row = get_invite(token)
        if row is None:
            return "invalid"
        if row.get("redeemed_at"):
            return "already"
        (client.table("waitlist")
         .update({
             "redeemed_at": datetime.now(timezone.utc).isoformat(),
             "chapter_picked": chapter_picked,
         })
         .eq("invite_token", token)
         .execute())
        return "redeemed"
    except Exception as e:
        print(f"[db] redeem_invite failed: {e}")
        return "invalid"


def attach_render(token: str, render_id: str) -> bool:
    """Link a render_id to the invite row and mark free_used=true.
    Called when the free chapter render actually starts."""
    client = _get_client()
    if client is None:
        return False
    try:
        (client.table("waitlist")
         .update({
             "render_id": render_id,
             "free_used": True,
         })
         .eq("invite_token", token)
         .execute())
        return True
    except Exception as e:
        print(f"[db] attach_render failed: {e}")
        return False


def get_render(render_id: str) -> Optional[dict]:
    """Look up a renders row by id. Returns the full row dict or None.
    Used by the 'send video-ready email' admin flow to auto-pull video_url
    when the admin doesn't paste one explicitly."""
    client = _get_client()
    if client is None or not render_id:
        return None
    try:
        resp = (client.table("renders")
                .select("*")
                .eq("id", render_id)
                .limit(1)
                .execute())
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[db] get_render failed: {e}")
        return None


def add_paid_credits(email: str, credits: int) -> bool:
    """Increment paid_credits for the waitlist row by email match.
    Called from the Stripe webhook after a $25 (1) or $50 (3) purchase.

    Read-then-write — not strictly atomic. Good enough since Stripe webhooks
    for the same email don't normally race; if it becomes a problem, swap to
    a Postgres RPC `increment_paid_credits(email, n)` for atomic UPDATE.
    """
    client = _get_client()
    if client is None:
        return False
    try:
        normalized = email.lower().strip()
        resp = (client.table("waitlist")
                .select("paid_credits")
                .eq("email", normalized)
                .limit(1)
                .execute())
        rows = resp.data or []
        if not rows:
            print(f"[db] add_paid_credits: no waitlist row for {email}")
            return False
        new_credits = (rows[0].get("paid_credits") or 0) + credits
        (client.table("waitlist")
         .update({"paid_credits": new_credits})
         .eq("email", normalized)
         .execute())
        return True
    except Exception as e:
        print(f"[db] add_paid_credits failed: {e}")
        return False


def query_usage_summary(recent_limit: int = 50) -> Optional[dict]:
    """Return same dict shape as usage.get_summary(), sourced from Supabase.

    Returns None when the DB is unreachable or the query fails so callers
    know to fall back to JSON. An empty-but-reachable DB returns a valid
    dict with total_events=0 and source='supabase'.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.table("usage_events").select("*").order("created_at", desc=True).limit(5000).execute()
        rows = resp.data or []
    except Exception as e:
        print(f"[db] query_usage_summary failed: {e}")
        return None

    by_event = Counter(r.get("event", "unknown") for r in rows)
    by_model = Counter(r["model"] for r in rows if r.get("model"))
    by_ip = Counter(r.get("ip", "unknown") for r in rows).most_common(20)

    return {
        "total_events": len(rows),
        "unique_ips": len({r.get("ip") for r in rows}),
        "by_event": dict(by_event),
        "by_model": dict(by_model),
        "by_ip": dict(by_ip),
        "recent": rows[:recent_limit],
        "source": "supabase",
    }

"""
Supabase integration — singleton client + helper queries.

Gated by SUPABASE_URL + SUPABASE_SECRET_KEY env vars. If either is missing,
is_enabled() returns False and every helper becomes a no-op. This lets the
app run identically to pre-Supabase state when DB is unconfigured.

All helpers swallow exceptions — a DB outage must never break a render.
"""
import os
from collections import Counter
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

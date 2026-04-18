"""
Usage tracking — logs one event per money-spending API hit.

Dual-write: JSON file (always, reliable fallback) + Supabase (when configured).
Reads prefer Supabase when enabled, fall back to the JSON file otherwise.

JSON file lives at /data/usage_log.json on Modal (Volume-backed) or next to
the server in dev. Supabase is gated by SUPABASE_URL + SUPABASE_SECRET_KEY.

Never raises — tracking must not break a render.
"""
import json
import threading
import time
from collections import Counter
from pathlib import Path

from fastapi import Request

import db

# Modal mounts the Volume at /data; fall back to local file in dev.
_MODAL_DATA = Path("/data")
USAGE_FILE = (_MODAL_DATA if _MODAL_DATA.exists() else Path(__file__).parent) / "usage_log.json"

_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _load() -> list:
    if not USAGE_FILE.exists():
        return []
    try:
        return json.loads(USAGE_FILE.read_text())
    except Exception:
        return []


def _save(log: list) -> None:
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(log, indent=2))


def log_event(request: Request, event: str, **fields) -> None:
    """Append one usage event to JSON (primary) and Supabase (best-effort).

    Swallows all errors — never break a render.
    """
    ip = _client_ip(request)
    clean_fields = {k: v for k, v in fields.items() if v is not None}

    try:
        entry = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ip": ip,
            "event": event,
            **clean_fields,
        }
        with _lock:
            log = _load()
            log.append(entry)
            _save(log)
    except Exception as e:
        print(f"[usage] JSON log failed: {e}")

    db.insert_usage_event(ip, event, **clean_fields)


def get_summary(recent_limit: int = 50) -> dict:
    """Stats for /admin/usage. Prefers Supabase when configured, JSON otherwise."""
    if db.is_enabled():
        summary = db.query_usage_summary(recent_limit=recent_limit)
        if summary.get("total_events", 0) > 0 or summary.get("source") == "supabase":
            return summary
        # DB is enabled but empty or failed — fall through to JSON as safety net.

    with _lock:
        log = _load()

    if not log:
        return {"total_events": 0, "unique_ips": 0, "by_event": {}, "by_model": {}, "by_ip": {}, "recent": [], "source": "json"}

    return {
        "total_events": len(log),
        "unique_ips": len({e.get("ip") for e in log}),
        "by_event": dict(Counter(e.get("event", "unknown") for e in log)),
        "by_model": dict(Counter(e["model"] for e in log if e.get("model"))),
        "by_ip": dict(Counter(e.get("ip", "unknown") for e in log).most_common(20)),
        "recent": log[-recent_limit:][::-1],
        "source": "json",
    }

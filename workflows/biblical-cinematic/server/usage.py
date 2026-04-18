"""
Usage tracking — logs one event per money-spending API hit.

Writes to /data/usage_log.json on Modal (Volume-backed, survives restarts).
Falls back to a local file next to the server in dev.

Usage pattern in an endpoint:
    from usage import log_event
    log_event(request, "biblical_generate_video", model=body.model, scenes=len(body.scenes))

Never raises — tracking must not break a render.
"""
import json
import threading
import time
from collections import Counter
from pathlib import Path

from fastapi import Request

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
    """Append one usage event. Swallows all errors — never break a render."""
    try:
        entry = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ip": _client_ip(request),
            "event": event,
            **{k: v for k, v in fields.items() if v is not None},
        }
        with _lock:
            log = _load()
            log.append(entry)
            _save(log)
    except Exception as e:
        print(f"[usage] log failed: {e}")


def get_summary(recent_limit: int = 50) -> dict:
    """Stats for /admin/usage."""
    with _lock:
        log = _load()

    if not log:
        return {"total_events": 0, "unique_ips": 0, "by_event": {}, "by_model": {}, "recent": []}

    return {
        "total_events": len(log),
        "unique_ips": len({e.get("ip") for e in log}),
        "by_event": dict(Counter(e.get("event", "unknown") for e in log)),
        "by_model": dict(Counter(e["model"] for e in log if e.get("model"))),
        "by_ip": dict(Counter(e.get("ip", "unknown") for e in log).most_common(20)),
        "recent": log[-recent_limit:][::-1],
    }

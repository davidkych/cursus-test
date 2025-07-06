# ── src/scheduler_fapp/utils.py ───────────────────────────────────────
"""
Shared helpers for the Durable-scheduler Function-App.

July 2025 · r12
────────────────
* `http.call` is now **generic** – supports any HTTP verb, headers,
  and bodies, so the scheduler can hit *any* API (inside or outside
  Azure).
* All prompt handlers are **fire-and-forget**: no exception will
  propagate back to the orchestrator.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import logging
import os
import time
import requests

# ── constants ────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    _HKT = ZoneInfo("Asia/Hong_Kong")
except Exception:                  # pragma: no cover
    logging.warning("tzdata ‘Asia/Hong_Kong’ missing – fallback UTC+8")
    _HKT = timezone(timedelta(hours=8), name="HKT")

_MIN_LEAD      = 60                      # sec – must schedule ≥ 1 min ahead
_RETRY_DELAYS  = (1, 2, 4)               # sec – best-effort retries for log
_HTTP_TIMEOUT  = 10                      # default timeout for outbound calls

# ── time helpers ─────────────────────────────────────────────────────
def to_utc_iso(ts: str) -> str:
    """Normalise any ISO-8601 ts → **UTC-aware** ISO string (+00:00)."""
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError as exc:
        raise ValueError("`exec_at` must be ISO-8601 (YYYY-MM-DDThh:mm[:ss])") from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_HKT)         # assume HKT if naïve
    else:
        dt = dt.astimezone(_HKT)

    utc = dt.astimezone(timezone.utc)
    delta = (utc - datetime.now(timezone.utc)).total_seconds()
    if delta < _MIN_LEAD:
        raise ValueError(f"`exec_at` must be ≥ {_MIN_LEAD} s in the future (Δ={delta:.1f}s)")
    return utc.isoformat(timespec="seconds")

# Back-compat alias
parse_hkt_to_utc = to_utc_iso

# ── base URL helper ──────────────────────────────────────────────────
def _internal_base() -> str:
    if (base := os.getenv("WEBAPP_BASE_URL")):
        return base.rstrip("/")
    if (site := os.getenv("FASTAPI_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    if (site := os.getenv("WEBAPP_SITE_NAME") or os.getenv("WEBSITE_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    return "http://localhost:8000"

# ── light-weight Log API helper ──────────────────────────────────────
def log_to_api(level: str, message: str,
               secondary_tag: str = "scheduler", tertiary_tag: str | None = None):
    url = f"{_internal_base()}/api/log"
    payload = {
        "tag": secondary_tag,
        "tertiary_tag": tertiary_tag,
        "base": level,
        "message": message,
    }
    try:
        requests.post(url, json=payload, timeout=_HTTP_TIMEOUT).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logging.warning("Log API call failed: %s", exc)

# ── prompt handlers ─────────────────────────────────────────────────
def _log_append(payload: dict):
    """
    Fire-and-forget proxy to `/api/log` inside the FastAPI app.
    Never raises – returns a minimal result on failure.
    """
    url = f"{_internal_base()}/api/log"
    for attempt, delay in enumerate(_RETRY_DELAYS, 1):
        try:
            resp = requests.post(url, json=payload, timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"status": "ok"}
        except Exception as exc:  # noqa: BLE001
            logging.warning("log.append attempt %s failed: %s", attempt, exc)
            time.sleep(delay)
    logging.error("log.append failed after retries – giving up")
    return {"status": "log_failed"}

def _http_call(payload: dict):
    """
    **Generic** HTTP caller – supports any verb, headers, body, timeout.

    Expected keys in *payload*  (required → ★):
      ★ url:      str
        method:   str  (default POST)
        headers:  dict
        body:     any  ( JSON serialised if dict/list )
        timeout:  int | float  (default 10 s)

    Always returns a short summary – never raises.
    """
    try:
        url     = payload["url"]
        method  = payload.get("method", "POST").upper()
        headers = payload.get("headers", {})
        body    = payload.get("body", None)
        timeout = payload.get("timeout", _HTTP_TIMEOUT)

        kwargs = {"headers": headers, "timeout": timeout}
        if method in ("GET", "DELETE", "HEAD", "OPTIONS"):
            resp = requests.request(method, url, **kwargs)
        else:
            if isinstance(body, (dict, list)):
                resp = requests.request(method, url, json=body, **kwargs)
            else:
                resp = requests.request(method, url, data=body, **kwargs)

        return {"status_code": resp.status_code, "ok": resp.ok}

    except Exception as exc:  # noqa: BLE001
        logging.warning("http.call to %s failed: %s", payload.get("url"), exc)
        return {"status": "failed", "error": str(exc)}

# dispatch table -------------------------------------------------------
PROMPTS: dict[str, callable[[dict], object]] = {
    "log.append": _log_append,
    "http.call":  _http_call,
}

def execute_prompt(prompt_type: str, payload: dict):
    """Dispatch without throwing – every handler must swallow its own errors."""
    handler = PROMPTS.get(prompt_type)
    if handler is None:
        return {"status": "failed", "error": f"Unknown prompt_type '{prompt_type}'"}
    return handler(payload)

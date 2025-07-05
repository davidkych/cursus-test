"""
Shared helpers for the Durable-scheduler Function-App.
Keeps business logic out of the individual Azure Functions.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import logging
import os
import requests

# ── constants ────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    _HKT = ZoneInfo("Asia/Hong_Kong")
except Exception:                  # pragma: no cover
    logging.warning("tzdata for 'Asia/Hong_Kong' not found – "
                    "falling back to fixed UTC+8 offset")
    _HKT = timezone(timedelta(hours=8), name="HKT")

_MIN_LEAD = 60   # seconds – must schedule ≥ 1 min ahead


# ── time helpers ─────────────────────────────────────────────────────
def parse_hkt_to_utc(exec_at_str: str) -> str:
    """
    Convert a *naive* ISO-8601 string (assumed HKT) into a **UTC-aware**
    ISO string **retaining its “+00:00” offset**.

    The Durable Functions runtime requires a timezone-aware timestamp;
    removing the offset will cause `create_timer()` never to fire.
    """
    try:
        hkt_dt = datetime.fromisoformat(exec_at_str)           # naive
    except ValueError as exc:
        raise ValueError("`exec_at` must be an ISO-8601 datetime "
                         "(YYYY-MM-DDThh:mm)") from exc

    # attach HKT zone and convert to UTC (still tz-aware here)
    if hkt_dt.tzinfo is None:
        hkt_dt = hkt_dt.replace(tzinfo=_HKT)
    else:
        hkt_dt = hkt_dt.astimezone(_HKT)

    utc_dt = hkt_dt.astimezone(timezone.utc)                   # tz-aware UTC

    now_utc = datetime.now(timezone.utc)                       # tz-aware UTC
    if (utc_dt - now_utc).total_seconds() < _MIN_LEAD:
        raise ValueError("`exec_at` must be at least 60 seconds in the future")

    # keep “+00:00” offset so that downstream code sees an **aware** value
    return utc_dt.isoformat(timespec="seconds")


# ── infrastructure helpers ──────────────────────────────────────────
def _internal_base() -> str:
    """
    Resolve the FastAPI base URL.

    Order of precedence:
    1. `WEBAPP_BASE_URL`
    2. `FASTAPI_SITE_NAME`
    3. `WEBAPP_SITE_NAME` / `WEBSITE_SITE_NAME`
    4. localhost
    """
    if (base := os.getenv("WEBAPP_BASE_URL")):
        return base.rstrip("/")

    if (site := os.getenv("FASTAPI_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"

    if (site := os.getenv("WEBAPP_SITE_NAME") or os.getenv("WEBSITE_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"

    return "http://localhost:8000"


# ── logging helper ──────────────────────────────────────────────────
def log_to_api(level: str,
               message: str,
               secondary_tag: str = "scheduler",
               tertiary_tag: str | None = None):
    """
    Fire-and-forget wrapper around the existing `/api/log` endpoint.

    Never raises – errors are logged but don’t break the scheduler.
    """
    url = f"{_internal_base()}/api/log"
    payload = {
        "tag":           secondary_tag,
        "tertiary_tag":  tertiary_tag,
        "base":          level,
        "message":       message,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as exc:                       # noqa: BLE001
        logging.warning("Log API call failed: %s", exc)


# ── prompt dispatch table ────────────────────────────────────────────
def _log_append(payload: dict):
    """Simply proxies to the Log API (best-effort)."""
    url = f"{_internal_base()}/api/log"
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


PROMPTS: dict[str, callable[[dict], object]] = {
    "log.append": _log_append,
    "http.call":  lambda p: requests.post(
        p["url"],
        json=p.get("body"),
        timeout=p.get("timeout", 10)
    ).json(),
}


def execute_prompt(prompt_type: str, payload: dict):
    """
    Execute the requested prompt and return whatever the handler returns.
    Raises ValueError for unknown `prompt_type`.
    """
    try:
        handler = PROMPTS[prompt_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported prompt_type '{prompt_type}'") from exc

    return handler(payload)

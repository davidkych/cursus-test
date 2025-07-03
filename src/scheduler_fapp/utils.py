"""
Shared helpers for the Durable-scheduler Function-App.
Keeps business logic out of the individual Azure Functions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os, requests, logging

# ── constants ────────────────────────────────────────────────────────
_HKT = ZoneInfo("Asia/Hong_Kong")        # Hong Kong Time (UTC+8)
_MIN_LEAD = 60                           # seconds – must schedule ≥ 1 min ahead

# ── time helpers ─────────────────────────────────────────────────────
def parse_hkt_to_utc(exec_at_str: str) -> str:
    """
    Convert a naive ISO-8601 string (assumed HKT) into a UTC ISO string.
    Raises ValueError on bad format or if < 60 s in the future.
    """
    try:
        hkt_dt = datetime.fromisoformat(exec_at_str)
    except ValueError as exc:
        raise ValueError("`exec_at` must be an ISO-8601 datetime (YYYY-MM-DDThh:mm)") from exc

    if hkt_dt.tzinfo is None:
        hkt_dt = hkt_dt.replace(tzinfo=_HKT)
    else:
        # Always force HKT (design decision #4)
        hkt_dt = hkt_dt.astimezone(_HKT)

    utc_dt = hkt_dt.astimezone(timezone.utc)
    if (utc_dt - datetime.now(timezone.utc)).total_seconds() < _MIN_LEAD:
        raise ValueError("`exec_at` must be at least 60 seconds in the future")

    return utc_dt.isoformat(timespec="seconds")

# ── infrastructure helpers ──────────────────────────────────────────
def _internal_base() -> str:
    """
    Resolve the FastAPI base URL.

    1.  Set `WEBAPP_BASE_URL` in app-settings (recommended).
    2.  Else fall back to https://<WEBAPP_SITE_NAME>.azurewebsites.net
    3.  Else localhost (dev / tests).
    """
    if (base := os.getenv("WEBAPP_BASE_URL")):
        return base.rstrip("/")
    if (site := os.getenv("WEBAPP_SITE_NAME") or os.getenv("WEBSITE_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    return "http://localhost:8000"

def log_to_api(level: str, message: str,
               secondary_tag: str = "scheduler", tertiary_tag: str | None = None):
    """
    Fire-and-forget wrapper around the existing /api/log endpoint.
    Never throws – errors are logged but don’t break the scheduler.
    """
    url = f"{_internal_base()}/api/log"
    payload = {
        "tag":            secondary_tag,
        "tertiary_tag":   tertiary_tag,
        "base":           level,
        "message":        message,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as exc:            # noqa: BLE001
        logging.warning("Log API call failed: %s", exc)

# ── prompt dispatch table ────────────────────────────────────────────
def _log_append(payload: dict):
    """Simply proxies to the Log API."""
    url = f"{_internal_base()}/api/log"
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()

PROMPTS: dict[str, callable[[dict], object]] = {
    "log.append": _log_append,
    "http.call":  lambda p: requests.post(p["url"],
                                          json=p.get("body"),
                                          timeout=p.get("timeout", 10)).json(),
}

def execute_prompt(prompt_type: str, payload: dict):
    """
    Execute the requested prompt and return whatever the handler returns.
    Raises ValueError for unknown prompt types.
    """
    try:
        handler = PROMPTS[prompt_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported prompt_type '{prompt_type}'") from exc

    return handler(payload)

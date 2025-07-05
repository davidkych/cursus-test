# ── src/scheduler_fapp/utils.py ───────────────────────────────────────
"""
Shared helpers for the Durable-scheduler Function-App.
Keeps business logic out of the individual Azure Functions.

Key change (July 2025):
    • `parse_hkt_to_utc` now returns a **timezone-aware UTC string**
      (e.g. “2025-07-05T16:59:53+00:00”) instead of a naïve one.
      Durable-Functions Python ≥1.2.x requires aware values for timers.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import logging
import os
import requests

# ── constants ────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo          # Python 3.9+
    _HKT = ZoneInfo("Asia/Hong_Kong")
except Exception:                          # pragma: no cover
    logging.warning(
        "tzdata for 'Asia/Hong_Kong' not found – "
        "falling back to fixed UTC+8 offset"
    )
    _HKT = timezone(timedelta(hours=8), name="HKT")

_MIN_LEAD = 60          # seconds – must schedule ≥ 1 min ahead

# ── time helpers ─────────────────────────────────────────────────────
def parse_hkt_to_utc(exec_at_str: str) -> str:
    """
    Convert an ISO-8601 **HKT** timestamp into a **timezone-aware UTC string**.

    Durable-Functions Python 1.2.x requires *aware* datetimes for `create_timer`.
    We therefore **keep** the “+00:00” offset in the returned string.

    Raises
    ------
    ValueError
        • If the string is not ISO-8601  
        • If the requested time is less than 60 s in the future (UTC)
    """
    try:
        hkt_dt = datetime.fromisoformat(exec_at_str)           # naïve or aware
    except ValueError as exc:
        raise ValueError("`exec_at` must be an ISO-8601 datetime "
                         "(YYYY-MM-DDThh:mm)") from exc

    # attach HKT zone then convert to aware UTC ------------------------------
    if hkt_dt.tzinfo is None:
        hkt_dt = hkt_dt.replace(tzinfo=_HKT)
    else:
        hkt_dt = hkt_dt.astimezone(_HKT)

    utc_dt_aware = hkt_dt.astimezone(timezone.utc)

    # ── stricter validation --------------------------------------------------
    delta = (utc_dt_aware - datetime.now(timezone.utc)).total_seconds()
    if delta <= _MIN_LEAD:
        raise ValueError(
            f"`exec_at` must be at least {_MIN_LEAD} s in the future "
            f"(Δ={delta:.1f}s)"
        )

    # keep seconds precision **with offset**
    return utc_dt_aware.isoformat(timespec="seconds")

# ── infrastructure helpers ──────────────────────────────────────────
def _internal_base() -> str:
    """
    Resolve the FastAPI base URL.

    Precedence:
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
        requests.post(url, json=payload, timeout=10).raise_for_status()
    except Exception as exc:                       # noqa: BLE001
        logging.warning("Log API call failed: %s", exc)

# ── prompt dispatch table ────────────────────────────────────────────
def _log_append(payload: dict):
    """Proxy to the Log API (best-effort)."""
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
    """Dispatch to the requested prompt handler."""
    try:
        handler = PROMPTS[prompt_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported prompt_type '{prompt_type}'") from exc
    return handler(payload)

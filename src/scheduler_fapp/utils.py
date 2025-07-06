# ── src/scheduler_fapp/utils.py ───────────────────────────────────────
"""
Shared helpers for the Durable-scheduler Function-App.
Keeps business logic out of the individual Azure Functions.

Key change (July 2025)
──────────────────────
All internal code now works exclusively with **UTC-aware ISO strings**
(e.g. “2025-07-05T16:59:53+00:00”).  
`to_utc_iso()` is the single normaliser; the previous
`parse_hkt_to_utc()` remains as a thin alias for back-compat.
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
    logging.warning(
        "tzdata for 'Asia/Hong_Kong' not found – "
        "falling back to fixed UTC+8 offset"
    )
    _HKT = timezone(timedelta(hours=8), name="HKT")

_MIN_LEAD = 60  # seconds – must schedule ≥ 1 min ahead


# ── time helpers ─────────────────────────────────────────────────────
def to_utc_iso(ts: str) -> str:
    """
    Convert *any* ISO-8601 timestamp into a timezone-aware **UTC** ISO string
    (keeps seconds precision and the “+00:00” offset).

    If the input is naïve (no zone information) we assume **Hong Kong Time**,
    preserving existing clients that always sent HKT.

    Raises
    ------
    ValueError
        • If the string is not ISO-8601  
        • If the requested time is < 60 s in the future (UTC)
    """
    try:
        dt = datetime.fromisoformat(ts)          # naïve *or* aware
    except ValueError as exc:
        raise ValueError(
            "`exec_at` must be ISO-8601 (YYYY-MM-DDThh:mm[:ss])"
        ) from exc

    if dt.tzinfo is None:                        # default to HKT
        dt = dt.replace(tzinfo=_HKT)
    else:
        dt = dt.astimezone(_HKT)                 # normalise first

    utc_aware = dt.astimezone(timezone.utc)

    delta = (utc_aware - datetime.now(timezone.utc)).total_seconds()
    if delta < _MIN_LEAD:
        raise ValueError(
            f"`exec_at` must be at least {_MIN_LEAD} s in the future (Δ={delta:.1f}s)"
        )

    return utc_aware.isoformat(timespec="seconds")


# Back-compat alias – will be removed in a future major revision
parse_hkt_to_utc = to_utc_iso


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
def log_to_api(
    level: str,
    message: str,
    secondary_tag: str = "scheduler",
    tertiary_tag: str | None = None,
):
    """
    Fire-and-forget wrapper around the existing `/api/log` endpoint.

    Never raises – errors are logged but don’t break the scheduler.
    """
    url = f"{_internal_base()}/api/log"
    payload = {
        "tag": secondary_tag,
        "tertiary_tag": tertiary_tag,
        "base": level,
        "message": message,
    }
    try:
        requests.post(url, json=payload, timeout=10).raise_for_status()
    except Exception as exc:  # noqa: BLE001
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
    "http.call": lambda p: requests.post(
        p["url"], json=p.get("body"), timeout=p.get("timeout", 10)
    ).json(),
}


def execute_prompt(prompt_type: str, payload: dict):
    """Dispatch to the requested prompt handler."""
    try:
        handler = PROMPTS[prompt_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported prompt_type '{prompt_type}'") from exc
    return handler(payload)

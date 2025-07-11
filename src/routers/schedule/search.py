# ── src/routers/schedule/search.py ──────────────────────────────────
"""
Helper for `/api/schedule/search`.

Downloads the full job registry from the Durable-Functions
scheduler and filters it locally by *tag*, *secondary_tag*,
and *tertiary_tag*.  Any filter that is left blank / omitted
acts as a wildcard.
"""
from __future__ import annotations

import logging
from typing import Optional, List

import requests
from fastapi import HTTPException

from .helpers import list_url, forward_error

_logger = logging.getLogger(__name__)


def _fetch_jobs() -> list[dict]:
    """
    Call the scheduler’s ‘list’ endpoint and return the raw JSON payload
    (a dict with a top-level `"jobs": […]` list).  Tries both the
    anonymous `/api/schedules` and the legacy `/schedules` route.
    """
    for path in (list_url(), list_url().replace("/api/schedules", "/schedules")):
        try:
            resp = requests.get(path, timeout=15)
        except Exception as exc:              # noqa: BLE001
            _logger.warning("Scheduler unreachable at %s: %s", path, exc)
            continue

        if resp.status_code == 200:
            try:
                return resp.json().get("jobs", [])
            except ValueError:
                raise HTTPException(
                    status_code=502,
                    detail="Scheduler returned invalid JSON",
                ) from None

        if resp.status_code in (404, 503):    # cold start → try next
            continue

        forward_error(resp)                   # bubble up unexpected errors

    raise HTTPException(status_code=502, detail="Scheduler list endpoint not found")


def handle_search(
    tag: Optional[str],
    secondary_tag: Optional[str],
    tertiary_tag: Optional[str],
) -> List[str]:
    """
    Return a list of *instanceId* strings whose metadata matches all
    **non-blank** filters.  Blank / None filters are treated as wildcards.
    """
    jobs = _fetch_jobs()
    matched: List[str] = []

    for job in jobs:
        if tag and job.get("tag") != tag:
            continue
        if secondary_tag and job.get("secondary_tag") != secondary_tag:
            continue
        if tertiary_tag and job.get("tertiary_tag") != tertiary_tag:
            continue
        matched.append(job.get("instanceId"))

    return matched

# ── src/routers/lcsd/lcsd_cleanup_validator_scheduler.py ──────────────
"""
Public endpoint
    /api/lcsd/lcsd_cleanup_validator_scheduler   (GET | POST)

Combined **validator + scheduler** helper.

•  Runs the same duplicate-cleanup / validation logic as
   *lcsd_cleanup_validator.py* for **both** the current month and the
   *next* month (HKT), fully in-lined – no import from the original file.

•  If *this-month* validation fails, it triggers the LCSD timetable probe
   endpoint **immediately**.

•  It then wipes **all** schedules that *this* helper has previously
   created (tag = lcsd, secondary_tag = cleanup_validator_scheduler) and
   finally creates **one** fresh schedule that fires a
   `lcsd.timetable_probe` job at a future time determined by the rules
   in the user story (D1 – D3).

All significant actions are logged via `/api/log`.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time as _time, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
import os
import requests
from fastapi import APIRouter, HTTPException
from azure.cosmos import exceptions as cosmos_exc

# Re-use the Cosmos helpers already wired up by /api/json
from routers.jsondata.endpoints import _container  # type: ignore

# ───────────────────────────────────────────────────────────────────────
# Configuration
# ───────────────────────────────────────────────────────────────────────
_TZ_HKT = ZoneInfo("Asia/Hong_Kong")
_LOG_PAYLOAD_BASE = {
    "tag":          "lcsd",
    "tertiary_tag": "cleanup_validator",
    "base":         "[info]",
}

_TAG_VAL      = "lcsd"
_SEC_TT       = "af_excel_timetable"
_SCHED_TAG    = "lcsd"
_SCHED_SECOND = "cleanup_validator_scheduler"

_HTTP_TIMEOUT = 15  # seconds

router = APIRouter()


# ───────────────────────────────────────────────────────────────────────
# Small helpers
# ───────────────────────────────────────────────────────────────────────
def _internal_base() -> str:
    """Derive the *public* base-URL of the FastAPI app."""
    if (base := os.getenv("WEBAPP_BASE_URL")):
        return base.rstrip("/")
    if (site := os.getenv("WEBSITE_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    return "http://localhost:8000"


def _log(message: str) -> None:
    """Fire-and-forget wrapper around /api/log."""
    try:
        requests.post(
            f"{_internal_base()}/api/log",
            json={**_LOG_PAYLOAD_BASE, "message": message},
            timeout=_HTTP_TIMEOUT,
        )
    except Exception:  # noqa: BLE001 – logging must never break the flow
        pass


def _cleanup_month(yr: int, mon: int, ref_day: int) -> Dict:
    """
    Duplicate clean-up & validation for one specific year / month.
    Returns a dict with detailed stats.
    """
    query = """
        SELECT c.id, c.tertiary_tag, c.day
        FROM   c
        WHERE  c.tag = @tag
          AND  c.secondary_tag = @sec
          AND  c.year  = @yr
          AND  c.month = @mon
    """
    params = [
        {"name": "@tag", "value": _TAG_VAL},
        {"name": "@sec", "value": _SEC_TT},
        {"name": "@yr",  "value": yr},
        {"name": "@mon", "value": mon},
    ]

    try:
        items: List[Dict] = list(
            _container.query_items(
                query=query,
                parameters=params,
                partition_key=_TAG_VAL,
                enable_cross_partition_query=False,
            )
        )
    except cosmos_exc.CosmosHttpResponseError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cosmos DB query failed: {exc.message}",
        ) from exc

    total_loaded = len(items)
    _log(f"[{yr}-{mon:02d}] loaded {total_loaded} timetable docs")

    # group by tertiary_tag (LCSD number); keep doc nearest *ref_day*
    groups: Dict[str, List[Dict]] = {}
    for itm in items:
        key = itm.get("tertiary_tag")
        if key:
            groups.setdefault(key, []).append(itm)

    deleted = 0
    for docs in groups.values():
        if len(docs) <= 1:
            continue

        # distance metric: abs(day – ref_day); tie-break → larger day (more recent)
        docs.sort(key=lambda d: (abs(int(d.get("day", 1)) - ref_day), -int(d.get("day", 1))))
        keep_id = docs[0]["id"]

        for doc in docs[1:]:
            try:
                _container.delete_item(item=doc["id"], partition_key=_TAG_VAL)
                deleted += 1
            except cosmos_exc.CosmosHttpResponseError:
                pass  # delete failure non-fatal

    remaining = len(groups)
    validation_passed = remaining >= 20
    verdict = "passed" if validation_passed else "failed"
    _log(f"[{yr}-{mon:02d}] duplicate clean-up done → remaining {remaining} ({verdict})")

    return {
        "loaded":            total_loaded,
        "deleted":           deleted,
        "remaining":         remaining,
        "validation_passed": validation_passed,
    }


def _trigger_timetable_probe() -> Optional[Dict]:
    """POST /api/lcsd/lcsd_af_timetable_probe (fire-and-forget, but return JSON if available)."""
    url = f"{_internal_base()}/api/lcsd/lcsd_af_timetable_probe"
    try:
        resp = requests.post(url, timeout=_HTTP_TIMEOUT)
        if resp.headers.get("content-type", "").startswith("application/json"):
            _log("Triggered lcsd_af_timetable_probe")
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        _log(f"[warn] timetable_probe trigger failed: {exc}")
    return None


def _wipe_existing_schedules() -> List[str]:
    """Delete every schedule created by earlier runs of this helper."""
    base = _internal_base()
    try:
        resp = requests.get(
            f"{base}/api/schedule/search",
            params={"tag": _SCHED_TAG, "secondary_tag": _SCHED_SECOND},
            timeout=_HTTP_TIMEOUT,
        )
        ids: List[str] = resp.json().get("instance_ids", [])  # type: ignore[arg-type]
    except Exception:
        ids = []

    deleted: List[str] = []
    for inst_id in ids:
        try:
            requests.delete(f"{base}/api/schedule/{inst_id}", timeout=_HTTP_TIMEOUT)
            deleted.append(inst_id)
        except Exception:
            pass

    if deleted:
        _log(f"Deleted {len(deleted)} old schedule(s): {', '.join(deleted)}")
    return deleted


def _days_in_month(yr: int, mon: int) -> int:
    return calendar.monthrange(yr, mon)[1]


def _compute_next_exec(today: date) -> datetime:
    """
    Implement rules D1 – D3 to pick the *next* execution datetime (HKT).
    The returned datetime is **tz-aware**.
    """
    yr, mon, day = today.year, today.month, today.day
    days = _days_in_month(yr, mon)
    mid  = days // 2
    lower_start = mid + 1

    if day <= mid:
        target = date(yr, mon, lower_start)         # D1
    elif day == days:
        # last day → first day of lower half of *next* month
        next_mon = mon + 1 if mon < 12 else 1
        next_yr  = yr + 1 if next_mon == 1 else yr
        next_days = _days_in_month(next_yr, next_mon)
        target = date(next_yr, next_mon, (next_days // 2) + 1)  # D2
    else:
        cand = today + timedelta(days=5)
        if cand.month != mon:
            target = date(yr, mon, days)            # month overflow → last day
        else:
            target = cand                           # D3

    # schedule at 03:00 local time
    dt_hkt = datetime.combine(target, _time(hour=3, minute=0), tzinfo=_TZ_HKT)
    # ensure ≥ 60 s in the future
    if (dt_hkt - datetime.now(_TZ_HKT)).total_seconds() < 120:  # safety cushion
        dt_hkt += timedelta(minutes=2)
    return dt_hkt


def _schedule_probe(exec_dt_hkt: datetime) -> Optional[str]:
    """Create a new *lcsd.timetable_probe* schedule – return the instance-id."""
    body = {
        "exec_at":       exec_dt_hkt.isoformat(timespec="seconds"),
        "prompt_type":   "lcsd.timetable_probe",
        "payload":       {},
        "tag":           _SCHED_TAG,
        "secondary_tag": _SCHED_SECOND,
    }
    try:
        resp = requests.post(f"{_internal_base()}/api/schedule", json=body, timeout=_HTTP_TIMEOUT)
        if resp.status_code in (200, 202) and resp.headers.get("content-type", "").startswith("application/json"):
            inst_id = resp.json().get("transaction_id") or resp.json().get("id")
            _log(f"Created schedule {inst_id} for {body['exec_at']}")
            return inst_id
    except Exception as exc:  # noqa: BLE001
        _log(f"[warn] failed to create schedule: {exc}")
    return None


# ───────────────────────────────────────────────────────────────────────
# FastAPI route
# ───────────────────────────────────────────────────────────────────────
@router.api_route(
    "/api/lcsd/lcsd_cleanup_validator_scheduler",
    methods=["GET", "POST"],
    summary="Clean up duplicate Excel timetables AND manage re-probe schedule",
)
def lcsd_cleanup_validator_scheduler() -> Dict:
    today_hkt = datetime.now(_TZ_HKT).date()

    # ── A) clean-up + validate for *this* and *next* month ──────────────
    this_stats = _cleanup_month(today_hkt.year, today_hkt.month, today_hkt.day)

    # compute next month
    nxt_mon = today_hkt.month + 1 if today_hkt.month < 12 else 1
    nxt_yr  = today_hkt.year + 1 if nxt_mon == 1 else today_hkt.year
    # ref-day → use today's *day* as anchor for next month
    next_stats = _cleanup_month(nxt_yr, nxt_mon, today_hkt.day)

    # ── B) trigger probe if *this-month* failed ─────────────────────────
    probe_result = None
    if not this_stats["validation_passed"]:
        probe_result = _trigger_timetable_probe()

    # ── C) wipe old schedules created by this helper ────────────────────
    wiped_ids = _wipe_existing_schedules()

    # ── D) create new schedule for next probe run ───────────────────────
    exec_dt_hkt = _compute_next_exec(today_hkt)
    new_sched_id = _schedule_probe(exec_dt_hkt)

    # ── summary payload -------------------------------------------------
    return {
        "status":  "success",
        "timestamp_hkt": datetime.now(_TZ_HKT).isoformat(timespec="seconds"),
        "this_month": this_stats,
        "next_month": next_stats,
        "thismonth_validation_passed": this_stats["validation_passed"],
        "nextmonth_validation_passed": next_stats["validation_passed"],
        "probe_triggered": probe_result is not None,
        "probe_result": probe_result,
        "wiped_schedule_ids": wiped_ids,
        "new_schedule_id": new_sched_id,
        "next_exec_hkt": exec_dt_hkt.isoformat(timespec="seconds"),
    }

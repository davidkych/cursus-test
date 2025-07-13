"""
lcsd_cleanup_validator_scheduler.py
===================================

Public route
    /api/lcsd/lcsd_cleanup_validator_scheduler   (GET | POST)

A self-contained variant of *lcsd_cleanup_validator.py* that

  • validates **this** and **next** month’s Excel-timetable documents  
  • triggers a fresh `/api/lcsd/lcsd_af_timetable_probe` run when
    the *current* month validation fails  
  • cleans up any *previous* schedules raised by itself, then creates
    a new *lcsd.timetable_probe* job according to the rules in the
    user story (see doc-string in parent ticket)

All Cosmos, log-API and scheduler interactions use the existing
internal helpers/endpoints – **no external imports** from the older
cleanup module.
"""
from __future__ import annotations

import calendar
import os
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, HTTPException
from azure.cosmos import exceptions as cosmos_exc

# ── shared Cosmos & log helpers ──────────────────────────────────────
from routers.jsondata.endpoints import _container
from routers.log.endpoints import append_log, LogPayload

router = APIRouter()

_HKT = ZoneInfo("Asia/Hong_Kong")
_MIN_DOCS = 20            # validation threshold
_TAG = "lcsd"
_SEC_TAG = "af_excel_timetable"
_SCHED_SEC_TAG = "cleanup_validator_scheduler"


# ─────────────────────────────────────────────────────────────────────
# Logging helper – always pushes to `/api/log`
# ─────────────────────────────────────────────────────────────────────
def _log(msg: str) -> None:
    payload = LogPayload(
        tag=_TAG,
        tertiary_tag=_SCHED_SEC_TAG,
        base="info",
        message=msg,
    )
    append_log(payload)


# ─────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────
def _today_hkt() -> date:
    return datetime.now(_HKT).date()


def _internal_base() -> str:
    """Resolve the FastAPI base-URL the same way *scheduler_fapp.utils* does."""
    if (base := os.getenv("WEBAPP_BASE_URL")):
        return base.rstrip("/")
    if (site := os.getenv("FASTAPI_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    if (site := os.getenv("WEBAPP_SITE_NAME") or os.getenv("WEBSITE_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    return "http://localhost:8000"


def _month_after(yy: int, mm: int) -> Tuple[int, int]:
    return (yy + (mm == 12), 1 if mm == 12 else mm + 1)


# ─────────────────────────────────────────────────────────────────────
# Core clean-up & validation logic (independent, no imports)
# ─────────────────────────────────────────────────────────────────────
def _process_month(year: int, month: int, anchor_day: int) -> Tuple[int, int, bool]:
    """
    For (*year*, *month*) – load all timetable docs, keep **one** per
    `tertiary_tag` closest to *anchor_day*, delete the rest, return

        (total_loaded, deleted, validation_passed_bool)
    """
    query = """
        SELECT c.id, c.tertiary_tag, c.day
        FROM   c
        WHERE  c.tag = @tag
          AND  c.secondary_tag = @sec
          AND  c.year = @yr
          AND  c.month = @mon
    """
    params = [
        {"name": "@tag", "value": _TAG},
        {"name": "@sec", "value": _SEC_TAG},
        {"name": "@yr",  "value": year},
        {"name": "@mon", "value": month},
    ]

    try:
        items: List[Dict] = list(
            _container.query_items(
                query=query,
                parameters=params,
                partition_key=_TAG,
                enable_cross_partition_query=False,
            )
        )
    except cosmos_exc.CosmosHttpResponseError as exc:
        raise HTTPException(
            status_code=500, detail=f"Cosmos DB query failed: {exc.message}"
        ) from exc

    total_loaded = len(items)
    groups: Dict[str, List[Dict]] = {}
    for itm in items:
        key = itm.get("tertiary_tag")
        if key:
            groups.setdefault(key, []).append(itm)

    deleted = 0
    for docs in groups.values():
        if len(docs) <= 1:
            continue

        # choose the **one** closest to anchor_day (tie-breaker → newer)
        def _metric(d):
            day_val = int(d.get("day", 1))
            return abs(day_val - anchor_day), -day_val

        docs.sort(key=_metric)
        keep_id = docs[0]["id"]

        for doc in docs[1:]:
            try:
                _container.delete_item(item=doc["id"], partition_key=_TAG)
                deleted += 1
            except cosmos_exc.CosmosHttpResponseError:
                pass  # deletion failure not fatal

    remaining = len(groups)
    validation_passed = remaining >= _MIN_DOCS
    return total_loaded, deleted, validation_passed


# ─────────────────────────────────────────────────────────────────────
# Scheduler helpers
# ─────────────────────────────────────────────────────────────────────
def _scheduler_search() -> List[str]:
    url = f"{_internal_base()}/api/schedule/search"
    try:
        resp = requests.get(
            url,
            params={
                "tag": _TAG,
                "secondary_tag": _SCHED_SEC_TAG,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("instance_ids", [])
    except Exception:
        return []


def _scheduler_delete(instance_id: str) -> None:
    url = f"{_internal_base()}/api/schedule/{instance_id}"
    try:
        requests.delete(url, timeout=15)
    except Exception:
        pass


def _scheduler_create(exec_at_iso: str) -> str | None:
    url = f"{_internal_base()}/api/schedule"
    payload = {
        "exec_at": exec_at_iso,
        "prompt_type": "lcsd.timetable_probe",
        "payload": {},
        "tag": _TAG,
        "secondary_tag": _SCHED_SEC_TAG,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json().get("transaction_id") or resp.json().get("id")
    except Exception as exc:
        _log(f"Failed to create schedule: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────
# Timetable-probe trigger
# ─────────────────────────────────────────────────────────────────────
def _trigger_probe() -> None:
    url = f"{_internal_base()}/api/lcsd/lcsd_af_timetable_probe"
    try:
        requests.post(url, params={"start": 0, "end": 20}, timeout=30)
    except Exception as exc:
        _log(f"lcsd_af_timetable_probe trigger failed: {exc}")


# ─────────────────────────────────────────────────────────────────────
# Exec-date calculation
# ─────────────────────────────────────────────────────────────────────
def _calc_exec_date(today: date,
                    this_ok: bool,
                    next_ok: bool) -> datetime:
    yy, mm, dd = today.year, today.month, today.day
    days_in_month = calendar.monthrange(yy, mm)[1]
    mid = days_in_month // 2

    # A. upper half (1…mid)
    if dd <= mid:
        exec_day = mid + 1
        exec_date = date(yy, mm, exec_day)

    # B. last day
    elif dd == days_in_month:
        nyy, nmm = _month_after(yy, mm)
        n_days = calendar.monthrange(nyy, nmm)[1]
        exec_day = n_days // 2 + 1
        exec_date = date(nyy, nmm, exec_day)

    # C. lower half but not last day
    else:
        if not next_ok:                           # C3i
            tentative = today + timedelta(days=5)
            if tentative.month != mm:             # rolled over → use last day
                exec_date = date(yy, mm, days_in_month)
            else:
                exec_date = tentative
        else:                                     # C3ii
            nyy, nmm = _month_after(yy, mm)
            n_days = calendar.monthrange(nyy, nmm)[1]
            exec_day = n_days // 2 + 1
            exec_date = date(nyy, nmm, exec_day)

    # fixed local schedule time → 03:00 HKT
    exec_dt = datetime(
        exec_date.year, exec_date.month, exec_date.day, 3, 0, tzinfo=_HKT
    )
    # ensure ≥ 60 s ahead
    if (exec_dt - datetime.now(_HKT)).total_seconds() < 60:
        exec_dt = datetime.now(_HKT) + timedelta(seconds=65)
    return exec_dt


# ─────────────────────────────────────────────────────────────────────
# FastAPI route
# ─────────────────────────────────────────────────────────────────────
@router.api_route(
    "/api/lcsd/lcsd_cleanup_validator_scheduler",
    methods=["GET", "POST"],
    summary="LCSD timetable clean-up, validation & self-scheduler",
)
def lcsd_cleanup_validator_scheduler() -> Dict:
    today = _today_hkt()
    yy, mm = today.year, today.month
    nyy, nmm = _month_after(yy, mm)

    # 1️⃣ process current & next month ----------------------------------------
    c_loaded, c_del, c_ok = _process_month(yy, mm, today.day)
    _log(f"Current month: loaded={c_loaded}, deleted={c_del}, ok={c_ok}")

    n_loaded, n_del, n_ok = _process_month(nyy, nmm, 1)
    _log(f"Next month: loaded={n_loaded}, deleted={n_del}, ok={n_ok}")

    # 2️⃣ trigger probe if current failed ------------------------------------
    if not c_ok:
        _log("Current month validation failed – triggering timetable_probe")
        _trigger_probe()

    # 3️⃣ clean up **existing** schedules raised by this script --------------
    for inst_id in _scheduler_search():
        _scheduler_delete(inst_id)
        _log(f"Cancelled previous schedule {inst_id}")

    # 4️⃣ create new schedule -------------------------------------------------
    exec_dt = _calc_exec_date(today, c_ok, n_ok)
    exec_iso = exec_dt.isoformat(timespec="seconds")
    new_id = _scheduler_create(exec_iso)
    if new_id:
        _log(f"Scheduled new timetable_probe at {exec_iso} (id={new_id})")
    else:
        _log("Failed to create new schedule")

    return {
        "status": "success",
        "current_validation_passed": c_ok,
        "next_validation_passed": n_ok,
        "new_schedule_id": new_id,
        "exec_at": exec_iso,
    }

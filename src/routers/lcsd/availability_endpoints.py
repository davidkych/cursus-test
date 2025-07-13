# ── src/routers/lcsd/availability_endpoints.py ───────────────────────────────
"""
LCSD jogging-lane **availability** checker  –  /api/lcsd/availability

*Refactor 3 — 2025-07-13*

The query semantics (point-in-time & same-day period) are identical to the
legacy implementation, but the timetable source has moved:

    tag            = 'lcsd'
    secondary_tag  = 'af_excel_timetable'
    tertiary_tag   = <lcsd_number>   (≘ request.lcsdid)
    year/month/day = HKT date when the Excel parser ran

The endpoint now fetches **the document with the latest *day* value** for the
requested month and LCSD-ID and answers against its ``timetable`` mapping.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

from azure.cosmos import exceptions as cosmos_exc

# Re-use the already-configured Cosmos container from /api/json helpers
from routers.jsondata.endpoints import _container

# ── constants ────────────────────────────────────────────────────────────────
_HK_TZ = ZoneInfo("Asia/Hong_Kong")

_TAG      = "lcsd"
_SEC_TAG  = "af_excel_timetable"
_TRUE_OK  = {"A", "L", "G", "T", "F"}           # letters that mean “available”

# ── regex helpers ────────────────────────────────────────────────────────────
_TIME_TBL_RE  = re.compile(r"^\d{1,2}:\d{2}$")                 # timetable HH:MM
_TIME_USER_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")        # user HH:MM[:SS]
_PERIOD_RE    = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?-\d{1,2}:\d{2}(:\d{2})?$")

# ── time helpers ─────────────────────────────────────────────────────────────
def _now_hk() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).astimezone(_HK_TZ)


def _parse_hhmm_tbl(txt: str) -> _dt.time:
    if not _TIME_TBL_RE.fullmatch(txt.strip()):
        raise ValueError(f"Bad timetable time {txt!r}")
    h, m = map(int, txt.strip().split(":"))
    return _dt.time(h, m)


def _parse_user_time(txt: str) -> _dt.time:
    if not _TIME_USER_RE.fullmatch(txt.strip()):
        raise ValueError(f"Bad time {txt!r}")
    parts = list(map(int, txt.strip().split(":")))
    h, m, s = (parts + [0, 0])[:3]
    return _dt.time(h, m, s)


def _sec(t: _dt.time) -> int:  # hh:mm[:ss] → seconds since midnight
    return t.hour * 3600 + t.minute * 60 + t.second


def _range_to_str(st: int, en: int) -> str:
    def _hhmmss(sec: int) -> str:
        h, sec = divmod(sec, 3600)
        m, s   = divmod(sec, 60)
        return f"{h:02}:{m:02}:{s:02}"
    return f"{_hhmmss(st)}-{_hhmmss(en)}"


# ── Cosmos helper ────────────────────────────────────────────────────────────
def _latest_timetable_doc(lcsdid: str, year: int, month: int) -> Optional[Dict]:
    """
    Return ``data`` field of the *latest-day* timetable document for *lcsdid*
    in (*year*, *month*).  None → no matching document.
    """
    query = """
      SELECT c.data, c.day
      FROM   c
      WHERE  c.tag = @tag
        AND  c.secondary_tag = @sec
        AND  c.tertiary_tag = @ter
        AND  c.year = @yr
        AND  c.month = @mon
    """
    params = [
        {"name": "@tag",  "value": _TAG},
        {"name": "@sec",  "value": _SEC_TAG},
        {"name": "@ter",  "value": lcsdid},
        {"name": "@yr",   "value": year},
        {"name": "@mon",  "value": month},
    ]
    try:
        items = list(
            _container.query_items(
                query=query,
                parameters=params,
                partition_key=_TAG,                 # single-partition query
                enable_cross_partition_query=False,
            )
        )
    except cosmos_exc.CosmosHttpResponseError as exc:
        raise HTTPException(500, f"Cosmos DB query failed: {exc.message}") from exc

    if not items:
        return None
    # pick the document with the highest *day*
    items.sort(key=lambda r: int(r.get("day", 0)), reverse=True)
    return items[0]["data"]


# ── legend & interval helpers ────────────────────────────────────────────────
def _legend_for(code: str, doc: Dict[str, Any]) -> Optional[str]:
    return (doc.get("legend_map") or {}).get(code)


def _intervals_for_date(doc: Dict[str, Any], date_iso: str) -> List[Tuple[int, int, str]]:
    """
    Convert timetable rows for *date_iso* into
        [(start_sec, end_sec_inclusive, status_letter), …]  sorted ascending.
    """
    intervals: List[Tuple[int, int, str]] = []
    for row in doc.get("timetable", {}).get(date_iso, []):
        try:
            st = _parse_hhmm_tbl(row["start"])
            en = _parse_hhmm_tbl(row["end"])
        except Exception:
            continue
        s_sec, e_sec = _sec(st), _sec(en) - 1      # timetable “end” is exclusive
        if e_sec < s_sec:
            continue
        letter = str(row.get("status", "")).strip()
        intervals.append((s_sec, e_sec, letter))
    return sorted(intervals, key=lambda t: t[0])


def _same_status(a: Dict[str, str], b: Dict[str, str]) -> bool:
    return (
        a["status_letter"] == b["status_letter"]
        and a["availability"] == b["availability"]
    )


def _slice_period(intervals: List[Tuple[int, int, str]],
                  q_st: int, q_en: int,
                  legend_cb) -> List[Dict[str, str]]:
    """
    Slice *intervals* (sorted) by [q_st, q_en] inclusive → non-overlapping
    segments with status/legend.  Fills gaps as «closed».
    """
    segs: List[Dict[str, str]] = []
    i = 0
    cur = q_st
    while cur <= q_en:
        while i < len(intervals) and intervals[i][1] < cur:
            i += 1
        if i >= len(intervals) or intervals[i][0] > cur:
            gap_end = min(q_en, intervals[i][0] - 1) if i < len(intervals) else q_en
            segs.append(
                {
                    "time_range": _range_to_str(cur, gap_end),
                    "status_letter": "closed",
                    "availability": "false",
                    "legend": "運動場關閉時間",
                }
            )
            cur = gap_end + 1
            continue
        iv_st, iv_en, status = intervals[i]
        seg_end = min(iv_en, q_en)
        segs.append(
            {
                "time_range": _range_to_str(cur, seg_end),
                "status_letter": status if status else None,
                "availability": "true" if status in _TRUE_OK else "false",
                "legend": legend_cb(status) if status else None,
            }
        )
        cur = seg_end + 1

    # merge adjacent identical segments
    merged: List[Dict[str, str]] = []
    for sg in segs:
        if merged and _same_status(merged[-1], sg):
            merged[-1]["time_range"] = (
                f"{merged[-1]['time_range'].split('-')[0]}-{sg['time_range'].split('-')[1]}"
            )
        else:
            merged.append(sg)
    return merged


# ── FastAPI models & router ──────────────────────────────────────────────────
class AvailabilityRequest(BaseModel):
    lcsdid: str = Field(..., description="LCSD facility number")
    date:   Optional[str] = Field(None, description="YYYY-MM-DD")
    time:   Optional[str] = Field(None, description="HH:MM[:SS] (point query)")
    period: Optional[str] = Field(
        None,
        description="HH:MM[:SS]-HH:MM[:SS] (same-day range)",
        regex=_PERIOD_RE.pattern,
    )


router = APIRouter()


@router.post("/api/lcsd/availability", summary="Check LCSD availability (POST)")
def availability_post(req: AvailabilityRequest):
    return _handle(req.lcsdid, req.date, req.time, req.period)


@router.get("/api/lcsd/availability", summary="Check LCSD availability (GET)")
def availability_get(
    lcsdid: str = Query(..., description="LCSD facility number"),
    date:   Optional[str] = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    time:   Optional[str] = Query(None, regex=_TIME_USER_RE.pattern),
    period: Optional[str] = Query(None, regex=_PERIOD_RE.pattern),
):
    return _handle(lcsdid, date, time, period)


# ── main handler ─────────────────────────────────────────────────────────────
def _handle(lcsdid: str,
            date_str: Optional[str],
            time_str: Optional[str],
            period_str: Optional[str]) -> Dict[str, Any]:
    if time_str and period_str:
        raise HTTPException(400, "Provide either *time* or *period*, not both.")

    now = _now_hk()
    date_obj = _dt.date.fromisoformat(date_str) if date_str else now.date()
    year, month = date_obj.year, date_obj.month

    # accept only current or next month
    first = now.date().replace(day=1)
    nextm = (first + _dt.timedelta(days=32)).replace(day=1)
    if (year, month) not in {(first.year, first.month), (nextm.year, nextm.month)}:
        raise HTTPException(400, "Only current or next month timetables accepted.")

    doc = _latest_timetable_doc(lcsdid, year, month)
    if not doc:
        raise HTTPException(404, "Timetable document not found.")

    legend_cb = lambda code: _legend_for(code, doc)
    intervals = _intervals_for_date(doc, date_obj.isoformat())
    facility_name = doc.get("name") or lcsdid

    # ―― point query (default) ――――――――――――――――――――――――――――――――――――――――
    if not period_str:
        time_obj = (
            _parse_user_time(time_str)
            if time_str else now.time().replace(microsecond=0)
        )
        sec_val = _sec(time_obj)
        for st, en, status in intervals:
            if st <= sec_val <= en:
                availability = "true" if status in _TRUE_OK else "false"
                return _point_resp(
                    now, facility_name, lcsdid, date_obj, time_obj,
                    status or "closed", availability, legend_cb(status)
                )
        # outside timetable → closed
        return _point_resp(
            now, facility_name, lcsdid, date_obj, time_obj,
            "closed", "false", "運動場關閉時間"
        )

    # ―― period query ―――――――――――――――――――――――――――――――――――――――――――――――
    start_txt, end_txt = period_str.split("-", 1)
    t_start = _parse_user_time(start_txt)
    t_end   = _parse_user_time(end_txt)
    if t_start >= t_end:
        raise HTTPException(400, "period start must be earlier than end.")
    q_start, q_end = _sec(t_start), _sec(t_end) - 1

    segments = _slice_period(intervals, q_start, q_end, legend_cb)
    return {
        "timestamp_queried": now.isoformat(timespec="seconds"),
        "facility_name": facility_name,
        "requested": {
            "lcsdid": lcsdid,
            "date": date_obj.isoformat(),
            "period": period_str,
        },
        "segments": segments,
    }


# ── helper to build point-query response ────────────────────────────────────
def _point_resp(ts: _dt.datetime, fac_name: str, lcsdid: str,
                d_obj: _dt.date, t_obj: _dt.time,
                status: str, avail: str, legend: Optional[str]) -> Dict[str, Any]:
    return {
        "timestamp_queried": ts.isoformat(timespec="seconds"),
        "facility_name": fac_name,
        "requested": {
            "lcsdid": lcsdid,
            "datetime_iso": f"{d_obj.isoformat()}T{t_obj.isoformat()}",
        },
        "status_letter": status,
        "availability": avail,
        "legend": legend,
    }

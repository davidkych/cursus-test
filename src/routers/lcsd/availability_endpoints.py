# ── src/routers/lcsd/availability_endpoints.py ─────────────────────────────
"""
LCSD jogging-lane **availability** checker  —  /api/lcsd/availability

Key changes (2025-07-14)
────────────────────────
* The public query parameter is now **lcsd_number**.  
  – For backwards-compatibility a deprecated alias **lcsdid** is still
    accepted but not documented.  
* AvailabilityRequest model updated accordingly.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from zoneinfo import ZoneInfo

# ── constants ──────────────────────────────────────────────────────────────
_TAG       = "lcsd"
_SEC_TAG   = "af_excel_timetable"
_TRUE      = {"A", "L", "G", "T", "F"}          # “available” status letters
_HK_TZ     = ZoneInfo("Asia/Hong_Kong")

_TIME_TBL  = re.compile(r"^\d{1,2}:\d{2}$")
_TIME_USR  = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_PERIOD_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?-\d{1,2}:\d{2}(:\d{2})?$")

# ── Cosmos wiring ──────────────────────────────────────────────────────────
_ep   = os.getenv("COSMOS_ENDPOINT")
_db   = os.getenv("COSMOS_DATABASE", "cursusdb")
_cont = os.getenv("COSMOS_CONTAINER", "jsonContainer")
_key  = os.getenv("COSMOS_KEY")                         # optional (MSI if None)

_client    = (CosmosClient(_ep, credential=_key)
              if _key else CosmosClient(_ep, credential=DefaultAzureCredential()))
_container = _client.get_database_client(_db).get_container_client(_cont)


def _latest_timetable_doc(lcsd_number: str, year: int, month: int) -> Optional[Dict[str, Any]]:
    """
    Return the **data** part of the newest `af_excel_timetable` document that
    matches (lcsd_number, year, month).  Newest = highest `day`, `_ts` tie-break.
    """
    query = """
      SELECT c.data, c.day, c._ts
      FROM   c
      WHERE  c.tag = @tag AND c.secondary_tag = @sec AND c.tertiary_tag = @ter
             AND  c.year = @yr  AND c.month = @mon
      ORDER BY c.day DESC, c._ts DESC
    """
    params = [
        {"name": "@tag",  "value": _TAG},
        {"name": "@sec",  "value": _SEC_TAG},
        {"name": "@ter",  "value": lcsd_number},
        {"name": "@yr",   "value": year},
        {"name": "@mon",  "value": month},
    ]
    docs = list(
        _container.query_items(
            query=query,
            parameters=params,
            partition_key=_TAG,
            enable_cross_partition_query=False,
        )
    )
    return docs[0]["data"] if docs else None


# ── helpers ────────────────────────────────────────────────────────────────
def _now_hk() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).astimezone(_HK_TZ)


def _parse_tbl_time(txt: str) -> datetime.time:
    if not _TIME_TBL.fullmatch(txt.strip()):
        raise ValueError(f"Bad timetable time {txt!r}")
    h, m = map(int, txt.split(":"))
    return datetime.time(h, m)


def _parse_user_time(txt: str) -> datetime.time:
    if not _TIME_USR.fullmatch(txt.strip()):
        raise ValueError(f"Bad time {txt!r}")
    h, m, *s = map(int, txt.split(":"))
    return datetime.time(h, m, s[0] if s else 0)


def _sec(t: datetime.time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def _intervals_for_date(
    schedules: List[Dict[str, Any]], date_iso: str
) -> List[Tuple[int, int, str]]:
    out: List[Tuple[int, int, str]] = []
    for sch in schedules:
        for iv in sch.get("timetable", {}).get(date_iso, []):
            try:
                st = _parse_tbl_time(iv["start"])
                en = _parse_tbl_time(iv["end"])
            except Exception:
                continue
            start, end = _sec(st), _sec(en) - 1    # timetable “end” is exclusive
            if end >= start:
                out.append((start, end, str(iv["status"]).strip()))
    return sorted(out, key=lambda x: x[0])


def _legend_for_letter(schedules: List[Dict[str, Any]], code: str) -> Optional[str]:
    for sch in schedules:
        if code in (sch.get("legend_map") or {}):
            return str(sch["legend_map"][code]).strip()
    return None


def _make_legend_cache(scheds):
    cache = {}
    def _legend(code: str):
        if code not in cache:
            cache[code] = _legend_for_letter(scheds, code)
        return cache[code]
    return _legend


def _hhmmss(sec: int) -> str:
    h, sec = divmod(sec, 3600)
    m, s   = divmod(sec, 60)
    return f"{h:02}:{m:02}:{s:02}"


def _range_txt(st: int, en: int) -> str:
    return f"{_hhmmss(st)}-{_hhmmss(en)}"


def _merge_adjacent(segments: List[Dict[str, str]]) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    for seg in segments:
        if merged and all(
            merged[-1][k] == seg[k] for k in ("status_letter", "availability", "legend")
        ):
            merged[-1]["time_range"] = (
                f"{merged[-1]['time_range'].split('-')[0]}-{seg['time_range'].split('-')[1]}"
            )
        else:
            merged.append(seg)
    return merged


def _slice_period(intervals, q_start, q_end, legend_fn) -> List[Dict[str, str]]:
    segments: List[Dict[str, str]] = []
    i, cur = 0, q_start
    while cur <= q_end:
        while i < len(intervals) and intervals[i][1] < cur:
            i += 1
        if i >= len(intervals) or intervals[i][0] > cur:         # gap → closed
            gap_end = min(q_end, intervals[i][0] - 1) if i < len(intervals) else q_end
            segments.append({
                "time_range": _range_txt(cur, gap_end),
                "status_letter": "closed",
                "availability": "false",
                "legend": "運動場關閉時間",
            })
            cur = gap_end + 1
            continue

        st, en, status = intervals[i]
        seg_end = min(en, q_end)
        segments.append({
            "time_range": _range_txt(cur, seg_end),
            "status_letter": status,
            "availability": "true" if status in _TRUE else "false",
            "legend": legend_fn(status),
        })
        cur = seg_end + 1
    return _merge_adjacent(segments)


# ── Pydantic model & router ──────────────────────────────────────────
class AvailabilityRequest(BaseModel):
    lcsd_number: str = Field(..., alias="lcsd_number")
    date:   Optional[str] = Field(None, description="YYYY-MM-DD")
    time:   Optional[str] = Field(None, description="HH:MM[:SS]  (point query)")
    period: Optional[str] = Field(
        None, description="HH:MM[:SS]-HH:MM[:SS]  (same-day period query)"
    )

router = APIRouter()

@router.post("/api/lcsd/availability")
def availability_post(req: AvailabilityRequest):
    return _handle(req.lcsd_number, req.date, req.time, req.period)

@router.get("/api/lcsd/availability")
def availability_get(
    lcsd_number: Optional[str] = Query(None, alias="lcsd_number"),
    lcsdid_alias: Optional[str] = Query(None, alias="lcsdid"),  # deprecated
    date:   Optional[str] = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    time:   Optional[str] = Query(None, regex=r"^\d{1,2}:\d{2}(:\d{2})?$"),
    period: Optional[str] = Query(None, regex=_PERIOD_RE.pattern),
):
    lcsdid_value = lcsd_number or lcsdid_alias
    if not lcsdid_value:
        raise HTTPException(400, "Query parameter 'lcsd_number' is required.")
    return _handle(lcsdid_value, date, time, period)


# ── main handler ─────────────────────────────────────────────────────
def _handle(lcsdid: str,
            date_str: Optional[str],
            time_str: Optional[str],
            period_str: Optional[str]):
    if time_str and period_str:
        raise HTTPException(400, "Provide either *time* or *period*, not both.")

    now = _now_hk()
    date_obj = datetime.date.fromisoformat(date_str) if date_str else now.date()
    year, month = date_obj.year, date_obj.month

    # only current / next month accepted
    first = now.date().replace(day=1)
    nextm = (first + datetime.timedelta(days=32)).replace(day=1)
    if (year, month) not in {(first.year, first.month), (nextm.year, nextm.month)}:
        raise HTTPException(400, "Only current or next month timetables accepted.")

    doc = _latest_timetable_doc(lcsdid, year, month)
    if not doc:
        raise HTTPException(404, "Timetable not found for requested facility/month.")

    facility = doc.get("name", lcsdid)
    schedules = [doc]                        # keep helper expectations
    legend_fn = _make_legend_cache(schedules)
    intervals = _intervals_for_date(schedules, date_obj.isoformat())

    # ―― point query (default) ――――――――――――――――――――――――――――――――――――――――
    if not period_str:
        t_obj = (_parse_user_time(time_str)
                 if time_str else now.time().replace(microsecond=0))
        return _point_query(now, facility, lcsdid, date_obj, t_obj,
                            intervals, legend_fn)

    # ―― period query ―――――――――――――――――――――――――――――――――――――――――――――――
    st_txt, en_txt = period_str.split("-", 1)
    t_start, t_end = _parse_user_time(st_txt), _parse_user_time(en_txt)
    if t_start >= t_end:
        raise HTTPException(400, "period start must be earlier than end.")
    segments = _slice_period(intervals, _sec(t_start), _sec(t_end) - 1, legend_fn)
    return {
        "timestamp_queried": now.isoformat(timespec="seconds"),
        "facility_name": facility,
        "requested": {"lcsd_number": lcsdid, "date": date_obj.isoformat(), "period": period_str},
        "segments": segments,
    }


# ── helpers for point query ──────────────────────────────────────────
def _point_query(ts, fac_name, lcsdid, d_obj, t_obj, intervals, legend_fn):
    sec = _sec(t_obj)
    for st, en, status in intervals:
        if st <= sec <= en:
            return _build_point_resp(ts, fac_name, lcsdid, d_obj, t_obj,
                                     status, "true" if status in _TRUE else "false",
                                     legend_fn(status))
    # outside all intervals → closed
    return _build_point_resp(ts, fac_name, lcsdid, d_obj, t_obj,
                             "closed", "false", "運動場關閉時間")


def _build_point_resp(ts, fac_name, lcsdid, d_obj, t_obj, status, avail, legend):
    return {
        "timestamp_queried": ts.isoformat(timespec="seconds"),
        "facility_name": fac_name,
        "requested": {
            "lcsd_number": lcsdid,
            "datetime_iso": f"{d_obj.isoformat()}T{t_obj.isoformat()}",
        },
        "status_letter": status,
        "availability": avail,
        "legend": legend,
    }

"""
LCSD jogging-lane **availability** checker – /api/lcsd/availability

Refactor 3 (2025-07-13)
───────────────────────
Same public contract as the legacy endpoint, **but** it now reads an
*Excel-timetable* JSON that lives as **one document per facility**

    tag            = 'lcsd'
    secondary_tag  = 'af_excel_timetable'
    tertiary_tag   = <lcsdid>
    year/month     = request date
    day            = **latest** in that month

Document schema (see lcsd_af_excel_timetable.py) ⟶
    {
      "did_number": …,
      "lcsd_number": …,
      "name": …,
      "timetable": { "YYYY-MM-DD":[{start,end,status},…] },
      "legend_map": { "A":"Available", … }
    }

All other behaviours (period query, legends, HK-only date checks, etc.)
remain identical to the 2025-06-21 endpoint.
"""
from __future__ import annotations

import datetime as _dt
import re as _re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo
from azure.cosmos import exceptions as _cosmos_exc

# ── shared Cosmos container (partition-key = 'lcsd') ─────────────────────────
from routers.jsondata.endpoints import _container                                         # type: ignore

_HK_TZ = ZoneInfo("Asia/Hong_Kong")
_TRUE_CODES = {"A", "L", "G", "T", "F"}

# ── regex helpers ────────────────────────────────────────────────────────────
_TIME_TBL_RE  = _re.compile(r"^\d{1,2}:\d{2}$")                       # timetable HH:MM
_TIME_USER_RE = _re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")              # user HH:MM[:SS]
_PERIOD_RE    = _re.compile(r"^\d{1,2}:\d{2}(:\d{2})?-\d{1,2}:\d{2}(:\d{2})?$")

# ── misc tiny helpers ────────────────────────────────────────────────────────
def _now_hk() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).astimezone(_HK_TZ)


def _parse_timetable_hhmm(txt: str) -> _dt.time:
    if not _TIME_TBL_RE.fullmatch(txt.strip()):
        raise ValueError(f"Bad timetable time {txt!r}")
    h, m = map(int, txt.strip().split(":"))
    return _dt.time(h, m)


def _parse_user_time(txt: str) -> _dt.time:
    if not _TIME_USER_RE.fullmatch(txt.strip()):
        raise ValueError(f"Bad time {txt!r}")
    h, m, *rest = map(int, txt.strip().split(":"))
    s = rest[0] if rest else 0
    return _dt.time(h, m, s)


def _time_to_sec(t: _dt.time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


# ── Cosmos helpers ───────────────────────────────────────────────────────────
def _latest_timetable_doc(year: int, month: int, lcsdid: str) -> Optional[Dict[str, Any]]:
    """
    Return `.data` of the newest (*day* DESC) timetable document for *lcsdid*
    in *year/month*, or **None** when absent.
    """
    query = """
        SELECT TOP 1 c.data
        FROM   c
        WHERE  c.tag = @tag
          AND  c.secondary_tag = @sec
          AND  c.tertiary_tag  = @ter
          AND  c.year = @yr
          AND  c.month = @mon
        ORDER BY c.day DESC
    """
    params = [
        {"name": "@tag",  "value": "lcsd"},
        {"name": "@sec",  "value": "af_excel_timetable"},
        {"name": "@ter",  "value": lcsdid},
        {"name": "@yr",   "value": year},
        {"name": "@mon",  "value": month},
    ]
    try:
        items = list(
            _container.query_items(
                query=query,
                parameters=params,
                partition_key="lcsd",
                enable_cross_partition_query=False,
            )
        )
    except _cosmos_exc.CosmosHttpResponseError as exc:                                     # pragma: no cover
        raise HTTPException(500, f"Cosmos DB query failed: {exc.message}") from exc
    return items[0]["data"] if items else None


# ── legend cache (per request) ───────────────────────────────────────────────
def _make_legend_cache(legend_map: Dict[str, str]):
    cache: Dict[str, Optional[str]] = {}
    def _legend(code: str) -> Optional[str]:
        if code not in cache:
            cache[code] = legend_map.get(code)
        return cache[code]
    return _legend


# ── timetable helpers ───────────────────────────────────────────────────────
def _intervals_for_date(tab: Dict[str, List[Dict[str, str]]],
                        date_iso: str) -> List[Tuple[int, int, str]]:
    """
    Convert one day’s timetable into a list of *(start_sec, end_sec_incl, status)*.
    """
    out: List[Tuple[int, int, str]] = []
    for itv in tab.get(date_iso, []):
        try:
            st = _parse_timetable_hhmm(itv["start"])
            en = _parse_timetable_hhmm(itv["end"])
        except Exception:
            continue
        start_sec = _time_to_sec(st)
        end_sec   = _time_to_sec(en) - 1                       # timetable *end* is exclusive
        if end_sec >= start_sec:
            out.append((start_sec, end_sec, str(itv["status"]).strip()))
    return sorted(out, key=lambda x: x[0])


def _sec_to_hhmmss(sec: int) -> str:
    h, sec = divmod(sec, 3600)
    m, s   = divmod(sec, 60)
    return f"{h:02}:{m:02}:{s:02}"


def _sec_range(st: int, en: int) -> str:
    return f"{_sec_to_hhmmss(st)}-{_sec_to_hhmmss(en)}"


def _same_status(a: Dict[str, str], b: Dict[str, str]) -> bool:
    return a["status_letter"] == b["status_letter"] and a["availability"] == b["availability"]


def _segment_period(iv: List[Tuple[int, int, str]],
                    q_start: int, q_end: int,
                    legend_of) -> List[Dict[str, str]]:
    """
    Slice intervals by `[q_start,q_end]` and coalesce identical statuses.
    """
    segs: List[Dict[str, str]] = []
    i = 0
    cur = q_start
    while cur <= q_end:
        while i < len(iv) and iv[i][1] < cur:
            i += 1
        if i >= len(iv) or iv[i][0] > cur:                      # gap -> closed
            gap_end = min(q_end, iv[i][0] - 1) if i < len(iv) else q_end
            segs.append({
                "time_range": _sec_range(cur, gap_end),
                "status_letter": "closed",
                "availability": "false",
                "legend": "運動場關閉時間",
            })
            cur = gap_end + 1
            continue

        iv_st, iv_en, status = iv[i]
        seg_end = min(iv_en, q_end)
        segs.append({
            "time_range": _sec_range(cur, seg_end),
            "status_letter": status or None,
            "availability": "true" if status in _TRUE_CODES else "false",
            "legend": legend_of(status) if status else None,
        })
        cur = seg_end + 1

    merged: List[Dict[str, str]] = []
    for s in segs:
        if merged and _same_status(merged[-1], s):
            merged[-1]["time_range"] = (
                f"{merged[-1]['time_range'].split('-')[0]}-{s['time_range'].split('-')[1]}"
            )
        else:
            merged.append(s)
    return merged


# ── FastAPI plumbing ─────────────────────────────────────────────────────────
router = APIRouter()


@router.get("/api/lcsd/availability", summary="Check LCSD availability (GET)")
def availability_get(
    lcsdid: str = Query(..., description="LCSD facility number"),
    date: Optional[str] = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    time: Optional[str] = Query(None, regex=r"^\d{1,2}:\d{2}(:\d{2})?$"),
    period: Optional[str] = Query(None, regex=_PERIOD_RE.pattern),
):
    return _handle(lcsdid, date, time, period)


@router.post("/api/lcsd/availability", summary="Check LCSD availability (POST)")
def availability_post(payload: Dict[str, Any]):
    """
    Body JSON identical to the legacy spec:
        {
          "lcsdid": "1060a",
          "date":   "2025-07-13",
          "time":   "18:00:00"           # XOR period
        }
    """
    return _handle(
        payload.get("lcsdid"),
        payload.get("date"),
        payload.get("time"),
        payload.get("period"),
    )


# ── main handler ─────────────────────────────────────────────────────────────
def _handle(lcsdid: str | None,
            date_str: Optional[str],
            time_str: Optional[str],
            period_str: Optional[str]):
    if not lcsdid:
        raise HTTPException(400, "Parameter *lcsdid* is required.")
    if time_str and period_str:
        raise HTTPException(400, "Provide either *time* or *period*, not both.")

    now_hk = _now_hk()
    date_obj = (
        _dt.date.fromisoformat(date_str) if date_str else now_hk.date()
    )
    year, month = date_obj.year, date_obj.month

    # only current OR next month
    first_of_cur = now_hk.date().replace(day=1)
    first_of_next = (first_of_cur + _dt.timedelta(days=32)).replace(day=1)
    if (year, month) not in {(first_of_cur.year, first_of_cur.month),
                             (first_of_next.year, first_of_next.month)}:
        raise HTTPException(400, "Only current or next month timetables accepted.")

    doc = _latest_timetable_doc(year, month, lcsdid)
    if not doc:
        raise HTTPException(404, "Timetable not found for requested facility/month.")

    legend_cached = _make_legend_cache(doc.get("legend_map") or {})
    intervals = _intervals_for_date(doc.get("timetable", {}), date_obj.isoformat())

    # ――― point-in-time query ――――――――――――――――――――――――――――――――――――――――――
    if not period_str:
        time_obj = (
            _parse_user_time(time_str) if time_str else now_hk.time().replace(microsecond=0)
        )
        sec = _time_to_sec(time_obj)
        for st, en, status in intervals:
            if st <= sec <= en:
                avail = "true" if status in _TRUE_CODES else "false"
                return _point_resp(
                    now_hk, doc["name"], lcsdid, date_obj, time_obj,
                    status, avail, legend_cached(status)
                )
        # outside all intervals → closed
        return _point_resp(
            now_hk, doc["name"], lcsdid, date_obj, time_obj,
            "closed", "false", "運動場關閉時間"
        )

    # ――― period query ―――――――――――――――――――――――――――――――――――――――――――――――
    start_txt, end_txt = period_str.split("-", 1)
    t_start = _parse_user_time(start_txt)
    t_end   = _parse_user_time(end_txt)
    if t_start >= t_end:
        raise HTTPException(400, "period start must be earlier than end.")

    q_start, q_end = _time_to_sec(t_start), _time_to_sec(t_end) - 1
    segments = _segment_period(intervals, q_start, q_end, legend_cached)
    return {
        "timestamp_queried": now_hk.isoformat(timespec="seconds"),
        "facility_name": doc["name"],
        "requested": {
            "lcsdid": lcsdid,
            "date": date_obj.isoformat(),
            "period": period_str,
        },
        "segments": segments,
    }


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

# ── src/routers/lcsd/availability_endpoints.py ───────────────────────
"""
LCSD jogging-lane **availability** checker – /api/lcsd/availability

Refactor 2 (2025-06-21 • period query)
──────────────────────────────────────
• Keeps the *point-in-time* query (`date` + `time`) as the default.  
• Adds **period query** support  
    – `period="HH:MM[:SS]-HH:MM[:SS]"` (same-day range).  
    – Returns `segments:[{time_range, status_letter, availability, legend}, …]`.
• If the whole period shares one status, only one segment is returned.
• Timetable “end” (e.g. 21:30) is treated as **exclusive**, i.e. up to
  21:29:59, to prevent off-by-one errors.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Tuple
import datetime, os, re
from zoneinfo import ZoneInfo

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

# ── Time-zone helpers ────────────────────────────────────────────────
_HK_TZ = ZoneInfo("Asia/Hong_Kong")
def _now_hk() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).astimezone(_HK_TZ)

# ── Cosmos helpers ───────────────────────────────────────────────────
_cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
_database_name   = os.getenv("COSMOS_DATABASE", "cursusdb")
_container_name  = os.getenv("COSMOS_CONTAINER", "jsonContainer")
_cosmos_key      = os.getenv("COSMOS_KEY")

_client = (
    CosmosClient(_cosmos_endpoint, credential=_cosmos_key)
    if _cosmos_key else CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
)
_container = _client.get_database_client(_database_name).get_container_client(_container_name)

TRUE_CODES = {"A", "L", "G", "T", "F"}

# ── Regex & parsers ──────────────────────────────────────────────────
_TIME_TBL_RE  = re.compile(r"^\d{1,2}:\d{2}$")                 # timetable HH:MM
_TIME_USER_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")        # user HH:MM[:SS]
_PERIOD_RE    = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?-\d{1,2}:\d{2}(:\d{2})?$")

def _parse_timetable_hhmm(txt: str) -> datetime.time:
    if not _TIME_TBL_RE.fullmatch(txt.strip()):
        raise ValueError(f"Bad timetable time {txt!r}")
    h, m = map(int, txt.strip().split(":"))
    return datetime.time(h, m)

def _parse_user_time(txt: str) -> datetime.time:
    if not _TIME_USER_RE.fullmatch(txt.strip()):
        raise ValueError(f"Bad time {txt!r}")
    parts = list(map(int, txt.strip().split(":")))
    h, m, s = (parts + [0, 0])[:3]
    return datetime.time(h, m, s)

def _time_to_sec(t: datetime.time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second

# ── Cosmos helpers ───────────────────────────────────────────────────
def _latest_timetable_doc(year: int, month: int) -> Optional[Dict[str, Any]]:
    docs = list(
        _container.query_items(
            query="""
              SELECT TOP 1 c.data
              FROM   c
              WHERE  c.tag='lcsd' AND c.secondary_tag='timetable'
                     AND c.year=@y AND c.month=@m
              ORDER BY c._ts DESC
            """,
            parameters=[{"name": "@y", "value": year}, {"name": "@m", "value": month}],
            enable_cross_partition_query=True,
        )
    )
    return docs[0]["data"] if docs else None

def _legend_for_letter(schedules: List[Dict[str, Any]], code: str) -> Optional[str]:
    for sch in schedules:
        legend = sch.get("legend_map") or {}
        if code in legend:
            return str(legend[code]).strip()
    return None

# ── Core helpers ─────────────────────────────────────────────────────
def _intervals_for_date(schedules: List[Dict[str, Any]], date_iso: str) -> List[Tuple[int, int, str]]:
    """Return [(start_sec, end_sec_inclusive, status), …] for one date."""
    out: List[Tuple[int, int, str]] = []
    for sch in schedules:
        for iv in sch["timetable"].get(date_iso, []):
            try:
                st = _parse_timetable_hhmm(iv["start"])
                en = _parse_timetable_hhmm(iv["end"])
            except Exception:
                continue
            start_sec = _time_to_sec(st)
            end_sec   = _time_to_sec(en) - 1          # end is *exclusive*
            if end_sec < start_sec:
                continue
            out.append((start_sec, end_sec, iv["status"].strip()))
    return sorted(out, key=lambda x: x[0])

def _segment_period(intervals: List[Tuple[int, int, str]],
                    q_start: int, q_end: int) -> List[Dict[str, str]]:
    """
    Slice `intervals` (sorted) by [q_start, q_end] inclusive and return
    list of non-overlapping segments with status.
    """
    segments: List[Dict[str, str]] = []
    i = 0
    cur = q_start
    while cur <= q_end:
        # find interval covering cur
        while i < len(intervals) and intervals[i][1] < cur:
            i += 1
        if i >= len(intervals) or intervals[i][0] > cur:
            # gap: treat as closed
            gap_end = min(q_end, intervals[i][0] - 1) if i < len(intervals) else q_end
            segments.append({
                "time_range": _sec_range(cur, gap_end),
                "status_letter": "closed",
                "availability": "false",
                "legend": "運動場關閉時間"
            })
            cur = gap_end + 1
            continue
        # inside an interval
        iv_start, iv_end, status = intervals[i]
        seg_end = min(iv_end, q_end)
        segments.append({
            "time_range": _sec_range(cur, seg_end),
            "status_letter": status if status else None,
            "availability": "true" if status in TRUE_CODES else "false",
            "legend": None if not status else _legend_cached(status)
        })
        cur = seg_end + 1
    # merge adjacent identical status
    merged: List[Dict[str, str]] = []
    for seg in segments:
        if merged and _same_status(merged[-1], seg):
            merged[-1]["time_range"] = f"{merged[-1]['time_range'].split('-')[0]}-{seg['time_range'].split('-')[1]}"
        else:
            merged.append(seg)
    return merged

def _same_status(a: Dict[str, str], b: Dict[str, str]) -> bool:
    return a["status_letter"] == b["status_letter"] and a["availability"] == b["availability"]

def _sec_to_hhmmss(sec: int) -> str:
    h, sec = divmod(sec, 3600)
    m, s   = divmod(sec, 60)
    return f"{h:02}:{m:02}:{s:02}"

def _sec_range(st: int, en: int) -> str:
    return f"{_sec_to_hhmmss(st)}-{_sec_to_hhmmss(en)}"

# small cache for legends (per request)
def _make_legend_cache(schedules):
    cache = {}
    def _legend(code: str):
        if code not in cache:
            cache[code] = _legend_for_letter(schedules, code)
        return cache[code]
    return _legend
# will be initialised in _handle
_legend_cached = lambda code: None   # placeholder

# ── FastAPI models & router ──────────────────────────────────────────
class AvailabilityRequest(BaseModel):
    lcsdid: str = Field(..., description="LCSD facility number")
    date:   Optional[str] = Field(None, description="YYYY-MM-DD")
    time:   Optional[str] = Field(None, description="HH:MM[:SS] (point query)")
    period: Optional[str] = Field(
        None,
        description="HH:MM[:SS]-HH:MM[:SS] (same day)"
    )

router = APIRouter()

@router.post("/api/lcsd/availability", summary="Check LCSD availability (POST)")
def availability_post(req: AvailabilityRequest):
    return _handle(req.lcsdid, req.date, req.time, req.period)

@router.get("/api/lcsd/availability", summary="Check LCSD availability (GET)")
def availability_get(
    lcsdid: str = Query(..., description="LCSD facility number"),
    date:   Optional[str] = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    time:   Optional[str] = Query(None, regex=r"^\d{1,2}:\d{2}(:\d{2})?$"),
    period: Optional[str] = Query(
        None,
        regex=r"^\d{1,2}:\d{2}(:\d{2})?-\d{1,2}:\d{2}(:\d{2})?$"
    ),
):
    return _handle(lcsdid, date, time, period)

# ── Main handler ─────────────────────────────────────────────────────
def _handle(lcsdid: str, date_str: Optional[str],
            time_str: Optional[str], period_str: Optional[str]):
    if time_str and period_str:
        raise HTTPException(400, "Provide either *time* or *period*, not both.")

    now_hk = _now_hk()
    date_obj = (
        datetime.date.fromisoformat(date_str)
        if date_str else now_hk.date()
    )
    year, month = date_obj.year, date_obj.month

    # month validation (same as before)
    first = now_hk.date().replace(day=1)
    nextm = (first + datetime.timedelta(days=32)).replace(day=1)
    if (year, month) not in {(first.year, first.month), (nextm.year, nextm.month)}:
        raise HTTPException(400, "Only current or next month timetables accepted.")

    doc = _latest_timetable_doc(year, month)
    if not doc or lcsdid not in doc["facilities"]:
        raise HTTPException(404, "Timetable or facility not found.")

    facility   = doc["facilities"][lcsdid]
    schedules  = facility["schedules"]
    global _legend_cached
    _legend_cached = _make_legend_cache(schedules)

    date_iso   = date_obj.isoformat()
    intervals  = _intervals_for_date(schedules, date_iso)

    if not period_str:                         # ―― point query (legacy) ――
        time_obj = (
            _parse_user_time(time_str)
            if time_str else now_hk.time().replace(microsecond=0)
        )
        return _point_query(now_hk, facility, lcsdid, date_obj, time_obj, intervals)

    # ―― period query ――――――――――――――――――――――――――――――――――――――――――――――――
    start_txt, end_txt = period_str.split("-", 1)
    t_start = _parse_user_time(start_txt)
    t_end   = _parse_user_time(end_txt)
    if t_start >= t_end:
        raise HTTPException(400, "period start must be earlier than end.")
    q_start, q_end = _time_to_sec(t_start), _time_to_sec(t_end) - 1

    segments = _segment_period(intervals, q_start, q_end)
    return {
        "timestamp_queried": now_hk.isoformat(timespec="seconds"),
        "facility_name": facility["name"],
        "requested": {
            "lcsdid": lcsdid,
            "date": date_iso,
            "period": period_str,
        },
        "segments": segments,
    }

# ── Point query helper (unchanged behaviour) ─────────────────────────
def _point_query(now_hk, facility, lcsdid, date_obj, time_obj, intervals):
    sec = _time_to_sec(time_obj)
    for st, en, status in intervals:
        if st <= sec <= en:
            availability = "true" if status in TRUE_CODES else "false"
            return _build_point_resp(
                now_hk, facility["name"], lcsdid, date_obj, time_obj,
                status, availability, _legend_cached(status)
            )
    # outside all intervals → closed
    return _build_point_resp(
        now_hk, facility["name"], lcsdid, date_obj, time_obj,
        "closed", "false", "運動場關閉時間"
    )

def _build_point_resp(ts, fac_name, lcsdid, d_obj, t_obj,
                      status, avail, legend):
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

# ── End of file ──────────────────────────────────────────────────────

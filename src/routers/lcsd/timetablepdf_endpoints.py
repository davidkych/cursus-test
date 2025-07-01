# ── src/routers/lcsd/timetablepdf_endpoints.py ───────────────────────
"""
LCSD athletic-field timetable **PDF** builder – /api/lcsd/timetablepdf

• Reads the latest timetable-probe JSON (secondary_tag = "timetableprobe").
• For every facility that has a jogging-schedule PDF matching the requested
  month / year, downloads and parses the PDF with *pdfplumber*.
• Merges contiguous identical status blocks and fills gaps with status "A",
  mirroring the behaviour of the Excel version.
• Stores the consolidated JSON back to Cosmos DB with:
      tag            = "lcsd"
      secondary_tag  = "timetablepdf"
      year, month    = request parameters
• Always returns JSON:
      { stored_id, facility_count, diagnostics: [ "...", ... ] }
  or HTTP 500 on fatal errors.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Tuple, Optional
import datetime, hashlib, logging, os, re, requests
from io import BytesIO

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
import pdfplumber

# ── Constants ────────────────────────────────────────────────────────
TAG_PROBE        = "timetableprobe"
TAG_TIMETABLEPDF = "timetablepdf"

# ── Cosmos helpers (identical pattern to other LCSD routers) ─────────
_cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
_database_name   = os.getenv("COSMOS_DATABASE", "cursusdb")
_container_name  = os.getenv("COSMOS_CONTAINER", "jsonContainer")
_cosmos_key      = os.getenv("COSMOS_KEY")

_client = (
    CosmosClient(_cosmos_endpoint, credential=_cosmos_key)
    if _cosmos_key else CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())
)
_container = _client.get_database_client(_database_name).get_container_client(_container_name)

def _item_id(tag, secondary, year, month, day=None) -> str:
    parts = [tag, secondary, str(year), str(month)]
    if day is not None:
        parts.append(str(day))
    return "_".join(parts)

def _upsert(tag, secondary, year, month, day, data):
    _container.upsert_item({
        "id": _item_id(tag, secondary, year, month, day),
        "tag": tag,
        "secondary_tag": secondary,
        "year": year,
        "month": month,
        "day": day,
        "data": data,
    })

# ── PDF-parsing utilities ───────────────────────────────────────────
log = logging.getLogger("lcsd.timetablepdf")
log.setLevel(logging.INFO)

_TIME_ROW_RE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})\s+(.*)$")
_LEGEND_RE   = re.compile(r"^\s*([A-Z])\s+(.+)$")

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _parse_pdf_bytes(pdf_bytes: bytes, month: int, year: int) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Parse one LCSD jogging-schedule PDF and return (timetable_dict, legend_map).
    Fills any gaps in timetable with status "A".
    """
    lines: List[str] = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            lines.extend((p.extract_text() or "").splitlines())

    # 1  Locate first time row & collect legend.
    first_time_idx: Optional[int] = None
    legend_map: Dict[str, str] = {}
    for idx, ln in enumerate(lines):
        if _TIME_ROW_RE.match(ln):
            first_time_idx = idx
            break
        m = _LEGEND_RE.match(ln)
        if m and m.group(1) not in legend_map:
            legend_map[m.group(1)] = m.group(2).strip()

    if first_time_idx is None:
        return {}, legend_map                               # no timetable rows

    # 2  Harvest consecutive time-rows into status matrix.
    time_labels: List[str] = []
    status_matrix: List[List[str]] = []
    for ln in lines[first_time_idx:]:
        m = _TIME_ROW_RE.match(ln)
        if not m:
            if time_labels:
                break                                       # reached non-timetable area
            continue
        start_lbl, _end_lbl, rest = m.groups()
        tokens = rest.strip().split()
        time_labels.append(start_lbl)
        status_matrix.append(tokens)

    if not status_matrix:
        return {}, legend_map

    # Pad rows so they all have equal length.
    col_count = max(len(r) for r in status_matrix)
    for r in status_matrix:
        r += [""] * (col_count - len(r))

    # 3  Build per-day timetables.
    timetable: Dict[str, List[Dict[str, str]]] = {}
    for col in range(col_count):
        day = col + 1
        try:
            date_iso = datetime.date(year, month, day).isoformat()
        except ValueError:
            continue                                        # skip invalid days

        raw: List[Dict[str, str]] = []
        for i, row in enumerate(status_matrix):
            status = row[col].strip()
            if not status:
                continue
            start = time_labels[i]
            end   = time_labels[i+1] if i+1 < len(time_labels) else None
            if end:
                raw.append({"start": start, "end": end, "status": status})

        # Merge contiguous identical-status intervals.
        merged: List[Dict[str, str]] = []
        for iv in raw:
            if merged and merged[-1]["status"] == iv["status"] and merged[-1]["end"] == iv["start"]:
                merged[-1]["end"] = iv["end"]
            else:
                merged.append(iv.copy())

        # Fill gaps with status "A".
        filled: List[Dict[str, str]] = []
        if merged:
            if merged[0]["start"] != time_labels[0]:
                filled.append({"start": time_labels[0], "end": merged[0]["start"], "status": "A"})
            for i, iv in enumerate(merged):
                filled.append(iv)
                nxt = merged[i+1]["start"] if i+1 < len(merged) else None
                if nxt and iv["end"] != nxt:
                    filled.append({"start": iv["end"], "end": nxt, "status": "A"})
            if merged[-1]["end"] != time_labels[-1]:
                filled.append({"start": merged[-1]["end"], "end": time_labels[-1], "status": "A"})
        else:
            filled.append({"start": time_labels[0], "end": time_labels[-1], "status": "A"})

        timetable[date_iso] = filled

    return timetable, legend_map

# ── Core builder helpers ─────────────────────────────────────────────
def _latest_probe() -> Dict[str, Any]:
    docs = list(
        _container.query_items(
            query="SELECT TOP 1 c.data FROM c WHERE c.tag='lcsd' AND c.secondary_tag=@s ORDER BY c._ts DESC",
            parameters=[{"name": "@s", "value": TAG_PROBE}],
            enable_cross_partition_query=True,
        )
    )
    if not docs:
        raise RuntimeError("No timetable-probe data found in Cosmos DB.")
    return docs[0]["data"]

def _build_timetable_pdf(month: int, year: int) -> Tuple[Dict[str, Any], List[str]]:
    probe = _latest_probe()
    facilities_out: Dict[str, Any] = {}
    diagnostics: List[str] = []

    for facility in probe.get("timetables", []):
        lcsd_no   = facility.get("lcsd_number")
        base_name = facility.get("name")
        schedules = facility.get("jogging_schedule", [])

        sched_results: List[Dict[str, Any]] = []
        for sch in schedules:
            try:
                m = int(str(sch.get("month")).lstrip("0") or "0")
                y = int(sch.get("year"))
            except Exception:
                diagnostics.append(f"{lcsd_no}: invalid month/year in probe")
                continue
            if m != month or y != year:
                continue

            source = sch.get("pdf_url") or sch.get("pdf_filename") or ""
            if not source:
                diagnostics.append(f"{lcsd_no}: missing PDF URL for {month:02}/{year}")
                continue

            # Download/read PDF.
            try:
                if source.startswith("http"):
                    resp = requests.get(source, timeout=15)
                    resp.raise_for_status()
                    pdf_bytes = resp.content
                else:
                    with open(source, "rb") as fh:
                        pdf_bytes = fh.read()
            except Exception as exc:
                diagnostics.append(f"{lcsd_no}: PDF fetch failed – {exc}")
                continue

            # Parse.
            try:
                timetable, legend_map = _parse_pdf_bytes(pdf_bytes, month, year)
            except Exception as exc:
                diagnostics.append(f"{lcsd_no}: PDF parse error – {exc}")
                continue

            sched_results.append({
                "pdf_url": source,
                "sha256": _sha256(pdf_bytes),
                "timetable": timetable,
                "legend_map": legend_map,
            })

        if not sched_results:
            diagnostics.append(f"{lcsd_no}: no usable PDF for {month:02}/{year}")
            continue

        if len(sched_results) == 1:
            facilities_out[lcsd_no] = {"name": base_name, "schedules": sched_results}
        else:
            for idx, sr in enumerate(sched_results):
                key = f"{lcsd_no}{chr(ord('a') + idx)}"
                facilities_out[key] = {
                    "name": base_name,
                    "schedule_index": idx,
                    "schedules": [sr],
                }

    ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    data = {
        "metadata": {"timestamp": ts, "year": year, "month": month},
        "source": TAG_PROBE,
        "facilities": facilities_out,
    }
    return data, diagnostics

def _store_and_prepare_response(data: Dict[str, Any], diags: List[str], year: int, month: int):
    _upsert("lcsd", TAG_TIMETABLEPDF, year, month, None, data)
    return {
        "stored_id":      _item_id("lcsd", TAG_TIMETABLEPDF, year, month),
        "facility_count": len(data["facilities"]),
        "diagnostics":    diags,
    }

# ── FastAPI router ───────────────────────────────────────────────────
class TimetablePDFReq(BaseModel):
    year: int  = Field(..., ge=1900)
    month: int = Field(..., ge=1, le=12)

router = APIRouter()

@router.post("/api/lcsd/timetablepdf", summary="Build LCSD timetable-PDF JSON (POST)")
def timetablepdf_post(req: TimetablePDFReq):
    try:
        data, diags = _build_timetable_pdf(req.month, req.year)
        return _store_and_prepare_response(data, diags, req.year, req.month)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc)})

@router.get("/api/lcsd/timetablepdf", summary="Build LCSD timetable-PDF JSON (GET)")
def timetablepdf_get(
    year: int = Query(..., ge=1900),
    month: int = Query(..., ge=1, le=12),
):
    try:
        data, diags = _build_timetable_pdf(month, year)
        return _store_and_prepare_response(data, diags, year, month)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc)})

# ── End of file ──────────────────────────────────────────────────────

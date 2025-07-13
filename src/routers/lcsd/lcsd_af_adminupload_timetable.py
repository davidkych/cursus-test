# ── src/routers/lcsd/lcsd_af_adminupload_timetable.py ───────────────────────
"""
Public webpage endpoint

    • GET  /api/lcsd/lcsd_af_adminupload_timetable
          → returns an HTML upload form (layout module)

    • POST /api/lcsd/lcsd_af_adminupload_timetable/upload
          → accepts a timetable-JSON file, converts & saves it into Cosmos DB:
                 ─ master  → tag=lcsd, secondary=af_availtimetable
                 ─ per-fac → tag=lcsd, secondary=af_excel_timetable,
                              tertiary=lcsd_number
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from zoneinfo import ZoneInfo

from routers.jsondata.endpoints import _upsert, _item_id

from .lcsd_af_adminupload_timetable_layout import UPLOAD_FORM_HTML

router = APIRouter()


# ───────────────────────────── helpers ──────────────────────────────────────
def _iso_to_ymd(ts: str | None) -> tuple[int, int, int]:
    """Return (y, m, d) from ISO timestamp *ts* (or now if None/invalid)."""
    dt: datetime
    try:
        dt = datetime.fromisoformat(ts) if ts else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        dt = None
    if dt is None:
        dt = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    if dt.tzinfo is None:                  # make timezone-aware for consistency
        dt = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Hong_Kong"))
    return dt.year, dt.month, dt.day, dt.isoformat(timespec="seconds")


def _build_master_payload(src: Dict) -> Dict:
    """
    Convert the uploaded *records* JSON into the *af_availtimetable* structure.
    """
    facilities_map: Dict[str, Dict] = {}
    records: List[Dict] = src.get("records", [])

    for rec in records:
        lcsd_num = rec.get("lcsd_number")
        if not lcsd_num:
            continue
        fac = facilities_map.setdefault(
            lcsd_num,
            {
                "did_number":   rec.get("did_number"),
                "lcsd_number":  lcsd_num,
                "name":         rec.get("name"),
                "jogging_schedule": [],
            },
        )
        sched_entry = {
            "month_year": rec.get("month_year"),
            "excel_url":  rec.get("excel_url"),
        }
        if rec.get("pdf_url"):
            sched_entry["pdf_url"] = rec["pdf_url"]
        fac["jogging_schedule"].append(sched_entry)

    facilities: List[Dict] = list(facilities_map.values())
    num_dids = len({f["did_number"] for f in facilities if f.get("did_number")})
    timestamp_src = (src.get("metadata") or {}).get("timestamp")
    year, month, day, ts_iso = _iso_to_ymd(timestamp_src)

    return {
        "metadata": {
            "timestamp":       ts_iso,
            "num_dids":        num_dids,
            "num_facilities":  len(facilities),
        },
        "facilities": facilities,
    }, (year, month, day)  # 2-tuple: payload + date parts


# ──────────────────────────── routes ────────────────────────────────────────
@router.get(
    "/api/lcsd/lcsd_af_adminupload_timetable",
    include_in_schema=False,
    response_class=HTMLResponse,
)
def admin_upload_form() -> HTMLResponse:
    """Serve the HTML page with the file-upload form."""
    return HTMLResponse(UPLOAD_FORM_HTML)


@router.post("/api/lcsd/lcsd_af_adminupload_timetable/upload")
async def admin_upload_post(file: UploadFile = File(...)) -> Dict:
    """
    Handle the uploaded timetable-JSON, convert & persist to Cosmos DB.
    """
    try:
        raw = await file.read()
        src_json = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    # 1️⃣ build & save master document (af_availtimetable) --------------------
    master_payload, (y, m, d) = _build_master_payload(src_json)

    _upsert(
        "lcsd",
        "af_availtimetable",
        None, None, None,          # tertiary / quaternary / quinary
        y, m, d,
        master_payload,
    )
    master_id = _item_id("lcsd", "af_availtimetable", None, None, None, y, m, d)

    # 2️⃣ save each record as af_excel_timetable ------------------------------
    records: List[Dict] = src_json.get("records", [])
    saved = 0
    for rec in records:
        lcsd_num = rec.get("lcsd_number")
        if not lcsd_num:
            continue
        _upsert(
            "lcsd",
            "af_excel_timetable",
            lcsd_num,
            None, None,
            y, m, d,
            rec,
        )
        saved += 1

    return {
        "status":            "success",
        "master_item_id":    master_id,
        "excel_docs_saved":  saved,
        "timestamp_hkt":     master_payload["metadata"]["timestamp"],
    }

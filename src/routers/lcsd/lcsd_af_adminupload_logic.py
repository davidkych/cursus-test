# ── src/routers/lcsd/lcsd_af_adminupload_logic.py ───────────────────────────
"""
Backend logic for the *admin upload* of LCSD timetables.

Route
    POST /api/lcsd/lcsd_af_adminupload_timetable   (multipart/form-data; JSON file)
Workflow
    1.  Read the uploaded JSON (see README in user story).
    2.  Derive the “avail-timetable” meta-JSON (same structure as
        /api/lcsd/lcsd_af_timetable_probe output) and save it:
            tag='lcsd', secondary_tag='af_availtimetable'
    3.  For every *record* inside the upload, save it as an individual
        “excel-timetable” doc:
            tag='lcsd', secondary_tag='af_excel_timetable',
            tertiary_tag=<lcsd_number>
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, HTTPException, UploadFile
from azure.cosmos import exceptions as cosmos_exc

# Re-use the Cosmos helpers already wired up by /api/json
from routers.jsondata.endpoints import _upsert   # type: ignore

TAG = "lcsd"
SEC_AVAIL = "af_availtimetable"
SEC_EXCEL = "af_excel_timetable"

router = APIRouter()


def _save_avail(payload: Dict, ts: datetime) -> None:
    """Upsert *avail-timetable* JSON."""
    _upsert(
        TAG, SEC_AVAIL, None, None, None,
        ts.year, ts.month, ts.day,
        payload,
    )


def _save_excel(record: Dict, ts: datetime) -> None:
    """Upsert one *excel-timetable* JSON."""
    lcsd_num = record.get("lcsd_number")
    _upsert(
        TAG, SEC_EXCEL, lcsd_num, None, None,
        ts.year, ts.month, ts.day,
        record,
    )


@router.post("/api/lcsd/lcsd_af_adminupload_timetable",
             summary="Admin upload LCSD timetable JSON → Cosmos DB")
async def adminupload_timetable(file: UploadFile = File(...)) -> Dict:
    """
    Accept an *aggregate* timetable JSON, decompose it, and save all parts to
    Cosmos DB.  Returns a summary of what was stored.
    """
    try:
        raw = await file.read()
        data_root = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON file") from exc

    if not isinstance(data_root, dict) or "metadata" not in data_root \
            or "records" not in data_root:
        raise HTTPException(status_code=400, detail="Unexpected JSON schema")

    metadata = data_root["metadata"]
    records: List[Dict] = data_root["records"]

    # ── derive timestamp (HKT → local date parts) ───────────────────────────
    try:
        ts = datetime.fromisoformat(metadata["timestamp"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Bad timestamp format") from exc
    ts_hkt = ts.astimezone(ZoneInfo("Asia/Hong_Kong"))

    # ── build *avail-timetable* aggregate ───────────────────────────────────
    facilities: List[Dict] = []
    did_set = set()
    for rec in records:
        did_set.add(rec.get("did_number"))
        facilities.append(
            {
                "did_number":   rec.get("did_number"),
                "lcsd_number":  rec.get("lcsd_number"),
                "name":         rec.get("name"),
                "jogging_schedule": [
                    {
                        "month_year": rec.get("month_year"),
                        "excel_url":  rec.get("excel_url"),
                        **({"pdf_url": rec["pdf_url"]} if "pdf_url" in rec else {}),
                    }
                ],
            }
        )

    avail_payload = {
        "metadata": {
            "timestamp":       ts_hkt.isoformat(timespec="seconds"),
            "num_dids":        len(did_set),
            "num_facilities":  len(facilities),
        },
        "facilities": facilities,
    }

    # ── save everything to Cosmos DB (with upsert) ──────────────────────────
    try:
        _save_avail(avail_payload, ts_hkt)
        for rec in records:
            _save_excel(rec, ts_hkt)
    except cosmos_exc.CosmosHttpResponseError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cosmos DB write failed: {exc.message}",
        ) from exc

    return {
        "status":          "success",
        "upload_filename": file.filename,
        "timestamp_hkt":   ts_hkt.isoformat(timespec="seconds"),
        "docs_saved": {
            "avail_timetable": 1,
            "excel_timetable": len(records),
        },
    }

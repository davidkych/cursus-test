# ── src/routers/lcsd/lcsd_af_excel_timetable.py ─────────────────────────────
"""
Public endpoint
    /api/lcsd/lcsd_af_excel_timetable   (GET | POST)

Workflow
────────
1.  Fetch the **newest** JSON created by `/api/lcsd/lcsd_af_timetable_probe`
    (tag = `lcsd`, secondary_tag = `af_availtimetable`).

2.  For every facility listed there and for each month-entry:
      • try to download & parse the **Excel** (excel_url) via
        `excel_to_timetable()`.  
      • **If that fails** *and* a `pdf_url` is available for the same
        month, fall back to `pdf_to_timetable()`.

3.  Save **one JSON per worksheet/page** back to Cosmos DB using the
    existing helper:
        tag            = 'lcsd'
        secondary_tag  = 'af_excel_timetable'  (or pdf payload – name kept)
        tertiary_tag   = <lcsd_number>
        year/month/day = date when this endpoint runs

4.  After completing its own work fire-and-forget a POST to
        `/api/lcsd/lcsd_cleanup_validator_scheduler`
    (unchanged behaviour).

Response
────────
    {
      "status": "success",
      "timestamp_hkt": "2025-07-14T09:32:10+08:00",
      "docs_saved":    123,
      "docs_skipped":  7,
      "errors": [
        {
          "type":  "excel",
          "url":   "https://…/1060_Field Timetable_6_2025.xlsx",
          "error": "HTTP 404: Not Found"
        },
        {
          "type":  "pdf",
          "url":   "https://…/1060_Field Timetable_6_2025.pdf",
          "error": "pdfplumber.PDFSyntaxError: No /Root object!"
        }
      ]
    }
"""
from __future__ import annotations

import os
from datetime import datetime, date
from typing import List, Dict, Any
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, HTTPException, Query
from azure.cosmos import exceptions as cosmos_exc

# ── shared helpers (reuse existing Cosmos wiring) ───────────────────────────
from routers.jsondata.endpoints import (
    _container,            # Cosmos client – partition key 'lcsd'
    _upsert,               # save helper
    _item_id,              # build ID helper
)

from .lcsd_util_excel_timetable_parser import excel_to_timetable
from .lcsd_util_pdf_timetable_parser   import pdf_to_timetable

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _today_hkt() -> date:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).date()


def _load_latest_avail_json() -> Dict[str, Any]:
    """
    Return the *data* field of the most-recent
        tag='lcsd', secondary_tag='af_availtimetable'
    document in Cosmos DB (same partition, so no cross-partition query).
    """
    query = """
        SELECT c.id, c.data, c.year, c.month, c.day
        FROM   c
        WHERE  c.tag = @tag AND c.secondary_tag = @sec
    """
    params = [
        {"name": "@tag", "value": "lcsd"},
        {"name": "@sec", "value": "af_availtimetable"},
    ]
    items = list(
        _container.query_items(
            query=query,
            parameters=params,
            partition_key="lcsd",           # single-partition query
            enable_cross_partition_query=False,
        )
    )
    if not items:
        raise HTTPException(
            status_code=404,
            detail="No 'af_availtimetable' data found in Cosmos DB.",
        )

    # newest first
    items.sort(
        key=lambda r: (r.get("year", 0), r.get("month", 0), r.get("day", 0)),
        reverse=True,
    )
    return items[0]["data"]


def _save_record(payload: Dict[str, Any], today: date) -> None:
    """
    Save one timetable JSON back into Cosmos DB.
    Overwrites (upserts) if the same ID already exists.
    """
    _upsert(
        "lcsd",                      # tag  (partition key)
        "af_excel_timetable",        # secondary_tag  (kept for pdf too)
        payload.get("lcsd_number"),  # tertiary_tag
        None, None,                  # quaternary / quinary
        today.year,
        today.month,
        today.day,
        payload,
    )


def _internal_base() -> str:
    """
    Resolve the FastAPI base-URL without hard-coding, mirroring logic used
    elsewhere in the code-base.
    """
    if (base := os.getenv("WEBAPP_BASE_URL")):
        return base.rstrip("/")
    if (site := os.getenv("FASTAPI_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    if (site := os.getenv("WEBAPP_SITE_NAME") or os.getenv("WEBSITE_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    return "http://localhost:8000"


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI route
# ─────────────────────────────────────────────────────────────────────────────
@router.api_route(
    "/api/lcsd/lcsd_af_excel_timetable",
    methods=["GET", "POST"],
    summary="Harvest LCSD jogging timetables (Excel/PDF) and save to Cosmos DB",
)
def lcsd_af_excel_timetable(
    timeout: int = Query(15, ge=5,  le=60, description="Per-download timeout (s)"),
    debug:   bool = Query(False,      description="Verbose stdout logging"),
) -> Dict[str, Any]:
    """
    • Download & parse Excel timetables;  
    • fall back to PDF parsing on per-sheet basis when Excel fails;  
    • save results to Cosmos DB;  
    • kick off the clean-up / validator scheduler.
    """
    try:
        avail_data = _load_latest_avail_json()
    except HTTPException:
        raise
    except cosmos_exc.CosmosHttpResponseError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cosmos DB query failed: {exc.message}",
        ) from exc

    today   = _today_hkt()
    saved   = 0             # JSON docs written
    skipped = 0             # worksheets/pages skipped after both attempts
    errors  = []            # detailed error log

    for fac in avail_data.get("facilities", []):
        fac_info = {
            "did_number":  fac.get("did_number"),
            "lcsd_number": fac.get("lcsd_number"),
            "name":        fac.get("name"),
        }
        for sched in fac.get("jogging_schedule", []):
            excel_url = sched.get("excel_url")
            pdf_url   = sched.get("pdf_url")
            mm        = sched.get("month_year")
            if not mm or (not excel_url and not pdf_url):
                continue

            parsed: List[Dict[str, Any]] = []
            # 1️⃣ try Excel first ------------------------------------------------
            if excel_url:
                try:
                    parsed = excel_to_timetable(
                        excel_url,
                        mm,
                        timeout=timeout,
                        debug=debug,
                    )
                except Exception as exc:        # noqa: BLE001
                    errors.append(
                        {"type": "excel", "url": excel_url, "error": str(exc)}
                    )

            # 2️⃣ fallback to PDF if Excel failed ------------------------------
            if not parsed and pdf_url:
                try:
                    parsed = pdf_to_timetable(
                        pdf_url,
                        mm,
                        timeout=timeout,
                        debug=debug,
                    )
                except Exception as exc:        # noqa: BLE001
                    errors.append(
                        {"type": "pdf", "url": pdf_url, "error": str(exc)}
                    )

            # 3️⃣ persist or record skip ---------------------------------------
            if parsed:
                for sheet in parsed:
                    payload = {**fac_info, **sheet}
                    _save_record(payload, today)
                    saved += 1
            else:
                skipped += 1

    # ── build response first ──────────────────────────────────────────────────
    resp: Dict[str, Any] = {
        "status":        "success",
        "timestamp_hkt": datetime.now(ZoneInfo("Asia/Hong_Kong"))
                             .isoformat(timespec="seconds"),
        "docs_saved":    saved,
        "docs_skipped":  skipped,
        "errors":        errors,
    }

    # ── fire-and-forget clean-up / validator scheduler ───────────────────────
    try:
        requests.post(
            f"{_internal_base()}/api/lcsd/lcsd_cleanup_validator_scheduler",
            timeout=5,
        )
    except Exception:
        # non-blocking by design – swallow any error
        pass

    return resp

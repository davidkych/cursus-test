# ── src/routers/lcsd/lcsd_af_excel_timetable.py ─────────────────────────────
"""
Public endpoint
    /api/lcsd/lcsd_af_excel_timetable   (GET | POST)

Updated behaviour (2025-07-14)
──────────────────────────────
* Supports **multiple jogging_schedule entries** per facility (one per
  month/ year).
* Every schedule is parsed (Excel first, PDF fallback) **independently**.
* Saved-document date logic:
      • If month_year == today(HKT) → year/month/day = today
      • Else                        → year/month/day = YYYY/MM/01
* Response payload now reports detailed counters:

        {
          "status": "success",
          "timestamp_hkt": "...",
          "currentmonthdoc_excel_parsedsaved": 7,
          "currentmonthdoc_pdf_parsedsaved":   2,
          "othermonthdoc_excel_parsedsaved":   11,
          "othermonthdoc_pdf_parsedsaved":     4,
          "docs_excel_failed": [...],
          "docs_pdf_failed":   [...],
          "errors": [...]
        }

Unchanged pieces
~~~~~~~~~~~~~~~~
* Fire-and-forget clean-up/validator scheduler call at the end.
* Underlying Excel/PDF parser helpers – untouched.
"""
from __future__ import annotations

import os
from datetime import datetime, date
from typing import List, Dict, Any, Tuple
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
    document in Cosmos DB (single-partition query).
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
            partition_key="lcsd",
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


def _save_record(payload: Dict[str, Any], save_date: date) -> None:
    """
    Persist one timetable JSON into Cosmos DB.
    Overwrites (upserts) if the same ID already exists.
    """
    _upsert(
        "lcsd",                      # tag  (partition key)
        "af_excel_timetable",        # secondary_tag
        payload.get("lcsd_number"),  # tertiary_tag
        None, None,                  # quaternary / quinary
        save_date.year,
        save_date.month,
        save_date.day,
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


def _parse_month_year(mm: str) -> Tuple[int, int]:
    """
    '6/2025' → (2025, 6) handling leading zeros & whitespace.
    """
    mm = mm.strip()
    if "/" not in mm:
        raise ValueError(f"Invalid month_year '{mm}'")
    month_part, year_part = mm.split("/", 1)
    month = int(month_part.lstrip("0") or "0")
    year = int(year_part)
    return year, month


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
    • For **every** jogging_schedule entry (month/year) in the latest
      avail-timetable JSON:
         – try Excel, fall back to PDF;
         – save parsed JSON(s) to Cosmos DB with date logic defined above.
    • Return extended statistics (see module docstring).
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

    today          = _today_hkt()
    cur_year       = today.year
    cur_month      = today.month

    # counters ----------------------------------------------------------------
    cur_excel_saved   = 0
    cur_pdf_saved     = 0
    other_excel_saved = 0
    other_pdf_saved   = 0

    failed_excel_urls: List[str] = []
    failed_pdf_urls:   List[str] = []
    errors: List[Dict[str, Any]] = []

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

            # guard – missing month/year or links -----------------------------
            if not mm or (not excel_url and not pdf_url):
                continue

            try:
                tgt_year, tgt_month = _parse_month_year(mm)
            except ValueError:
                continue  # skip malformed entry

            is_current_month = (tgt_year == cur_year and tgt_month == cur_month)
            # determine the date under which docs will be stored
            save_date = today if is_current_month else date(tgt_year, tgt_month, 1)

            parsed: List[Dict[str, Any]] = []
            used_parser: str | None = None

            # 1️⃣ Excel first --------------------------------------------------
            if excel_url:
                try:
                    parsed = excel_to_timetable(
                        excel_url,
                        mm,
                        timeout=timeout,
                        debug=debug,
                    )
                    if parsed:
                        used_parser = "excel"
                except Exception as exc:        # noqa: BLE001
                    err_txt = str(exc)
                    errors.append({"type": "excel", "url": excel_url, "error": err_txt})
                    failed_excel_urls.append(excel_url)
                    if debug:
                        print(f"[ERROR] Excel fail → {err_txt}")

            # 2️⃣ PDF fallback if Excel produced nothing ----------------------
            if not parsed and pdf_url:
                try:
                    parsed = pdf_to_timetable(
                        pdf_url,
                        mm,
                        timeout=timeout,
                        debug=debug,
                    )
                    if parsed:
                        used_parser = "pdf"
                except Exception as exc:        # noqa: BLE001
                    err_txt = str(exc)
                    errors.append({"type": "pdf", "url": pdf_url, "error": err_txt})
                    failed_pdf_urls.append(pdf_url)
                    if debug:
                        print(f"[ERROR] PDF fail → {err_txt}")

            # 3️⃣ persist & update counters -----------------------------------
            if parsed and used_parser:
                for sheet in parsed:
                    payload = {**fac_info, **sheet}
                    _save_record(payload, save_date)

                    if used_parser == "excel":
                        if is_current_month:
                            cur_excel_saved += 1
                        else:
                            other_excel_saved += 1
                    else:
                        if is_current_month:
                            cur_pdf_saved += 1
                        else:
                            other_pdf_saved += 1

    # ── assemble response ───────────────────────────────────────────────────
    resp: Dict[str, Any] = {
        "status": "success",
        "timestamp_hkt": datetime.now(ZoneInfo("Asia/Hong_Kong"))
                             .isoformat(timespec="seconds"),
        "currentmonthdoc_excel_parsedsaved": cur_excel_saved,
        "currentmonthdoc_pdf_parsedsaved":   cur_pdf_saved,
        "othermonthdoc_excel_parsedsaved":   other_excel_saved,
        "othermonthdoc_pdf_parsedsaved":     other_pdf_saved,
        "docs_excel_failed": failed_excel_urls,
        "docs_pdf_failed":   failed_pdf_urls,
        "errors":            errors,
    }

    # ── fire-and-forget clean-up / validator scheduler (unchanged) ───────────
    try:
        requests.post(
            f"{_internal_base()}/api/lcsd/lcsd_cleanup_validator_scheduler",
            timeout=5,
        )
    except Exception:
        pass  # non-blocking

    return resp

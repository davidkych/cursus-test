# ── src/routers/lcsd/lcsd_af_excel_timetable.py ─────────────────────────────
"""
Public endpoint
    /api/lcsd/lcsd_af_excel_timetable   (GET | POST)

Extended 2025-07-14
───────────────────
* Handles **multiple** jogging-schedule entries per facility.
* Saves timetables using a dynamic YYYY/MM/DD:
      · current month/year  →  today’s HKT date (legacy),
      · other months        →  the schedule’s year/month with day = 1.
* Detailed counters for Excel/PDF successes & failures, split into
  *current* vs *other* month buckets.

Response
────────
    {
      "status": "success",
      "timestamp_hkt": "2025-07-14T10:05:34+08:00",
      "currentmonthdoc_excel_parsedsaved":  98,
      "currentmonthdoc_pdf_parsedsaved":     4,
      "othermonthdoc_excel_parsedsaved":   176,
      "othermonthdoc_pdf_parsedsaved":      12,
      "docs_excel_failed": [ … ],
      "docs_pdf_failed":   [ … ],
      "docs_skipped": 7,
      "skipped_details": [ … ],
      "errors": [ … ]
    }
"""
from __future__ import annotations

import os
from datetime import datetime, date
from typing import List, Dict, Any, Tuple
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, HTTPException, Query
from azure.cosmos import exceptions as cosmos_exc

# ── shared helpers ──────────────────────────────────────────────────────────
from routers.jsondata.endpoints import (
    _container,            # Cosmos client – partition key 'lcsd'
    _upsert,               # save helper
)

from .lcsd_util_excel_timetable_parser import excel_to_timetable
from .lcsd_util_pdf_timetable_parser   import pdf_to_timetable

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _today_hkt() -> date:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).date()


def _parse_month_year(mm_str: str) -> Tuple[int, int]:
    """'07/2025' → (7, 2025)"""
    month_txt, year_txt = (p.strip() for p in mm_str.split("/", 1))
    return int(month_txt.lstrip("0") or "0"), int(year_txt)


def _save_record(payload: Dict[str, Any], save_date: date) -> None:
    """Upsert one timetable JSON into Cosmos DB."""
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
    """Return the service base-URL without hard-coding."""
    if (base := os.getenv("WEBAPP_BASE_URL")):
        return base.rstrip("/")
    if (site := os.getenv("FASTAPI_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    if (site := os.getenv("WEBAPP_SITE_NAME") or os.getenv("WEBSITE_SITE_NAME")):
        return f"https://{site}.azurewebsites.net"
    return "http://localhost:8000"


def _load_latest_avail_json() -> Dict[str, Any]:
    """Fetch the most-recent af_availtimetable doc from Cosmos DB."""
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
    items.sort(
        key=lambda r: (r.get("year", 0), r.get("month", 0), r.get("day", 0)),
        reverse=True,
    )
    return items[0]["data"]


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
    try:
        avail_data = _load_latest_avail_json()
    except HTTPException:
        raise
    except cosmos_exc.CosmosHttpResponseError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cosmos DB query failed: {exc.message}",
        ) from exc

    today        = _today_hkt()
    cur_month    = today.month
    cur_year     = today.year

    # counters & trackers -----------------------------------------------------
    cur_excel_saved   = cur_pdf_saved = 0
    other_excel_saved = other_pdf_saved = 0
    excel_fail_urls: List[str] = []
    pdf_fail_urls:   List[str] = []
    errors:   List[Dict[str, Any]] = []
    skipped_details: List[Dict[str, Any]] = []

    # ─────────────────────────── main loop ───────────────────────────────────
    for fac in avail_data.get("facilities", []):
        fac_info = {
            "did_number":  fac.get("did_number"),
            "lcsd_number": fac.get("lcsd_number"),
            "name":        fac.get("name"),
        }
        for sched in fac.get("jogging_schedule", []):
            mm_str    = sched.get("month_year")
            excel_url = sched.get("excel_url")
            pdf_url   = sched.get("pdf_url")

            if not mm_str or (not excel_url and not pdf_url):
                skipped_details.append({**fac_info, "month_year": mm_str,
                                        "reason": "No month_year or links present"})
                continue

            try:
                sched_month, sched_year = _parse_month_year(mm_str)
            except ValueError:
                skipped_details.append({**fac_info, "month_year": mm_str,
                                        "reason": "Malformed month_year"})
                continue

            is_current = (sched_month == cur_month and sched_year == cur_year)
            save_date  = today if is_current else date(sched_year, sched_month, 1)

            parsed: List[Dict[str, Any]] = []
            parser_used: str | None = None

            # ① Excel first ---------------------------------------------------
            if excel_url:
                try:
                    parsed = excel_to_timetable(excel_url, mm_str,
                                                timeout=timeout, debug=debug)
                    if parsed:
                        parser_used = "excel"
                except Exception as exc:                       # noqa: BLE001
                    errors.append({"type": "excel", "url": excel_url,
                                   "error": str(exc)})
                    excel_fail_urls.append(excel_url)
                    if debug:
                        print(f"[ERROR] Excel fail → {exc}")

            # ② PDF fallback --------------------------------------------------
            if not parsed and pdf_url:
                try:
                    parsed = pdf_to_timetable(pdf_url, mm_str,
                                              timeout=timeout, debug=debug)
                    if parsed:
                        parser_used = "pdf"
                except Exception as exc:                       # noqa: BLE001
                    errors.append({"type": "pdf", "url": pdf_url,
                                   "error": str(exc)})
                    pdf_fail_urls.append(pdf_url)
                    if debug:
                        print(f"[ERROR] PDF fail → {exc}")

            # ③ persist or record skip ---------------------------------------
            if parsed:
                for sheet in parsed:
                    payload = {**fac_info, **sheet}
                    _save_record(payload, save_date)

                if parser_used == "excel":
                    (cur_excel_saved if is_current else other_excel_saved) += len(parsed)
                elif parser_used == "pdf":
                    (cur_pdf_saved if is_current else other_pdf_saved) += len(parsed)
            else:
                skipped_details.append({**fac_info, "month_year": mm_str,
                                        "excel_url": excel_url, "pdf_url": pdf_url,
                                        "reason": "No timetable parsed"})

    # ─────────────────────────── response ────────────────────────────────────
    resp: Dict[str, Any] = {
        "status": "success",
        "timestamp_hkt": datetime.now(ZoneInfo("Asia/Hong_Kong"))
                             .isoformat(timespec="seconds"),
        "currentmonthdoc_excel_parsedsaved":  cur_excel_saved,
        "currentmonthdoc_pdf_parsedsaved":    cur_pdf_saved,
        "othermonthdoc_excel_parsedsaved":    other_excel_saved,
        "othermonthdoc_pdf_parsedsaved":      other_pdf_saved,
        "docs_excel_failed": excel_fail_urls,
        "docs_pdf_failed":   pdf_fail_urls,
        "docs_skipped":      len(skipped_details),
        "skipped_details":   skipped_details,
        "errors":            errors,
    }

    # fire-and-forget clean-up / validator scheduler -------------------------
    try:
        requests.post(f"{_internal_base()}/api/lcsd/lcsd_cleanup_validator_scheduler",
                      timeout=5)
    except Exception:
        pass  # non-blocking

    return resp

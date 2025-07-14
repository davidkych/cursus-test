# ── src/routers/lcsd/lcsd_af_excel_timetable.py ─────────────────────────────
"""
Public endpoint
    /api/lcsd/lcsd_af_excel_timetable   (GET | POST)

Changes (2025-07-14)
────────────────────
* Supports **multiple** jogging-schedule entries per facility.
* Saves JSON for the *current* HKT month/day **or** for the month/year
  specified by each schedule (day = 1) depending on match.
* Extended response payload – see bottom of this file.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Any, Dict, List, Tuple
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
_MONTH_YEAR_RE = re.compile(r"^\s*0?(?P<month>\d{1,2})\s*[/\-]\s*(?P<year>\d{4})\s*$")


def _today_hkt() -> date:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).date()


def _parse_month_year(s: str) -> Tuple[int, int]:
    """
    Convert «M/YYYY» or «MM-YYYY» (with optional leading zero) → (month, year).
    Raises `ValueError` on invalid input.
    """
    m = _MONTH_YEAR_RE.match(s)
    if not m:
        raise ValueError(f"Invalid month_year string: {s!r}")
    return int(m.group("month")), int(m.group("year"))


def _load_latest_avail_json() -> Dict[str, Any]:
    """
    Return the *data* field of the most-recent
        tag='lcsd' AND secondary_tag='af_availtimetable'
    document in Cosmos DB.
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


def _save_record(
    payload: Dict[str, Any],
    *,
    year: int,
    month: int,
    day: int,
) -> None:
    """
    Save one timetable JSON back into Cosmos DB.
    Chooses partition/ID scheme identical to legacy behaviour, but allows
    caller-supplied Y/M/D.
    """
    _upsert(
        "lcsd",                      # tag (partition key)
        "af_excel_timetable",        # secondary_tag
        payload.get("lcsd_number"),  # tertiary_tag
        None, None,                  # quaternary / quinary
        year,
        month,
        day,
        payload,
    )


def _internal_base() -> str:
    """
    Resolve the FastAPI base-URL without hard-coding.
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
    • fall back to PDF parsing when Excel fails;  
    • save results to Cosmos DB using date rules described below;  
    • trigger the clean-up / validator scheduler.

    Save-date rules
    ───────────────
    * If `month_year` equals the *current* HKT month/year → save with **today’s**
      year/month/day (legacy behaviour).
    * Otherwise → save with the month/year indicated by `month_year` and
      **day = 1**.
    """

    # ── fetch source JSON ────────────────────────────────────────────────────
    try:
        avail_data = _load_latest_avail_json()
    except HTTPException:
        raise
    except cosmos_exc.CosmosHttpResponseError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cosmos DB query failed: {exc.message}",
        ) from exc

    today = _today_hkt()
    cur_m, cur_y = today.month, today.year

    # counters & accumulators -------------------------------------------------
    cur_excel_saved   = 0
    cur_pdf_saved     = 0
    other_excel_saved = 0
    other_pdf_saved   = 0

    excel_failed: List[str] = []
    pdf_failed:   List[str] = []
    errors:       List[Dict[str, str]] = []

    # ── main loop over facilities & schedules ────────────────────────────────
    for fac in avail_data.get("facilities", []):
        fac_info = {
            "did_number":  fac.get("did_number"),
            "lcsd_number": fac.get("lcsd_number"),
            "name":        fac.get("name"),
        }

        for sched in fac.get("jogging_schedule", []):
            mm_yy   = sched.get("month_year")
            excel_url = sched.get("excel_url")
            pdf_url   = sched.get("pdf_url")

            # guard – month_year mandatory for processing
            if not mm_yy:
                continue

            try:
                sched_m, sched_y = _parse_month_year(mm_yy)
            except ValueError:
                continue  # malformed month_year – skip silently

            is_current = (sched_m == cur_m and sched_y == cur_y)
            save_year, save_month, save_day = (
                (today.year, today.month, today.day)
                if is_current
                else (sched_y, sched_m, 1)
            )

            parsed: List[Dict[str, Any]] = []
            src_type: str | None = None  # "excel" | "pdf"

            # ── 1️⃣ try Excel first ────────────────────────────────────────
            if excel_url:
                try:
                    parsed = excel_to_timetable(
                        excel_url,
                        mm_yy,
                        timeout=timeout,
                        debug=debug,
                    )
                    src_type = "excel"
                except Exception as exc:           # noqa: BLE001
                    err_txt = str(exc)
                    errors.append(
                        {"type": "excel", "url": excel_url, "error": err_txt}
                    )
                    excel_failed.append(excel_url)
                    if debug:
                        print(f"[ERROR] Excel fail → {err_txt}")

            # ── 2️⃣ fallback to PDF ─────────────────────────────────────────
            if not parsed and pdf_url:
                try:
                    parsed = pdf_to_timetable(
                        pdf_url,
                        mm_yy,
                        timeout=timeout,
                        debug=debug,
                    )
                    src_type = "pdf"
                except Exception as exc:           # noqa: BLE001
                    err_txt = str(exc)
                    errors.append(
                        {"type": "pdf", "url": pdf_url, "error": err_txt}
                    )
                    pdf_failed.append(pdf_url)
                    if debug:
                        print(f"[ERROR] PDF fail → {err_txt}")

            # ── 3️⃣ persist results ────────────────────────────────────────
            if parsed:
                for sheet in parsed:
                    payload = {**fac_info, **sheet}
                    _save_record(
                        payload,
                        year=save_year,
                        month=save_month,
                        day=save_day,
                    )

                if src_type == "excel":
                    if is_current:
                        cur_excel_saved   += len(parsed)
                    else:
                        other_excel_saved += len(parsed)
                elif src_type == "pdf":
                    if is_current:
                        cur_pdf_saved   += len(parsed)
                    else:
                        other_pdf_saved += len(parsed)

    # ── assemble response payload ────────────────────────────────────────────
    resp: Dict[str, Any] = {
        "status":                  "success",
        "timestamp_hkt":           datetime.now(ZoneInfo("Asia/Hong_Kong"))
                                        .isoformat(timespec="seconds"),
        "currentmonthdoc_excel_parsedsaved": cur_excel_saved,
        "currentmonthdoc_pdf_parsedsaved":   cur_pdf_saved,
        "othermonthdoc_excel_parsedsaved":   other_excel_saved,
        "othermonthdoc_pdf_parsedsaved":     other_pdf_saved,
        "docs_excel_failed":                 excel_failed,
        "docs_pdf_failed":                   pdf_failed,
        "errors":                            errors,
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

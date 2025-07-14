# ── src/routers/lcsd/lcsd_util_pdf_timetable_parser.py ───────────────────────
"""
lcsd_util_pdf_timetable_parser.py
=================================
Light-weight helper that converts an LCSD *Field / Jogging Timetable* PDF
into the same JSON-ready structure produced by `excel_to_timetable()`.

Only the minimum code paths needed by the `/api/lcsd/lcsd_af_excel_timetable`
endpoint are retained.  All internal logging is optional (via *debug* flag).

Public API
~~~~~~~~~~
    pdf_to_timetable(pdf_source: str,
                     month_year: str,
                     *,
                     timeout: int = 15,
                     debug: bool = False) -> list[dict]

Return value – list [dict] each representing **one PDF page**:

    {
        "month_year":  "6/2025",
        "pdf_url":     "<url-or-path>",
        "source":      "pdf",
        "sha256":      "<hex-digest>",
        "timetable":   {
            "YYYY-MM-DD": [
                {"start": "07:00", "end": "08:00", "status": "A"},
                …
            ],
            …
        },
        "legend_map":  { "A": "Available", … },
        "closure_detail": {}               # reserved – may be empty
    }
"""
from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import re as _re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests as _requests
import pdfplumber                          # type: ignore

# ─────────────────────────────────────────────────────────────────────────────
# Optional helper – closure detail extractor (best-effort import)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from lcsd_pdf_timetable_converter_maintainence import (  # type: ignore
        extract_closure_detail as _extract_closure_detail,   # noqa: WPS433
    )
except ImportError:          # helper missing → graceful fallback
    def _extract_closure_detail(*_a: Any, **_kw: Any) -> Dict[str, List[dict]]:  # type: ignore
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# Regex helpers
# ─────────────────────────────────────────────────────────────────────────────
_CODE_RE          = _re.compile(r"\b([A-Z])\b")
_CID_RE           = _re.compile(r"\(cid:\d+\)")
_CAL_START_RE     = _re.compile(r"^\s*日期\s+Date", _re.I)
_DAY_TRAIL_RE     = _re.compile(r"(?:\s+\d{1,2})+\s*$")
_HEADER_NOISE_RE  = _re.compile(r"^\s*(Sports\s+Ground|Opening\s+Hour)", _re.I)
_TIME_ROW_RE      = _re.compile(r"^\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s+(.*)$")
_TITLE_RE         = _re.compile(r"(主場|副場|Main Field|Secondary Field)")

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _download_pdf(source: str, *, timeout: int) -> bytes:
    if source.startswith(("http://", "https://")):
        resp = _requests.get(source, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    return Path(source).read_bytes()


def _sha256_digest(data: bytes) -> str:
    return _hashlib.sha256(data).hexdigest()


def _extract_legend(lines: List[str]) -> Dict[str, str]:
    legend: Dict[str, str] = {}
    cur: str | None = None
    for raw in lines:
        cleaned = _CID_RE.sub("", raw).strip()
        if not cleaned:
            continue
        if _CAL_START_RE.match(cleaned):
            break

        matches = list(_CODE_RE.finditer(cleaned))
        if matches:
            codes = [m.group(1) for m in matches]
            after = cleaned[matches[-1].end():].strip(" ：:.-\t ")
            for c in codes:
                legend[c] = after or legend.get(c, "")
                cur = c
            continue

        if cur:
            legend[cur] = (legend[cur] + " " + cleaned).strip()

    # clean trailing “ …  1 2 3” artefacts
    cleaned_legend: Dict[str, str] = {}
    for k, v in legend.items():
        v = _re.sub(r"\s+", " ", v)
        v = _DAY_TRAIL_RE.sub("", v).strip()
        if v and not _HEADER_NOISE_RE.match(v):
            cleaned_legend[k] = v
    return cleaned_legend


def _augment_L(lines: List[str], legend: Dict[str, str]) -> None:
    """
    If code 'L' exists but the PDF lists a verbose *lane-closure* note
    elsewhere, merge that detail into the legend entry.
    """
    if "L" not in legend or "為配合" in legend["L"]:
        return

    blob = "\n".join(lines)
    chi = _re.search(r"為配合[\S ]+?號線道給公眾人士作緩跑之用。", blob)
    eng = _re.search(r"Jogging will be confined[\S ]+?ball games\.", blob)
    note = " ".join(f.group(0) for f in (chi, eng) if f).strip()
    if note:
        legend["L"] = note


def _parse_page(
    lines: List[str], *, month: int, year: int, debug: bool
) -> Tuple[str, Dict[str, Any], Dict[str, str]] | None:
    """
    Parse **one** PDF page.  Returns (sheet_name, timetable, legend) or None
    when page does not contain a timetable.
    """
    first_row = last_row = None
    for idx, line in enumerate(lines):
        if _TIME_ROW_RE.match(line):
            first_row = first_row or idx
            last_row = idx
    if first_row is None:
        return None

    banner = " ".join(lines[:first_row])[:160]
    m_title = _TITLE_RE.search(banner)
    sheet_name = (
        m_title.group(0).strip().replace(" ", "") if m_title else ""
    )  # e.g. "主場"

    legend = _extract_legend(lines[:first_row])

    # timetable grid ---------------------------------------------------------
    labels: List[str] = []
    matrix: List[List[str]] = []
    for line in lines[first_row:]:
        m = _TIME_ROW_RE.match(line)
        if not m:
            if labels:
                break  # reached end of timetable
            continue
        start, _, rest = m.groups()
        labels.append(start)
        matrix.append(rest.strip().split())

    if not matrix:
        return None
    width = max(len(row) for row in matrix)
    for row in matrix:
        row += [""] * (width - len(row))

    first_lbl, last_lbl = labels[0], labels[-1]
    timetable: Dict[str, List[dict]] = {}
    for col in range(width):
        try:
            date_iso = _dt.date(year, month, col + 1).isoformat()
        except ValueError:
            continue
        segments: List[dict] = []
        for row_idx, row in enumerate(matrix):
            status = row[col].strip()
            if not status:
                continue
            start = labels[row_idx]
            end = labels[row_idx + 1] if row_idx + 1 < len(labels) else None
            if end:
                segments.append({"start": start, "end": end, "status": status})

        # merge consecutive identical statuses
        merged: List[dict] = []
        for seg in segments:
            if (
                merged
                and merged[-1]["status"] == seg["status"]
                and merged[-1]["end"] == seg["start"]
            ):
                merged[-1]["end"] = seg["end"]
            else:
                merged.append(seg.copy())

        # fill gaps with default "A"
        filled: List[dict] = []
        if merged:
            if merged[0]["start"] != first_lbl:
                filled.append(
                    {"start": first_lbl, "end": merged[0]["start"], "status": "A"}
                )
            for j, seg in enumerate(merged):
                filled.append(seg)
                if (
                    j + 1 < len(merged)
                    and seg["end"] != merged[j + 1]["start"]
                ):
                    filled.append(
                        {
                            "start": seg["end"],
                            "end": merged[j + 1]["start"],
                            "status": "A",
                        }
                    )
            if merged[-1]["end"] != last_lbl:
                filled.append(
                    {"start": merged[-1]["end"], "end": last_lbl, "status": "A"}
                )
        else:
            filled.append({"start": first_lbl, "end": last_lbl, "status": "A"})
        timetable[date_iso] = filled

    if last_row is not None:
        _augment_L(lines[last_row + 1 :], legend)

    return sheet_name, timetable, legend


# ─────────────────────────────────────────────────────────────────────────────
# Public façade
# ─────────────────────────────────────────────────────────────────────────────
def pdf_to_timetable(
    pdf_source: str,
    month_year: str,
    *,
    timeout: int = 15,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    """
    Convert *pdf_source* (URL or local path) into timetable JSON(s).

    • On success returns list[dict] – one entry per PDF page that contains a
      timetable.  
    • Raises any `requests` / `pdfplumber` / parsing errors to the caller.
    """
    pdf_bytes = _download_pdf(pdf_source, timeout=timeout)
    sha256    = _sha256_digest(pdf_bytes)
    month, year = map(int, month_year.split("/"))

    # closure detail – helper may be absent
    closure_detail = {}
    try:
        closure_detail = _extract_closure_detail(
            pdf_source, month_year, timeout=timeout, debug=debug
        )
    except Exception:
        pass  # non-fatal

    results: List[Dict[str, Any]] = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            text = (page.extract_text() or "").replace("\u3000", " ")
            parsed = _parse_page(
                text.splitlines(), month=month, year=year, debug=debug
            )
            if parsed is None:
                continue
            sheet_name, timetable, legend = parsed
            results.append(
                {
                    "_sheet_name": sheet_name,
                    "_page": page_no,
                    "source": "pdf",
                    "month_year": month_year,
                    "pdf_url": pdf_source,
                    "sha256": sha256,
                    "timetable": timetable,
                    "legend_map": legend,
                    "closure_detail": closure_detail,
                }
            )
    if not results:
        raise ValueError("No timetable found in PDF.")
    return results


__all__ = ["pdf_to_timetable"]

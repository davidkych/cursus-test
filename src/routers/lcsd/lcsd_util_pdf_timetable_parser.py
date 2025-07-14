# ── src/routers/lcsd/lcsd_util_pdf_timetable_parser.py ───────────────────────
"""
Standalone helper that converts an LCSD *Jogging Timetable* **PDF** into the
same JSON-ready structure consumed by ``lcsd_af_excel_timetable``.

Public API
~~~~~~~~~~
    pdf_to_timetable(pdf_source: str,
                     month_year: str,
                     *,
                     timeout: int = 15,
                     debug: bool = False) -> list[dict]

Return value – one dictionary per PDF page:

    {
        "source":         "pdf",
        "month_year":     "7/2025",
        "pdf_url":        "<original-url>",
        "sha256":         "<hex-digest>",
        "timetable":      { "YYYY-MM-DD": [ {start, end, status}, … ], … },
        "legend_map":     { "A": "Available", … },
        "closure_detail": { … }              # may be empty
    }

The implementation is adapted (with silent logging) from the **local** utility
`lcsd_pdf_timetable_converter.py`, trimmed to the minimum required for server
use.  All non-essential CLI scaffolding has been removed.
"""
from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import re as _re
from io import BytesIO as _BytesIO
from typing import Any, Dict, List, Tuple

import requests as _requests
import pdfplumber                       # type: ignore

# ─────────────────────────────────────────────────────────────────────
# Optional closure-detail helper – keep debug output visible to caller
# ─────────────────────────────────────────────────────────────────────
try:
    from lcsd_pdf_timetable_converter_maintainence import extract_closure_detail  # type: ignore
except ImportError:          # helper missing – emit notice once
    def extract_closure_detail(*_a: Any, **_kw: Any) -> Dict[str, List[dict]]:    # type: ignore
        print("[WARN] Maintenance helper not found – 'closure_detail' will be empty.")
        return {}

# ─────────────────────────────────────────────────────────────────────
# I/O helpers
# ─────────────────────────────────────────────────────────────────────
def _download_pdf(source: str, *, timeout: int) -> bytes:
    if source.startswith(("http://", "https://")):
        r = _requests.get(source, timeout=timeout)
        r.raise_for_status()
        return r.content
    with open(source, "rb") as fh:
        return fh.read()


def _sha256_digest(data: bytes) -> str:
    h = _hashlib.sha256()
    h.update(data)
    return h.hexdigest()

# ─────────────────────────────────────────────────────────────────────
# Legend extraction & timetable parsing helpers
# ─────────────────────────────────────────────────────────────────────
_CODE_RE          = _re.compile(r"\b([A-Z])\b")
_CID_RE           = _re.compile(r"\(cid:\d+\)")
_CAL_START_RE     = _re.compile(r"^\s*日期\s+Date", _re.I)
_DAY_TRAIL_RE     = _re.compile(r"(?:\s+\d{1,2})+\s*$")
_HEADER_NOISE_RE  = _re.compile(r"^\s*(Sports\s+Ground|Opening\s+Hour)", _re.I)
_TIME_ROW_RE      = _re.compile(r"^\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s+(.*)$")
_TITLE_RE         = _re.compile(r"(主場|副場|Main Field|Secondary Field)")


def _extract_legend(lines: List[str]) -> Dict[str, str]:
    legend: Dict[str, str] = {}
    cur: str | None = None
    for raw in lines:
        cleaned = _CID_RE.sub("", raw).strip()
        if not cleaned:
            continue
        if _CAL_START_RE.match(cleaned):
            break
        m_iter = list(_CODE_RE.finditer(cleaned))
        if m_iter:
            codes = [m.group(1) for m in m_iter]
            after = cleaned[m_iter[-1].end():].strip(" ：:.-\t ")
            for c in codes:
                legend[c] = after
                cur = c
            if not after:
                continue
            cur = codes[-1]
            continue
        if cur:
            legend[cur] = (legend[cur] + " " + cleaned).strip()

    cleaned: Dict[str, str] = {}
    for k, v in legend.items():
        v = _re.sub(r"\s+", " ", v)
        v = _DAY_TRAIL_RE.sub("", v).strip()
        if v and not _HEADER_NOISE_RE.match(v):
            cleaned[k] = v
    return cleaned


def _augment_L(lines: List[str], legend: Dict[str, str]) -> None:
    """
    Some PDFs describe code 'L' in a trailing paragraph.  If a concise legend
    for 'L' already exists, leave it untouched; otherwise, try to extend it.
    """
    if "L" not in legend or "為配合" in legend["L"]:
        return
    txt = "\n".join(lines)
    m_chi = _re.search(r"為配合[\S ]+?號線道給公眾人士作緩跑之用。", txt)
    m_eng = _re.search(r"Jogging will be confined[\S ]+?ball games\.", txt)
    if m_chi or m_eng:
        legend["L"] = " ".join(f.group(0) for f in (m_chi, m_eng) if f).strip()


def _parse_page(
    lines: List[str], *, month: int, year: int
) -> Tuple[str, Dict[str, Any], Dict[str, str]] | None:
    """
    Parse one PDF page worth of *lines* into:

        (sub-sheet-name, timetable-dict, legend-dict)
    """
    first = last = None
    for i, l in enumerate(lines):
        if _TIME_ROW_RE.match(l):
            first = first or i
            last = i
    if first is None:
        return None

    banner = " ".join(lines[:first])[:160]
    m_title = _TITLE_RE.search(banner)
    sheet_name = (m_title.group(0).strip() if m_title else "").replace(" ", "")
    legend = _extract_legend(lines[:first])

    labels, matrix = [], []
    for l in lines[first:]:
        m = _TIME_ROW_RE.match(l)
        if not m:
            if labels:
                break
            continue
        start, _, rest = m.groups()
        labels.append(start)
        matrix.append(rest.strip().split())

    if not matrix:
        return None

    w = max(len(r) for r in matrix)
    for r in matrix:
        r += [""] * (w - len(r))

    first_lbl, last_lbl = labels[0], labels[-1]
    table: Dict[str, List[dict]] = {}
    for col in range(w):
        try:
            date_iso = _dt.date(year, month, col + 1).isoformat()
        except ValueError:
            continue

        segs: List[dict] = []
        for i, row in enumerate(matrix):
            st = row[col].strip()
            if not st:
                continue
            start = labels[i]
            end = labels[i + 1] if i + 1 < len(labels) else None
            if end:
                segs.append({"start": start, "end": end, "status": st})

        merged: List[dict] = []
        for seg in segs:
            if merged and merged[-1]["status"] == seg["status"] and merged[-1]["end"] == seg["start"]:
                merged[-1]["end"] = seg["end"]
            else:
                merged.append(seg.copy())

        fill: List[dict] = []
        if merged:
            if merged[0]["start"] != first_lbl:
                fill.append({"start": first_lbl, "end": merged[0]["start"], "status": "A"})
            for j, seg in enumerate(merged):
                fill.append(seg)
                if j + 1 < len(merged) and seg["end"] != merged[j + 1]["start"]:
                    fill.append({"start": seg["end"], "end": merged[j + 1]["start"], "status": "A"})
            if merged[-1]["end"] != last_lbl:
                fill.append({"start": merged[-1]["end"], "end": last_lbl, "status": "A"})
        else:
            fill.append({"start": first_lbl, "end": last_lbl, "status": "A"})
        table[date_iso] = fill

    if last is not None:
        _augment_L(lines[last + 1 :], legend)
    return sheet_name, table, legend

# ─────────────────────────────────────────────────────────────────────
# Public façade
# ─────────────────────────────────────────────────────────────────────
def pdf_to_timetable(
    pdf_source: str,
    month_year: str,
    *,
    timeout: int = 15,
    debug: bool = False,          # kept for API symmetry; unused internally
) -> List[Dict[str, Any]]:
    """
    Download *pdf_source*, parse every page, and return a list of timetable
    dictionaries (one per page).  The structure matches the Excel parser with
    additional PDF-specific metadata.
    """
    pdf_bytes = _download_pdf(pdf_source, timeout=timeout)
    sha256    = _sha256_digest(pdf_bytes)

    # closure detail – keep helper verbose
    try:
        closure_detail = extract_closure_detail(
            pdf_bytes, month_year, timeout=timeout, debug=True
        )
    except TypeError:            # helper expects URL/path
        closure_detail = extract_closure_detail(
            pdf_source, month_year, timeout=timeout, debug=True
        )

    month, year = map(int, month_year.split("/"))
    out: List[Dict[str, Any]] = []
    with pdfplumber.open(_BytesIO(pdf_bytes)) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            txt = (page.extract_text() or "").replace("\u3000", " ")
            parsed = _parse_page(txt.splitlines(), month=month, year=year)
            if not parsed:
                continue
            sheet_name, timetable, legend = parsed
            out.append(
                {
                    "source": "pdf",
                    "month_year": month_year,
                    "pdf_url": pdf_source,
                    "sha256": sha256,
                    "timetable": timetable,
                    "legend_map": legend,
                    "_sheet_name": sheet_name,
                    "_page": pno,
                    "closure_detail": closure_detail,
                }
            )
    return out


__all__ = ["pdf_to_timetable"]

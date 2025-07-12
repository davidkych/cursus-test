#!/usr/bin/env python3
"""
lcsd_util_af_probe.py

Generic helper for probing LCSD athletic-field facility pages.

Core function
-------------
probe_dids(start, end, *, base_url=..., ftid=..., error_indicator=..., delay=...)

    • Iterates over DID numbers in the inclusive range [start, end].  
    • Returns a list of DIDs (as **str**) whose pages render real
      facility information (i.e. do **not** show the LCSD error page).

Why a separate module?
----------------------
Designed for reuse in other scripts or notebooks (e.g. the forthcoming
`lcsd_util_af_master.py` and the orchestrator `lcsd_af_info.py`).
Nothing is hard-wired except sensible defaults, so callers can:

    from lcsd_util_af_probe import probe_dids
    valid = probe_dids(0, 20)

Run this file directly to perform the default 0-20 probe and print the
resulting valid DID list.

Author: (your-name-here)
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import List

import requests

# ---------------------------------------------------------------------------
# Default configuration values (can be overridden via function parameters)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL: str = (
    "https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do"
)
DEFAULT_FTID: int = 38  # Facility-type ID for athletic fields
DEFAULT_ERROR_INDICATOR: str = "Sorry, the page you requested cannot be found"
DEFAULT_REQUEST_DELAY: float = 0.1  # polite delay (seconds) between requests
DEFAULT_TIMEOUT: int = 10  # seconds


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _is_valid_page(html: str, error_indicator: str) -> bool:
    """Return **True** when *html* does *not* contain the LCSD error marker."""
    return error_indicator not in html


def _save_json(obj: object, path: Path) -> None:
    """Utility to write *obj* as pretty JSON to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def probe_dids(
    start: int,
    end: int,
    *,
    base_url: str = DEFAULT_BASE_URL,
    ftid: int = DEFAULT_FTID,
    error_indicator: str = DEFAULT_ERROR_INDICATOR,
    delay: float = DEFAULT_REQUEST_DELAY,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> List[str]:
    """
    Probe LCSD athletic-field pages for DIDs in **[start, end]** (inclusive).

    Parameters
    ----------
    start, end : int
        Range of DID values to probe.
    base_url : str, optional
        LCSD facility-details URL (you almost never need to change this).
    ftid : int, optional
        Facility-type ID (38 = athletic fields).
    error_indicator : str, optional
        Sub-string that uniquely appears on LCSD *error* pages.
    delay : float, optional
        Seconds to sleep between successive requests (politeness).
    timeout : int, optional
        Per-request timeout passed to ``requests.get``.
    verbose : bool, optional
        If *True*, prints INFO / DEBUG messages to stdout.

    Returns
    -------
    list[str]
        Sorted list of DID strings that responded with *valid* pages.
    """
    valid: List[str] = []

    for did in range(start, end + 1):
        params = {"ftid": ftid, "fcid": "", "did": did}
        try:
            r = requests.get(base_url, params=params, timeout=timeout)
            r.raise_for_status()
        except requests.RequestException as exc:
            if verbose:
                print(f"[WARN] DID {did}: request failed → {exc}")
            time.sleep(delay)
            continue

        if _is_valid_page(r.text, error_indicator):
            valid.append(str(did))
            if verbose:
                print(f"[INFO] DID {did}: VALID")
        elif verbose:
            print(f"[DEBUG] DID {did}: error page")
        time.sleep(delay)

    return valid


# ---------------------------------------------------------------------------
# Optional CLI behaviour
# ---------------------------------------------------------------------------


def _default_output_filename() -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"{ts}_lcsd_af_probe.json")


def _main() -> None:
    """
    When executed as a script, probe DIDs 0-20 and dump results to JSON.
    """
    print("Probing LCSD athletic-field DIDs 0-20 …")
    dids = probe_dids(0, 20, verbose=True)

    out_file = _default_output_filename()
    payload = {
        "metadata": {"timestamp": datetime.datetime.now().isoformat()},
        "valid_dids": dids,
    }
    _save_json(payload, out_file)
    print(f"✔ Saved {len(dids)} valid DID(s) → {out_file.name}")


if __name__ == "__main__":  # pragma: no cover
    _main()

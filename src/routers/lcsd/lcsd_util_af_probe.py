# ── src/routers/lcsd/lcsd_util_af_probe.py ───────────────────────────────────
"""
Minimal, import-friendly version of the LCSD DID probe helper.
(Original CLI scaffolding removed.)
"""
from __future__ import annotations

from typing import List

import requests
import time

DEFAULT_BASE_URL: str = "https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do"
DEFAULT_FTID: int = 38          # Athletic-field facility-type ID
DEFAULT_ERROR_INDICATOR: str = "Sorry, the page you requested cannot be found"
DEFAULT_REQUEST_DELAY: float = 0.1   # polite delay (seconds)
DEFAULT_TIMEOUT: int = 10            # seconds


def _is_valid_page(html: str, error_indicator: str) -> bool:
    """True when *html* does **not** contain the LCSD error marker."""
    return error_indicator not in html


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

    Returns a **sorted** list of DID strings that responded with valid pages.
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

    return sorted(valid)

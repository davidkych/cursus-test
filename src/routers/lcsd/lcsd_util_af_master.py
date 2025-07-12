# ── src/routers/lcsd/lcsd_util_af_master.py ──────────────────────────────────
"""
Import-friendly wrapper that fetches & parses LCSD athletic-field pages.

Relies on:
    • probe_dids()           – for DID discovery (already imported elsewhere)
    • parse_facilities()     – HTML → list[dict] (in master_parser.py)
"""
from __future__ import annotations

from typing import Iterable, List, Optional

import requests
from bs4 import BeautifulSoup  # transitive dep already in requirements

from .lcsd_util_af_master_parser import parse_facilities

DEFAULT_BASE_URL: str = "https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do"
DEFAULT_FTID: int = 38     # Athletic-field facility-type ID
DEFAULT_TIMEOUT: int = 10  # seconds


def _fetch_page_html(
    did: str | int,
    *,
    base_url: str = DEFAULT_BASE_URL,
    ftid: int = DEFAULT_FTID,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    params = {"ftid": ftid, "fcid": "", "did": did}
    try:
        resp = requests.get(base_url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def fetch_facilities(
    valid_dids: Iterable[str | int],
    *,
    base_url: str = DEFAULT_BASE_URL,
    ftid: int = DEFAULT_FTID,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> List[dict]:
    """
    For every DID in *valid_dids*, download the page and run
    parse_facilities() → aggregated list of facility dicts.
    """
    all_records: List[dict] = []

    for did in valid_dids:
        if verbose:
            print(f"[INFO] DID {did}: fetching…")
        html = _fetch_page_html(did, base_url=base_url, ftid=ftid, timeout=timeout)
        if not html:
            continue
        recs = parse_facilities(html, did=str(did))
        if recs:
            all_records.extend(recs)
            if verbose:
                print(f"       → {len(recs)} facility entry(ies)")
    return all_records

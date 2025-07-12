#!/usr/bin/env python3
"""
lcsd_util_af_master.py
~~~~~~~~~~~~~~~~~~~~~~

Helper for harvesting LCSD athletic-field facility data, *minus* the parsing.

Workflow
--------
1. `_fetch_page_html()` – download one LCSD “Details” page.
2. `parse_facilities()`  – **imported** from lcsd_util_af_master_parser.py
                           (HTML ➜ list[dict]).
3. `fetch_facilities()`  – loop over valid DIDs, aggregate records.
4. `build_master_json()` – dump everything to a timestamped JSON file.

You can still run this file directly for a quick CLI that:
   • asks you to pick a *_lcsd_af_probe.json file,
   • reads its valid_dids,
   • writes a master JSON.

Nothing else changed externally; only the parsing has been moved out.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import Iterable, List, Optional

import requests
from bs4 import BeautifulSoup  # still required for CLI “probe-file preview”
from lcsd_util_af_master_parser import parse_facilities  # ← NEW import

# ---------------------------------------------------------------------------
# Default configuration (callers can override via keyword args)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL: str = (
    "https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do"
)
DEFAULT_FTID: int = 38  # Athletic-field facility-type ID
DEFAULT_TIMEOUT: int = 10  # seconds


# ---------------------------------------------------------------------------
# Networking helper
# ---------------------------------------------------------------------------


def _fetch_page_html(
    did: str | int,
    *,
    base_url: str = DEFAULT_BASE_URL,
    ftid: int = DEFAULT_FTID,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Return HTML text for *did* or **None** on network error."""
    params = {"ftid": ftid, "fcid": "", "did": did}
    try:
        resp = requests.get(base_url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print(f"[WARN] DID {did}: request failed → {exc}")
        return None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def fetch_facilities(
    valid_dids: Iterable[str | int],
    *,
    base_url: str = DEFAULT_BASE_URL,
    ftid: int = DEFAULT_FTID,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> List[dict]:
    """
    Fetch and parse **all** facilities across the supplied *valid_dids*.

    Uses `parse_facilities()` from *lcsd_util_af_master_parser.py*.
    """
    all_records: List[dict] = []

    for did in valid_dids:
        if verbose:
            print(f"[INFO] DID {did}: fetching…")
        html = _fetch_page_html(did, base_url=base_url, ftid=ftid, timeout=timeout)
        if not html:
            continue
        facs = parse_facilities(html, did=str(did))
        if facs:
            all_records.extend(facs)
            if verbose:
                print(f"       → {len(facs)} facility entry(ies) found")
        elif verbose:
            print("       → no entries found")
    return all_records


def build_master_json(
    valid_dids: Iterable[str | int],
    *,
    output_path: Optional[Path] = None,
    base_url: str = DEFAULT_BASE_URL,
    ftid: int = DEFAULT_FTID,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> Path:
    """
    Convenience wrapper: gather facilities and dump to timestamped JSON.

    If *output_path* is **None**, the file name pattern is
        (YYYYMMDD)_(HHMMSS)_lcsd_af_master.json
    """
    facilities = fetch_facilities(
        valid_dids,
        base_url=base_url,
        ftid=ftid,
        timeout=timeout,
        verbose=verbose,
    )

    if output_path is None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"{ts}_lcsd_af_master.json")

    payload = {
        "metadata": {
            "timestamp": datetime.datetime.now().isoformat(),
            "num_dids": len(list(valid_dids)),
            "num_facilities": len(facilities),
        },
        "facilities": facilities,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"[OK] Master JSON saved → {output_path.name} "
              f"({len(facilities)} facilities)")
    return output_path


# ---------------------------------------------------------------------------
# Optional CLI utility (unchanged except for parser import)
# ---------------------------------------------------------------------------


def _cli_select_probe_file() -> Path:
    """Prompt user to pick a *_lcsd_af_probe.json file in cwd."""
    probe_files = sorted(Path(".").glob("*_lcsd_af_probe.json"))
    if not probe_files:
        sys.exit("No *_lcsd_af_probe.json files found in this directory.")

    print("\nSelect a probe-file to process:\n")
    for idx, p in enumerate(probe_files, 1):
        print(f"  {idx}. {p.name}")
    print()

    while True:
        choice = input(f"Enter number (1-{len(probe_files)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(probe_files):
            return probe_files[int(choice) - 1]
        print("Invalid selection; try again.")


def _load_valid_dids_from_probe(probe_path: Path) -> List[str]:
    with probe_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("valid_dids", [])


def _main() -> None:
    """
    CLI entry point: prompt for a probe JSON → write master JSON.
    """
    probe_file = _cli_select_probe_file()
    dids = _load_valid_dids_from_probe(probe_file)
    if not dids:
        sys.exit("Selected probe-file contained zero valid DIDs.")

    print(f"\nProcessing {len(dids)} DIDs from {probe_file.name} …\n")
    build_master_json(dids, verbose=True)


if __name__ == "__main__":  # pragma: no cover
    _main()

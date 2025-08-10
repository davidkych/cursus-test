# src/routers/auth/grants.py
"""
Grant registry for the auth code-generator/redeemer.

- Single source of truth for supported grants.
- Keeps field names canonical and easily extensible.
- Zero external dependencies; pure dict mutation helpers.

Usage (from redeem flow)
------------------------
from .grants import ALLOWED_GRANTS, apply_grants, validate_grants

invalid = validate_grants(requested_grants)
if invalid:
    raise HTTPException(422, detail=f"Unknown grants: {', '.join(invalid)}; allowed: {sorted(ALLOWED_GRANTS)}")

applied = apply_grants(user_doc, requested_grants)
# persist user_doc afterwards (upsert/replace)
"""

from __future__ import annotations
from typing import Dict, Iterable, List, Set, Tuple

# ─────────────────────────── Registry ───────────────────────────
# Canonical field names (per your spec)
# - isAdmin
# - isPremiumMember
#
# Each entry is a small function that mutates the in-memory user document.
# Keep these idempotent (setting True repeatedly is safe).
def _grant_is_admin(user: Dict) -> None:
    user["isAdmin"] = True


def _grant_is_premium(user: Dict) -> None:
    user["isPremiumMember"] = True


GRANTS: Dict[str, callable] = {
    "isAdmin": _grant_is_admin,
    "isPremiumMember": _grant_is_premium,
}

ALLOWED_GRANTS: Set[str] = set(GRANTS.keys())


# ─────────────────────────── Helpers ───────────────────────────
def _normalize(grants: Iterable[str]) -> List[str]:
    """
    Deduplicate while preserving order of first appearance.
    Filters out falsy values and trims whitespace.
    """
    seen: Set[str] = set()
    out: List[str] = []
    for g in grants or []:
        if not g:
            continue
        key = str(g).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def validate_grants(requested: Iterable[str]) -> List[str]:
    """
    Return the list of unknown/invalid grants.
    Empty list means all requested grants are valid.
    """
    normalized = _normalize(requested)
    return [g for g in normalized if g not in ALLOWED_GRANTS]


def apply_grants(user_doc: Dict, requested: Iterable[str]) -> List[str]:
    """
    Apply valid grants to the provided user document (in-place).
    Returns the list of grants that were actually applied.
    Unknown grants are ignored here (validate first if you want strictness).
    """
    applied: List[str] = []
    for g in _normalize(requested):
        fn = GRANTS.get(g)
        if fn:
            before = dict(user_doc)  # shallow snapshot to detect changes if needed
            fn(user_doc)
            # record as applied if the field now reflects the intended truthy state
            # (this is naturally idempotent)
            applied.append(g)
    return applied

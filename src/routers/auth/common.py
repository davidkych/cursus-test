# ── src/routers/auth/common.py ────────────────────────────────────────────────
"""
Shared helpers for auth-related user document defaults.

- DEFAULT_USER_FLAGS: single source of truth for new boolean flags.
- apply_default_user_flags(doc): idempotently ensures the flags exist
  on a user document (mutates the given dict and returns it).
"""

from typing import Dict, Any

# Single source of truth for new flags (extendable later without hardcoding elsewhere)
DEFAULT_USER_FLAGS: Dict[str, bool] = {
    "is_admin": False,
    "is_premium_member": False,
}

def apply_default_user_flags(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure a user document has the expected boolean flags with safe defaults.
    - Mutates doc in place (and returns it for convenience).
    - Idempotent: existing values are preserved; only missing keys are added.
    """
    for key, default_val in DEFAULT_USER_FLAGS.items():
        if key not in doc:
            doc[key] = default_val
    return doc

__all__ = [
    "DEFAULT_USER_FLAGS",
    "apply_default_user_flags",
]
 
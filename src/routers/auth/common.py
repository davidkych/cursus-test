# ── src/routers/auth/common.py ────────────────────────────────────────────────
"""
Shared helpers for auth-related user document defaults and feature application.

- DEFAULT_USER_FLAGS: single source of truth for new boolean flags.
- apply_default_user_flags(doc): idempotently ensures the flags exist
  on a user document (mutates the given dict and returns it).

- FUNCTION_APPLIERS: registry mapping a "function" key to a callable that
  mutates a user document accordingly (kept here to avoid scattering logic).
- FUNCTION_KEYS: convenience set of supported function keys.
- apply_user_function(doc, function_key): looks up the applier and applies it.
"""

from typing import Dict, Any, Callable, Set

# ─────────────────────────── default flags ────────────────────────────────────
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


# ─────────────────────── function (feature) registry ─────────────────────────
def _set_flag(flag: str) -> Callable[[Dict[str, Any]], None]:
    """Factory: returns an applier that sets a boolean flag to True."""
    def applier(u: Dict[str, Any]) -> None:
        u[flag] = True
    return applier

# Central registry of supported "functions" that can be granted via codes.
# Extend this mapping to add new capabilities without touching route logic.
FUNCTION_APPLIERS: Dict[str, Callable[[Dict[str, Any]], None]] = {
    # Currently supported per requirements:
    "is_admin": _set_flag("is_admin"),
    "is_premium_member": _set_flag("is_premium_member"),
}

# Convenience set for validation
FUNCTION_KEYS: Set[str] = set(FUNCTION_APPLIERS.keys())

def apply_user_function(doc: Dict[str, Any], function_key: str) -> bool:
    """
    Apply a registered function to the given user document.

    Returns:
        bool: True if the document was changed by the applier, False otherwise
              (e.g., flag already set or unknown function_key).
    """
    applier = FUNCTION_APPLIERS.get(function_key)
    if not applier:
        return False

    before = {k: doc.get(k) for k in DEFAULT_USER_FLAGS.keys()}  # snapshot
    applier(doc)
    # Detect change by comparing known flags (keeps logic generic)
    after = {k: doc.get(k) for k in DEFAULT_USER_FLAGS.keys()}
    return before != after


__all__ = [
    "DEFAULT_USER_FLAGS",
    "apply_default_user_flags",
    "FUNCTION_APPLIERS",
    "FUNCTION_KEYS",
    "apply_user_function",
]

# ── src/routers/auth/common.py ────────────────────────────────────────────────
"""
Shared helpers for auth-related user document defaults and function application.

- DEFAULT_USER_FLAGS: single source of truth for new boolean flags.
- apply_default_user_flags(doc): idempotently ensures the flags exist
  on a user document (mutates the given dict and returns it).

- FUNCTION_REGISTRY: single source of truth for supported "functions"
  that can be applied to a user account via code redemption.
- apply_function(user_doc, fn_key): validates and applies a registered function
  to the given user document (mutates in place).
"""

from typing import Dict, Any, Callable

# ───────────────────────────── user-flag defaults ─────────────────────────────

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


# ───────────────────────────── function registry ──────────────────────────────
# Each registry entry is a small applicator that mutates the user document in place.
# Keep ALL supported functions here so the rest of the codebase never hardcodes them.

def _fn_is_admin(user_doc: Dict[str, Any]) -> None:
    # Ensure defaults exist first, then elevate
    apply_default_user_flags(user_doc)
    user_doc["is_admin"] = True


def _fn_is_premium_member(user_doc: Dict[str, Any]) -> None:
    apply_default_user_flags(user_doc)
    user_doc["is_premium_member"] = True


FUNCTION_REGISTRY: Dict[str, Callable[[Dict[str, Any]], None]] = {
    # v1 supported functions
    "is_admin": _fn_is_admin,
    "is_premium_member": _fn_is_premium_member,
    # Add future functions here (e.g., "beta_access": _fn_beta_access)
}


def apply_function(user_doc: Dict[str, Any], fn_key: str) -> None:
    """
    Validate and apply a registered function to the given user document.
    - Mutates user_doc in place.
    - Raises ValueError if the function key is not registered.
    """
    fn = FUNCTION_REGISTRY.get(fn_key)
    if not fn:
        raise ValueError(f"Unsupported function: {fn_key}")
    fn(user_doc)


__all__ = [
    "DEFAULT_USER_FLAGS",
    "apply_default_user_flags",
    "FUNCTION_REGISTRY",
    "apply_function",
]

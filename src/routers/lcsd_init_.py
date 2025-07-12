# ── src/routers/lcsd/__init__.py ──────────────────────────────────────
"""
LCSD router package – re-exports the athletic-field collector endpoint.
"""

from .lcsd_af_info import router  # noqa: F401  (re-export for main.include_router)

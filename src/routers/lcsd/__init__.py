# ── src/routers/lcsd/__init__.py ─────────────────────────────────────────────
"""
LCSD (Leisure & Cultural Services Department) sub-router.

Exposes one public endpoint:

    /api/lcsd/lcsd_af_info        (GET | POST)

which probes LCSD athletic-field pages, harvests facility data, and
stores the resulting master-JSON in Cosmos DB via the existing JSON API.
"""
from .endpoints import router   # re-export for main.py include_router

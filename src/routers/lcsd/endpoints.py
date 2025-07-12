# ── src/routers/lcsd/endpoints.py ────────────────────────────────────────────
"""
Aggregator for all LCSD sub-routers.

Add further sub-routers here so they are automatically exposed by main.py.
"""

from fastapi import APIRouter

# ⬇ existing endpoint(s)
from .lcsd_af_info               import router as _af_info_router
# ⬇ NEW jogging-timetable endpoint
from .lcsd_af_timetable_endpoint import router as _af_tt_router

router = APIRouter()
router.include_router(_af_info_router)   # /api/lcsd/lcsd_af_info
router.include_router(_af_tt_router)     # /api/lcsd/lcsd_af_timetable_probe

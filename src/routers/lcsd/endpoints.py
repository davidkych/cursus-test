# src/routers/lcsd/endpoints.py
from fastapi import APIRouter

# Existing LCSD info endpoint
from .lcsd_af_info import router as _af_info_router
# Renamed jogging-timetable endpoint
from .lcsd_af_timetable import router as _af_tt_router

router = APIRouter()
router.include_router(_af_info_router)   # /api/lcsd/lcsd_af_info
router.include_router(_af_tt_router)     # /api/lcsd/lcsd_af_timetable_probe

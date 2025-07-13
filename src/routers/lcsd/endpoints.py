# src/routers/lcsd/endpoints.py
from fastapi import APIRouter

from .lcsd_af_info import router as _af_info_router
from .lcsd_af_timetable import router as _af_tt_router
from .lcsd_af_excel_timetable import router as _af_excel_router  # NEW
from .lcsd_af_adminupload_page import router as _adminupload_router 

router = APIRouter()
router.include_router(_af_info_router)
router.include_router(_af_tt_router)
router.include_router(_af_excel_router)
router.include_router(_adminupload_router)  # NEW
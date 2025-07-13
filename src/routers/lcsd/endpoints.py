# ── src/routers/lcsd/endpoints.py ────────────────────────────────────
from fastapi import APIRouter

from .lcsd_af_info import router as _af_info_router
from .lcsd_af_timetable import router as _af_tt_router
from .lcsd_af_excel_timetable import router as _af_excel_router
from .lcsd_af_adminupload_html import router as _admin_html_router
from .lcsd_af_adminupload_logic import router as _admin_logic_router
from .lcsd_cleanup_validator import router as _cleanup_validator_router
from .lcsd_cleanup_validator_scheduler import (
    router as _cleanup_validator_sched_router,  # NEW
)

router = APIRouter()
router.include_router(_af_info_router)
router.include_router(_af_tt_router)
router.include_router(_af_excel_router)
router.include_router(_admin_html_router)
router.include_router(_admin_logic_router)
router.include_router(_cleanup_validator_router)
router.include_router(_cleanup_validator_sched_router)  # NEW

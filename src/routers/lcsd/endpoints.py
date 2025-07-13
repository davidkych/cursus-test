# ── src/routers/lcsd/endpoints.py ────────────────────────────────────
from fastapi import APIRouter

from .lcsd_af_info import router as _af_info_router
from .lcsd_af_timetable import router as _af_tt_router
from .lcsd_af_excel_timetable import router as _af_excel_router
from .lcsd_af_adminupload_html import router as _admin_html_router
from .lcsd_af_adminupload_logic import router as _admin_logic_router
# NOTE: lcsd_cleanup_validator removed per 2025-07 change-request
from .lcsd_cleanup_validator_scheduler import router as _cleanup_sched_router  # sched version kept
# NEW — availability endpoints
from .availability_endpoints import router as _availability_router
from .html_availability_endpoints import router as _html_avail_router

router = APIRouter()

router.include_router(_af_info_router)
router.include_router(_af_tt_router)
router.include_router(_af_excel_router)
router.include_router(_admin_html_router)
router.include_router(_admin_logic_router)
# cleanup-validator endpoint intentionally **not** included any longer
router.include_router(_cleanup_sched_router)
# NEW — make availability routes reachable
router.include_router(_availability_router)
router.include_router(_html_avail_router)

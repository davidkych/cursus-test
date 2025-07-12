# ── src/routers/lcsd/endpoints.py ────────────────────────────────────────────
"""
Aggregator for LCSD sub-routers.

• Keeps the public export `router` expected by main.py
• Includes individual endpoint modules so multiple endpoints can
  coexist without cluttering one file.
"""

from fastapi import APIRouter

# Import each endpoint module’s router here
from .lcsd_af_info import router as _af_info_router

router = APIRouter()
router.include_router(_af_info_router)

# Add future sub-routers with `router.include_router(<router>)` here.

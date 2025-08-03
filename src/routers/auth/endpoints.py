# ── src/routers/auth/endpoints.py ────────────────────────────────────────────
"""
Aggregator – keeps the original import path unchanged
(`from routers.auth.endpoints import router as auth_router`)
while delegating to the individual sub-modules.
"""
from fastapi import APIRouter
from .register import router as register_router
from .login    import router as login_router
from .me       import router as me_router          # ← NEW

router = APIRouter()
router.include_router(register_router)
router.include_router(login_router)
router.include_router(me_router)                   # ← NEW

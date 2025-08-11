# ── src/routers/auth/endpoints.py ────────────────────────────────────────────
"""
Aggregator – keeps the original import path unchanged
(`from routers.auth.endpoints import router as auth_router`)
while delegating to the dedicated modules.
"""
from fastapi import APIRouter
from .register import router as register_router
from .login    import router as login_router
from .me       import router as me_router

# ⟨NEW⟩ code generator + redemption JSON endpoints
from .codes import router as codes_router
# ⟨NEW⟩ lightweight HTML code generator form (independent of SPA)
#from .html_codegen import router as html_codegen_router

router = APIRouter()
router.include_router(register_router)
router.include_router(login_router)
router.include_router(me_router)

# ⟨NEW⟩ mount new routers under /api/auth/*
router.include_router(codes_router)
#router.include_router(html_codegen_router)

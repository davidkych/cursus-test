# ── src/routers/auth/endpoints.py ────────────────────────────────────────────
"""
Aggregator – keeps the original import path unchanged
(from routers.auth.endpoints import router as auth_router)
while delegating to the dedicated modules.
"""
from fastapi import APIRouter

from .register         import router as register_router
from .login            import router as login_router
from .me               import router as me_router
from .change_password  import router as change_pwd_router
from .change_email     import router as change_email_router

# ⟨NEW⟩ code generator (JSON API), HTML UI, and redemption endpoints
from .codegen          import router as codegen_router
from .html_codegen     import router as html_codegen_router
from .redeem           import router as redeem_router

router = APIRouter()

# existing auth routes
router.include_router(register_router)
router.include_router(login_router)
router.include_router(me_router)
router.include_router(change_pwd_router)
router.include_router(change_email_router)

# ⟨NEW⟩ code system routes
router.include_router(codegen_router)
router.include_router(html_codegen_router)
router.include_router(redeem_router)

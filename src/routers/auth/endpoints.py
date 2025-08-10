# ── src/routers/auth/endpoints.py ────────────────────────────────────────────
"""
Aggregator – keeps the original import path unchanged
(`from routers.auth.endpoints import router as auth_router`)
while delegating to the dedicated modules.
"""
from fastapi import APIRouter

from .register        import router as register_router
from .login           import router as login_router
from .me              import router as me_router
from .change_password import router as change_pwd_router
from .change_email    import router as change_email_router

# ⟨NEW⟩ Code generator / redeemer JSON API
from .codes           import router as codes_router

# ⟨NEW⟩ Simple HTML generator UI (independent of the Vue frontend)
from .html_endpoints  import router as codes_html_router

router = APIRouter()
router.include_router(register_router)
router.include_router(login_router)
router.include_router(me_router)
router.include_router(change_pwd_router)
router.include_router(change_email_router)

# ⟨NEW⟩ mount code generator + HTML UI
router.include_router(codes_router)
router.include_router(codes_html_router)

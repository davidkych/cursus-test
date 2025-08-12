# ── src/main.py ───────────────────────────────────────────────────────────────
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ── CORS (robust + deploy-safe)
# Accept a comma/space-separated FRONTEND_ORIGIN list.
# If none provided, fall back to "*" with allow_credentials=False so the browser
# accepts Authorization headers cross-origin without requiring ACAO to be non-wildcard.
def _parse_origins(env_value: str) -> list[str]:
    if not env_value:
        return []
    # split by comma or whitespace, trim, drop empties and trailing slashes
    raw = [p.strip() for chunk in env_value.split(",") for p in chunk.split()]
    origins = []
    for o in raw:
        o = o.rstrip("/")  # normalize
        if o and o not in origins:
            origins.append(o)
    return origins

_frontend_origins = _parse_origins(os.getenv("FRONTEND_ORIGIN", ""))

if _frontend_origins:
    # Concrete allowed origins → credentials may be enabled safely
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # No specific origin configured → use wildcard and disable credentials.
    # This still allows Authorization headers (non-cookie auth) with proper preflight.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ── core modules -------------------------------------------------------------
from routers.hello.endpoints           import router as hello_router
from routers.healthz.endpoints         import router as health_router
from routers.jsondata.endpoints        import router as jsondata_router
from routers.jsondata.html_endpoints   import router as html_json_router
from routers.log.endpoints             import router as log_router
from routers.log.html_console_endpoint import router as log_console_router
from routers.schedule.endpoints        import router as schedule_router
from routers.lcsd.endpoints            import router as lcsd_router
from routers.auth.endpoints            import router as auth_router      # ← NEW

# ── include routes -----------------------------------------------------------
app.include_router(hello_router)
app.include_router(health_router)
app.include_router(jsondata_router)
app.include_router(html_json_router)
app.include_router(log_router)
app.include_router(log_console_router)
app.include_router(schedule_router)
app.include_router(lcsd_router)
app.include_router(auth_router)                                           # ← NEW

# ── root ---------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return {
        "status": "ok",
        "info": (
            "/api/hello, /healthz, /api/json/*, /api/log, /api/log/console/, "
            "/api/schedule (POST|DELETE), /api/lcsd/lcsd_af_info, "
            "/api/auth/register, /api/auth/login"
        ),
    }

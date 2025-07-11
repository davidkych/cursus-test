# src/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Initialise app & CORS --------------------------------------------
app = FastAPI()

frontend_origin = os.getenv("FRONTEND_ORIGIN", "*")   # set in App-Service settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin] if frontend_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── core modules ------------------------------------------------------
from routers.hello.endpoints               import router as hello_router
from routers.healthz.endpoints             import router as health_router
from routers.jsondata.endpoints            import router as jsondata_router
from routers.jsondata.html_endpoints       import router as html_json_router
from routers.log.endpoints                 import router as log_router
from routers.log.html_console_endpoint     import router as log_console_router
from routers.schedule.endpoints            import router as schedule_router            # ← NEW

# ── include routes ----------------------------------------------------
app.include_router(hello_router)
app.include_router(health_router)
app.include_router(jsondata_router)
app.include_router(html_json_router)
app.include_router(log_router)
app.include_router(log_console_router)
app.include_router(schedule_router)          # ← NEW

# ── root --------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return {
        "status": "ok",
        "info": (
            "/api/hello, /healthz, /api/json/*, /api/log, /api/log/console/, "
            "/api/schedule (POST|DELETE)"
        ),
    }

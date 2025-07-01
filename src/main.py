# ── src/main.py ───────────────────────────────────────────────────────
from fastapi import FastAPI

from routers.hello.endpoints             import router as hello_router
from routers.healthz.endpoints           import router as health_router
from routers.jsondata.endpoints          import router as jsondata_router
from routers.jsondata.html_endpoints     import router as html_json_router

from routers.log.endpoints               import router as log_router
from routers.log.html_console_endpoint   import router as log_console_router   # ← NEW

# LCSD sub-modules
from routers.lcsd.probe_endpoints               import router as lcsd_probe_router
from routers.lcsd.html_probe_endpoints          import router as lcsd_html_probe_router
from routers.lcsd.master_endpoints              import router as lcsd_master_router
from routers.lcsd.html_master_endpoints         import router as lcsd_html_master_router
from routers.lcsd.timetableprobe_endpoints      import router as lcsd_timetableprobe_router
from routers.lcsd.html_timetableprobe_endpoints import router as lcsd_html_timetableprobe_router
from routers.lcsd.timetable_endpoints           import router as lcsd_timetable_router
from routers.lcsd.html_timetable_endpoints      import router as lcsd_html_timetable_router
from routers.lcsd.timetablepdf_endpoints        import router as lcsd_timetablepdf_router
from routers.lcsd.html_timetablepdf_endpoints   import router as lcsd_html_timetablepdf_router
from routers.lcsd.timetableexcel_endpoints      import router as lcsd_timetableexcel_router
from routers.lcsd.html_timetableexcel_endpoints import router as lcsd_html_timetableexcel_router
from routers.lcsd.availability_endpoints        import router as lcsd_availability_router
from routers.lcsd.html_availability_endpoints   import router as lcsd_html_availability_router
from routers.lcsd.html_dashboard_endpoints      import router as lcsd_html_dashboard_router
from routers.lcsd.html_dashboard_monthview_endpoints import \
    router as lcsd_html_monthview_router

app = FastAPI()

# ── core routes ──────────────────────────────────────────────────────
app.include_router(hello_router)
app.include_router(health_router)
app.include_router(jsondata_router)
app.include_router(html_json_router)
app.include_router(log_router)
app.include_router(log_console_router)   # ← NEW
# ── LCSD routes ──────────────────────────────────────────────────────
app.include_router(lcsd_probe_router)
app.include_router(lcsd_html_probe_router)
app.include_router(lcsd_master_router)
app.include_router(lcsd_html_master_router)
app.include_router(lcsd_timetableprobe_router)
app.include_router(lcsd_html_timetableprobe_router)
app.include_router(lcsd_timetable_router)
app.include_router(lcsd_html_timetable_router)
app.include_router(lcsd_timetablepdf_router)
app.include_router(lcsd_html_timetablepdf_router)
app.include_router(lcsd_timetableexcel_router)
app.include_router(lcsd_html_timetableexcel_router)
app.include_router(lcsd_availability_router)
app.include_router(lcsd_html_availability_router)
app.include_router(lcsd_html_dashboard_router)
app.include_router(lcsd_html_monthview_router)

# ── root ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def root():
    return {
        "status": "ok",
        "info": (
            "/api/hello, /healthz, /api/json/*, /api/log, /api/log/console/, "
            "/api/lcsd/probe (GET|POST), /api/lcsd/probe/html, "
            "/api/lcsd/master (GET|POST), /api/lcsd/master/html, "
            "/api/lcsd/timetableprobe (GET|POST), /api/lcsd/timetableprobe/html, "
            "/api/lcsd/timetable (GET|POST), /api/lcsd/timetable/html, "
            "/api/lcsd/timetablepdf (GET|POST), /api/lcsd/timetablepdf/html, "
            "/api/lcsd/timetableexcel (GET|POST), /api/lcsd/timetableexcel/html, "
            "/api/lcsd/availability (GET|POST), /api/lcsd/availability/html, "
            "/api/lcsd/dashboard/<lcsdid>, "
            "/api/lcsd/dashboard/<lcsdid>/month"
        ),
    }

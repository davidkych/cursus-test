# ── src/routers/log/__init__.py ───────────────────────────────────────
"""
Logging sub-router.

Exposes a single POST `/api/log` endpoint that other internal routes can
call to append structured log lines into the Cosmos “jsonContainer”.

The log is stored exactly the same way as the existing JSON API:
    tag           = "log"
    secondary_tag = <user-supplied tag>
    tertiary_tag  = <user-supplied tertiary_tag, if any>
    year/month/day= current HKT date
"""
from .endpoints import router  # re-export for `include_router`

"""
/healthz  – lightweight probe to verify the scheduler Function-App
and the Durable Functions extension are up & running.
"""
from __future__ import annotations

import azure.functions as func
from datetime import datetime, timezone
import platform, os, json, logging

def main(req: func.HttpRequest) -> func.HttpResponse:          # noqa: D401
    logging.info("↪ health probe")

    # quick “is Durable loaded?” heuristic
    try:
        import azure.durable_functions as df  # noqa: F401
        durable_ok = True
    except Exception:                         # noqa: BLE001
        durable_ok = False

    payload = {
        "status":            "ok",
        "utc":               datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version":    platform.python_version(),
        "site_name":         os.getenv("WEBSITE_SITE_NAME", "local"),
        "durable_extension": "loaded" if durable_ok else "missing",
        "hub_name":          "SchedulerHub"
    }

    return func.HttpResponse(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        status_code=200 if durable_ok else 500
    )

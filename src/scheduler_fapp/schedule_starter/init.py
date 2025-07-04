# ── src/scheduler_fapp/schedule_starter/init.py ───────────────────────
import azure.functions as func
import azure.durable_functions as df
import json
import logging
import os

from utils import parse_hkt_to_utc, log_to_api   # shared module


def _make_location_header(instance_id: str) -> str:
    """
    Build a *public* status-polling URL for the given `instance_id`.

    On the combination azure-functions==1.20.0 × durable==1.2.6
    `req.url` sometimes resolves to an **async coroutine**, causing  
    `TypeError: replace() argument 2 must be str, not coroutine`.

    The workaround is to reconstruct the base URL from the
    `WEBSITE_SITE_NAME` environment variable that is always present
    inside an App-Service / Function-App container.
    """
    site_name = os.getenv("WEBSITE_SITE_NAME", "")   # e.g. cursus-test-sched
    base = f"https://{site_name}.azurewebsites.net" if site_name else "http://localhost:7071"
    return f"{base}/runtime/webhooks/durabletask/instances/{instance_id}"


def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:  # noqa: D401
    """
    HTTP entry-point that kicks off the orchestration **without using**
    `create_check_status_response`, which currently crashes because of
    the coroutine/replace bug mentioned above.

    NOTE: Must remain **synchronous** – async entry-points are not
    supported by the in-proc Python worker used by Durable Functions.
    """
    try:
        logging.info("↪ /schedule called")

        # ── payload parsing & validation ──────────────────────────────
        try:
            body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON body"}),
                status_code=400,
                mimetype="application/json",
            )

        missing = [k for k in ("exec_at", "prompt_type", "payload") if k not in body]
        if missing:
            return func.HttpResponse(
                json.dumps({"error": f"Missing keys: {', '.join(missing)}"}),
                status_code=400,
                mimetype="application/json",
            )

        try:
            exec_at_utc = parse_hkt_to_utc(body["exec_at"])
        except ValueError as exc:
            return func.HttpResponse(
                json.dumps({"error": str(exc)}),
                status_code=400,
                mimetype="application/json",
            )

        orch_input = {
            "exec_at_utc": exec_at_utc,
            "prompt_type": body["prompt_type"],
            "payload": body["payload"],
        }

        # ── create orchestration (sync) ───────────────────────────────
        client = df.DurableOrchestrationClient(starter)
        instance_id = client.start_new("schedule_orchestrator", None, orch_input)
        logging.info("🎬 Started orchestration %s", instance_id)

        log_to_api(
            "info",
            f"Scheduled {body['prompt_type']} at {body['exec_at']} HKT "
            f"(instance {instance_id})",
        )

        # ── manual 202 Accepted response (work-around) ───────────────
        location = _make_location_header(instance_id)
        return func.HttpResponse(
            json.dumps({"id": instance_id}),
            status_code=202,
            mimetype="application/json",
            headers={"Location": location, "Retry-After": "5"},
        )

    # ── generic diagnostics ──────────────────────────────────────────
    except Exception as exc:  # noqa: BLE001
        logging.exception("Unhandled error in /schedule")
        return func.HttpResponse(
            json.dumps({"error": str(exc), "type": exc.__class__.__name__}),
            status_code=500,
            mimetype="application/json",
        )

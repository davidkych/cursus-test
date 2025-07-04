import azure.functions as func
import azure.durable_functions as df
import json
import logging
import os

from utils import parse_hkt_to_utc, log_to_api   # shared module


def _make_location_header(instance_id: str) -> str:
    """
    Build the public Durable-Functions status URL for `instance_id`.
    """
    site_name = os.getenv("WEBSITE_SITE_NAME", "")
    base = f"https://{site_name}.azurewebsites.net" if site_name else "http://localhost:7071"
    return f"{base}/runtime/webhooks/durabletask/instances/{instance_id}"


# ──────────────────────────────────────────────────────────────────────
# MAIN ENTRY-POINT  (now **async** so we can await Durable SDK calls)
# ----------------------------------------------------------------------
async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:  # noqa: D401
    """
    HTTP entry-point that schedules an orchestration and returns **202 Accepted**.
    Implements a manual response to work around coroutine → str bugs in the
    SDK helpers.
    """
    try:
        logging.info("↪ /schedule called")

        # ── payload parsing & validation ───────────────────────────────
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

        # ── create orchestration (await!) ──────────────────────────────
        client = df.DurableOrchestrationClient(starter)
        instance_id: str = await client.start_new(      # <- WAS sync call
            "schedule_orchestrator", None, orch_input
        )
        logging.info("🎬 Started orchestration %s", instance_id)

        log_to_api(
            "info",
            f"Scheduled {body['prompt_type']} at {body['exec_at']} HKT "
            f"(instance {instance_id})",
        )

        # ── manual 202 Accepted response ──────────────────────────────
        location = _make_location_header(instance_id)
        return func.HttpResponse(
            json.dumps({"id": instance_id}),
            status_code=202,
            mimetype="application/json",
            headers={
                "Location": location,
                "Retry-After": "5",
            },
        )

    # ── generic diagnostics ───────────────────────────────────────────
    except Exception as exc:  # noqa: BLE001
        logging.exception("Unhandled error in /schedule")
        return func.HttpResponse(
            json.dumps({"error": str(exc), "type": exc.__class__.__name__}),
            status_code=500,
            mimetype="application/json",
        )

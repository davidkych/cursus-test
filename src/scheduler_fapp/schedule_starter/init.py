import azure.functions as func
import azure.durable_functions as df
import json
import logging

from utils import parse_hkt_to_utc, log_to_api   # shared module


def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:  # noqa: D401
    """
    HTTP entry-point that kicks off the orchestration.

    On **any** unhandled exception we now return a JSON body with the
    exception type / message – this is surfaced by the API gateway and
    greatly speeds up troubleshooting.
    """
    try:
        logging.info("↪ /schedule called")

        try:
            body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON body"}),
                status_code=400,
                mimetype="application/json",
            )

        # ── validation ------------------------------------------------
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

        # ── start orchestration --------------------------------------
        client = df.DurableOrchestrationClient(starter)
        instance_id = client.start_new("schedule_orchestrator", None, orch_input)
        logging.info("🎬 Started orchestration %s", instance_id)

        log_to_api(
            "info",
            f"Scheduled {body['prompt_type']} at {body['exec_at']} HKT "
            f"(instance {instance_id})",
        )

        return client.create_check_status_response(req, instance_id)

    # ────────────────────────────────────────────────────────────────
    # GENERIC DIAGNOSTICS
    # ----------------------------------------------------------------
    except Exception as exc:  # noqa: BLE001
        logging.exception("Unhandled error in /schedule")
        return func.HttpResponse(
            json.dumps(
                {
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                }
            ),
            status_code=500,
            mimetype="application/json",
        )

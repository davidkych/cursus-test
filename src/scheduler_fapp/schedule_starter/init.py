import azure.functions as func
import azure.durable_functions as df
import logging, json
from utils import parse_hkt_to_utc, log_to_api   # shared module

def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:   # noqa: D401
    """HTTP entry-point that kicks off the orchestration."""
    logging.info("↪ /schedule called")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON body", status_code=400)

    # ── validation ----------------------------------------------------
    missing = [k for k in ("exec_at", "prompt_type", "payload") if k not in body]
    if missing:
        return func.HttpResponse(f"Missing keys: {', '.join(missing)}", status_code=400)

    try:
        exec_at_utc = parse_hkt_to_utc(body["exec_at"])
    except ValueError as exc:
        return func.HttpResponse(str(exc), status_code=400)

    orch_input = {
        "exec_at_utc": exec_at_utc,
        "prompt_type": body["prompt_type"],
        "payload":     body["payload"],
    }

    # ── start orchestration ------------------------------------------
    client      = df.DurableOrchestrationClient(starter)
    instance_id = client.start_new("schedule_orchestrator", None, orch_input)
    logging.info("🎬 Started orchestration %s", instance_id)

    log_to_api("info",
               f"Scheduled {body['prompt_type']} at {body['exec_at']} HKT "
               f"(instance {instance_id})")

    return client.create_check_status_response(req, instance_id)

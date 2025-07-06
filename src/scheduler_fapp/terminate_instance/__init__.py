import azure.functions as func
import azure.durable_functions as df
import json
import logging


async def main(req: func.HttpRequest, client: str) -> func.HttpResponse:  # noqa: D401
    """
    POST /api/terminate/{instanceId}

    Anonymous helper that lets the FastAPI façade cancel a pending
    orchestration *without* needing the management key.  Mirrors the
    behaviour of the existing /api/status/{instanceId} endpoint.
    """
    instance_id = req.route_params.get("instanceId")
    if not instance_id:
        return func.HttpResponse(
            json.dumps({"error": "instanceId missing in route"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        dclient = df.DurableOrchestrationClient(client)
        await dclient.terminate(instance_id, "user cancelled")

        # (optional) purge so the instance disappears from /api/schedules
        try:
            await dclient.purge_instance_history(instance_id)
        except Exception:
            pass

        return func.HttpResponse(status_code=202)          # Accepted
    except Exception as exc:                               # noqa: BLE001
        logging.exception("terminate_instance failed")
        return func.HttpResponse(
            json.dumps({"error": str(exc), "type": exc.__class__.__name__}),
            status_code=500,
            mimetype="application/json",
        )

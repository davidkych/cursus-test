# ── src/scheduler_fapp/status/__init__.py ─────────────────────────────
import azure.functions as func
import azure.durable_functions as df
import json
import logging

async def main(                       # HTTP GET  /api/status/{instanceId}
    req:     func.HttpRequest,
    client:  str,                     # durableClient binding
) -> func.HttpResponse:               # noqa: D401
    instance_id = req.route_params.get("instanceId")

    if not instance_id:                          # unlikely with correct route
        return func.HttpResponse(
            json.dumps({"error": "instanceId missing in route"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        dclient = df.DurableOrchestrationClient(client)
        status  = await dclient.get_status(instance_id)
        if status is None:
            return func.HttpResponse(
                json.dumps({"error": "Instance not found"}),
                status_code=404,
                mimetype="application/json",
            )

        # serialise the DurableOrchestrationStatus object to JSON
        return func.HttpResponse(
            json.dumps(status.to_json(), indent=2, default=str),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as exc:                      # noqa: BLE001
        logging.exception("Unhandled error in /status")
        return func.HttpResponse(
            json.dumps({"error": str(exc), "type": exc.__class__.__name__}),
            status_code=500,
            mimetype="application/json",
        )

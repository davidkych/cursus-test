# ── src/scheduler_fapp/list_schedules/__init__.py ────────────────────
import azure.functions as func
import azure.durable_functions as df
import json
import logging


async def main(req: func.HttpRequest, client: str) -> func.HttpResponse:   # noqa: D401
    """
    GET  /api/schedules   – List all jobs with metadata *and* live runtimeStatus.
    """
    try:
        dclient = df.DurableOrchestrationClient(client)
        entity_id = df.EntityId("schedule_entity", "registry")

        # ── pull current registry ------------------------------------------------
        state_resp = await dclient.read_entity_state(entity_id)
        registry: dict = state_resp.entity_state or {}

        # ── enrich with live runtimeStatus ---------------------------------------
        jobs = []
        for instance_id, info in registry.items():
            stat_obj = await dclient.get_status(instance_id)
            runtime = stat_obj.runtime_status.name if stat_obj else "Unknown"

            jobs.append(
                {
                    "instanceId":   instance_id,
                    "exec_at_utc":  info.get("exec_at_utc"),
                    "prompt_type":  info.get("prompt_type"),
                    "runtimeStatus": runtime,
                }
            )

        return func.HttpResponse(
            json.dumps({"jobs": jobs}, indent=2),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as exc:                                             # noqa: BLE001
        logging.exception("Unhandled error in /schedules")
        return func.HttpResponse(
            json.dumps({"error": str(exc), "type": exc.__class__.__name__}),
            mimetype="application/json",
            status_code=500,
        )

# ── src/scheduler_fapp/wipe_schedules/__init__.py ────────────────────
import azure.functions as func
import azure.durable_functions as df
import json, logging

async def main(req: func.HttpRequest, client: str) -> func.HttpResponse:  # noqa: D401
    """
    POST /api/wipe
    Terminates & purges EVERY orchestration instance then clears the
    registry entity so that `/api/schedules` returns an empty list.
    """
    try:
        dclient   = df.DurableOrchestrationClient(client)
        entity_id = df.EntityId("schedule_entity", "registry")

        # current registry ----------------------------------------------------
        state = (await dclient.read_entity_state(entity_id)).entity_state or {}
        terminated = []

        # terminate + purge each instance -------------------------------------
        for inst_id in list(state.keys()):
            try:
                await dclient.terminate(inst_id, "wipe-all requested")
            except Exception:
                pass                          # might already be Completed/Failed

            try:
                await dclient.purge_instance_history(inst_id)
            except Exception:
                pass                          # purge not fatal
            terminated.append(inst_id)

        # clear registry -------------------------------------------------------
        await dclient.signal_entity(entity_id, "reset")

        return func.HttpResponse(
            json.dumps({"terminated": terminated,
                        "total": len(terminated)}),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as exc:                                 # noqa: BLE001
        logging.exception("wipe_schedules failed")
        return func.HttpResponse(
            json.dumps({"error": str(exc),
                        "type":  exc.__class__.__name__}),
            status_code=500,
            mimetype="application/json",
        )

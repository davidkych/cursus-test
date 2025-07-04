import azure.durable_functions as df
from datetime import datetime
from utils import log_to_api

def orchestrator(ctx: df.DurableOrchestrationContext):   # noqa: D401
    data = ctx.get_input() or {}
    entity_id = df.EntityId("schedule_entity", "registry")

    # ── register in entity (for browse / deletion) --------------------
    ctx.signal_entity(entity_id, "add", {
        "instanceId":   ctx.instance_id,
        "exec_at_utc":  data["exec_at_utc"],
        "prompt_type":  data["prompt_type"],
    })

    # ── wait until exec time -----------------------------------------
    exec_at = datetime.fromisoformat(data["exec_at_utc"])
    fire_at = max(exec_at, ctx.current_utc_datetime)      # “next available instance”

    yield ctx.create_timer(fire_at)

    # ── run activity --------------------------------------------------
    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish ------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result

main = df.Orchestrator.create(orchestrator)

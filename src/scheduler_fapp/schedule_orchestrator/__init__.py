# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
import azure.durable_functions as df
from datetime import datetime                     # timezone no longer needed
from utils import log_to_api


def orchestrator(ctx: df.DurableOrchestrationContext):   # noqa: D401
    data = ctx.get_input() or {}
    entity_id = df.EntityId("schedule_entity", "registry")

    # ── register in entity (for browse / deletion) --------------------
    ctx.signal_entity(
        entity_id,
        "add",
        {
            "instanceId":  ctx.instance_id,
            "exec_at_utc": data["exec_at_utc"],
            "prompt_type": data["prompt_type"],
        },
    )

    # ── wait until exec time -----------------------------------------
    # Convert both times to *naive* UTC so the comparison is valid and
    # Durable Functions’ create_timer receives what it expects.
    exec_at = datetime.fromisoformat(data["exec_at_utc"])             # naive UTC
    now_utc = ctx.current_utc_datetime.replace(tzinfo=None)           # naive UTC
    fire_at = max(exec_at, now_utc)

    # inline diagnostics to aid future timing investigations
    log_to_api(
        "debug",
        f"[diag] orchestrator now={now_utc.isoformat()} "
        f"→ fire_at={fire_at.isoformat()}",
    )

    yield ctx.create_timer(fire_at)

    # ── run activity --------------------------------------------------
    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish ------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


main = df.Orchestrator.create(orchestrator)

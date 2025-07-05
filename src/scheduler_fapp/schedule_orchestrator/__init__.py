# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
import azure.durable_functions as df
from datetime import datetime
from utils import log_to_api


def orchestrator(ctx: df.DurableOrchestrationContext):    # noqa: D401
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
    exec_at = datetime.fromisoformat(data["exec_at_utc"])          # naïve UTC
    now_utc = ctx.current_utc_datetime                             # naïve UTC
    fire_at = max(exec_at, now_utc)

    # lightweight diagnostics (safe ⇒ no side-effects during replay)
    if not ctx.is_replaying:
        log_to_api(
            "debug",
            f"[diag] orch now={now_utc.isoformat()} "
            f"→ fire_at={fire_at.isoformat()} "
            f"(delta={(fire_at-now_utc).total_seconds():.1f}s)"
        )

    yield ctx.create_timer(fire_at)

    # ── run activity --------------------------------------------------
    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish ------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


main = df.Orchestrator.create(orchestrator)

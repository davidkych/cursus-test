# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
import azure.durable_functions as df
from datetime import datetime, timedelta, timezone
from utils import log_to_api


def orchestrator(ctx: df.DurableOrchestrationContext):      # noqa: D401
    """
    Wait until *exec_at_utc* then call ``execute_prompt``.

    All datetimes are handled as **timezone-aware UTC**, which is required for
    Durable Functions timers to resume correctly.
    """
    data = ctx.get_input() or {}
    entity_id = df.EntityId("schedule_entity", "registry")

    # register in entity (for browse/deletion) -------------------------------
    ctx.signal_entity(
        entity_id,
        "add",
        {
            "instanceId":  ctx.instance_id,
            "exec_at_utc": data["exec_at_utc"],
            "prompt_type": data["prompt_type"],
        },
    )

    # ── normalise datetimes (aware UTC) ─────────────────────────────────────
    exec_at = datetime.fromisoformat(data["exec_at_utc"])      # aware (+00:00)
    now_utc = ctx.current_utc_datetime                         # aware UTC

    # ensure the timer is *strictly* in the future ---------------------------
    fire_at = exec_at if exec_at > now_utc else now_utc + timedelta(seconds=1)

    # inline diagnostics (guarded against replay) ----------------------------
    if not ctx.is_replaying:
        delta = (fire_at - now_utc).total_seconds()
        log_to_api(
            "debug",
            f"[diag] orch now={now_utc.isoformat()} "
            f"→ fire_at={fire_at.isoformat()} (Δ={delta:.1f}s)"
        )

    # ── wait & execute ------------------------------------------------------
    yield ctx.create_timer(fire_at)
    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish --------------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


main = df.Orchestrator.create(orchestrator)

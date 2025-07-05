# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
import azure.durable_functions as df
from datetime import datetime
from utils import log_to_api


def orchestrator(ctx: df.DurableOrchestrationContext):    # noqa: D401
    """
    Single-fire orchestrator that waits until *exec_at_utc* and then calls the
    `execute_prompt` activity.

    **Important** – Durable Functions’ replay engine requires the orchestration
    to be *deterministic*: avoid non-deterministic I/O when `ctx.is_replaying`
    is *True*.
    """
    data = ctx.get_input() or {}
    entity_id = df.EntityId("schedule_entity", "registry")

    # ── register in entity (for browse / deletion) ----------------------------
    ctx.signal_entity(
        entity_id,
        "add",
        {
            "instanceId":  ctx.instance_id,
            "exec_at_utc": data["exec_at_utc"],
            "prompt_type": data["prompt_type"],
        },
    )

    # ── normalise datetimes  ➜ **naïve UTC** ---------------------------------
    exec_at = datetime.fromisoformat(data["exec_at_utc"])          # naïve
    now_utc = ctx.current_utc_datetime.replace(tzinfo=None)        # force naïve
    fire_at = max(exec_at, now_utc)

    # ── inline diagnostics (guarded against replay) ---------------------------
    if not ctx.is_replaying:
        delta = (fire_at - now_utc).total_seconds()
        log_to_api(
            "debug",
            f"[diag] orch now={now_utc.isoformat()} "
            f"→ fire_at={fire_at.isoformat()} (Δ={delta:.1f}s)"
        )

    # ── wait & execute --------------------------------------------------------
    yield ctx.create_timer(fire_at)
    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish ---------------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


main = df.Orchestrator.create(orchestrator)

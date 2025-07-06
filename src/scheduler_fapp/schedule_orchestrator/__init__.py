# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
"""
Orchestrator that waits until *exec_at_utc* then calls ``execute_prompt``.

Fix (July 2025 r2)
──────────────────
Durable-Functions Python 1.2.x will resume a timer only when the deadline
is a **naïve** UTC ``datetime`` (i.e. ``tzinfo is None``).  
Passing an aware value such as “2025-07-06T00:12:42+00:00” leaves the
instance forever in *Running*.

We therefore:
    • parse the incoming string (which may contain “+00:00”),  
    • convert it to UTC, and **strip the tzinfo**,  
    • feed the resulting naïve value into ``ctx.create_timer``.
"""
from __future__ import annotations

import azure.durable_functions as df
from datetime import datetime, timedelta, timezone
from utils import log_to_api


def orchestrator(ctx: df.DurableOrchestrationContext):  # noqa: D401
    data = ctx.get_input() or {}
    entity_id = df.EntityId("schedule_entity", "registry")

    # ── register job in the entity -----------------------------------------
    ctx.signal_entity(
        entity_id,
        "add",
        {
            "instanceId":  ctx.instance_id,
            "exec_at_utc": data["exec_at_utc"],
            "prompt_type": data["prompt_type"],
        },
    )

    # ── normalise datetimes -------------------------------------------------
    exec_at = datetime.fromisoformat(data["exec_at_utc"])
    # make sure it is UTC, then **strip tzinfo** → naïve UTC
    if exec_at.tzinfo is None:
        exec_at = exec_at.replace(tzinfo=timezone.utc)
    exec_at = exec_at.astimezone(timezone.utc).replace(tzinfo=None)

    now_utc = ctx.current_utc_datetime.replace(tzinfo=None)  # naïve UTC

    # ensure the timer is strictly in the future ----------------------------
    fire_at = exec_at if exec_at > now_utc else now_utc + timedelta(seconds=1)

    # one-off diagnostics (skipped during replay) ---------------------------
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

    # ── deregister & finish -------------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


# Azure Functions entry-point
main = df.Orchestrator.create(orchestrator)

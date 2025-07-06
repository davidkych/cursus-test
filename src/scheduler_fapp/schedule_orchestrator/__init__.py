# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
"""
Orchestrator that waits until *exec_at_utc* then calls ``execute_prompt``.

Durable-Functions ≤ 1.3.x returns **naïve** UTC from
``ctx.current_utc_datetime``.  If we keep *exec_at* timezone-aware we end up
comparing an aware datetime with a naïve one →  
``TypeError: can't compare offset-naive and offset-aware datetimes``.

**July 2025 r5 — final fix**

* **Normalise both datetimes to *naïve* UTC.**  
  We strip the ``tzinfo`` from *exec_at* (after converting to UTC if necessary)
  so the comparison is always “naïve vs naïve”.
* Rest of the logic unchanged.
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

    # ── normalise datetimes – both **naïve UTC** ---------------------------
    exec_at = datetime.fromisoformat(data["exec_at_utc"])
    if exec_at.tzinfo is not None:                    # strip offset → naïve UTC
        exec_at = exec_at.astimezone(timezone.utc).replace(tzinfo=None)

    now_utc = ctx.current_utc_datetime               # already naïve UTC

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
    yield ctx.create_timer(fire_at)                 # naïve UTC accepted in 1.3.x
    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish -------------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


# Azure Functions entry-point
main = df.Orchestrator.create(orchestrator)

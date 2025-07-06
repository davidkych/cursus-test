# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
"""
Orchestrator that waits until *exec_at_utc* then calls ``execute_prompt``.

### July 2025 · r6 (final)

Durable Functions 1.3.x returns **offset-aware** UTC from  
``ctx.current_utc_datetime`` **on some hosts but offset-naïve on others**  
(depending on the underlying extension build).  
To guarantee we never mix the two kinds we now:

1. **Force *both* timestamps to offset-naïve UTC**  
   – strip any ``tzinfo`` after converting to UTC.
2. Leave the rest of the logic unchanged.

With this normalisation the “can’t compare offset-naïve and offset-aware
datetimes” exception cannot occur and the timer fires as expected.
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
    if exec_at.tzinfo is not None:                        # aware  → naive UTC
        exec_at = exec_at.astimezone(timezone.utc).replace(tzinfo=None)

    now_utc = ctx.current_utc_datetime                   # may be aware or naive
    if now_utc.tzinfo is not None:                       # make it naive as well
        now_utc = now_utc.replace(tzinfo=None)

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
    yield ctx.create_timer(fire_at)                     # naïve UTC works on 1.3.x
    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish -------------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


# Azure Functions entry-point
main = df.Orchestrator.create(orchestrator)

# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
"""
Orchestrator that waits until *exec_at_utc* then calls ``execute_prompt``.

### July 2025 · r7  (aware-UTC fix)

The previous r6 release deliberately stripped ``tzinfo`` from all
timestamps.  That causes the Durable Functions runtime to compare an
offset-naïve value (ours) with an offset-aware one (its own), triggering  
``TypeError: can't compare offset-naive and offset-aware datetimes``.

**r7 keeps every `datetime` object offset-aware in UTC all the way
through**:

1. ``exec_at`` – parsed from the incoming ISO-8601 string – is converted
   to an *aware* UTC value (attaching `timezone.utc` when needed).
2. ``now_utc`` – returned by the runtime – is coerced to aware UTC if
   the host accidentally returns a naïve value.
3. Both values are used as-is; no more stripping of ``tzinfo``.
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

    # ── normalise datetimes – both **aware UTC** ---------------------------
    exec_at = datetime.fromisoformat(data["exec_at_utc"])
    if exec_at.tzinfo is None:                      # naïve → aware UTC
        exec_at = exec_at.replace(tzinfo=timezone.utc)
    else:                                           # aware, but not always UTC
        exec_at = exec_at.astimezone(timezone.utc)

    now_utc = ctx.current_utc_datetime             # may be naïve on some hosts
    if now_utc.tzinfo is None:                     # ensure it’s aware UTC
        now_utc = now_utc.replace(tzinfo=timezone.utc)

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

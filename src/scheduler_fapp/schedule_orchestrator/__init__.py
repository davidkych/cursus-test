# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
"""
Orchestrator that waits until *exec_at_utc* then calls ``execute_prompt``.

Durable-Functions Python ≤ 1.3.x will resume a timer **only** when the deadline
is a *naïve* (offset-free) UTC ``datetime``.  Passing an aware value
(`+00:00`) silently stalls the orchestration.

Fix (July 2025 r4)
──────────────────
* Convert **both** `exec_at` **and** `now_utc` to *naïve* UTC before comparison
  **and** before calling ``create_timer``.  
  This avoids the “ignored timer” bug while still keeping the comparison legal.
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

    # ── normalise datetimes – convert to **naïve UTC** ---------------------
    exec_at_aware = datetime.fromisoformat(data["exec_at_utc"])
    if exec_at_aware.tzinfo is None:                # tolerate naïve input
        exec_at_aware = exec_at_aware.replace(tzinfo=timezone.utc)
    exec_at = exec_at_aware.astimezone(timezone.utc).replace(tzinfo=None)

    now_aware = ctx.current_utc_datetime            # aware UTC
    now_utc   = now_aware.replace(tzinfo=None)      # ← make naïve

    # ensure the timer is strictly in the future ----------------------------
    fire_at = exec_at if exec_at > now_utc else now_utc + timedelta(seconds=1)

    # diagnostics once per run (skipped during replay) ----------------------
    if not ctx.is_replaying:
        delta = (fire_at - now_utc).total_seconds()
        log_to_api(
            "debug",
            f"[diag] orch now={now_aware.isoformat()} "
            f"→ fire_at={fire_at.isoformat()} (Δ={delta:.1f}s)"
        )

    # ── wait & execute ------------------------------------------------------
    yield ctx.create_timer(fire_at)                 # needs naïve UTC
    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish -------------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


# Azure Functions entry-point
main = df.Orchestrator.create(orchestrator)

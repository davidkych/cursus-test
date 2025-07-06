# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
"""
Orchestrator that waits until *exec_at_utc* then calls ``execute_prompt``.

### July 2025 · r8 (timer-naïve fix)

* r6 crashed (naïve vs aware mismatch)  
* r7 kept everything offset-aware but the East-Asia host interpreted an
  aware value as **local** time, pushing the timer ~8 h into the future.

**r8 solution**

* Keep comparisons *aware* (UTC) – no more Python `TypeError`.
* **Just before calling `ctx.create_timer` strip the tzinfo**, handing the
  Durable runtime a **naïve UTC** `datetime`.  
  That is the format the runtime expects regardless of the host region.
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

    # ── parse / normalise to **aware UTC** ---------------------------------
    exec_at = datetime.fromisoformat(data["exec_at_utc"])
    if exec_at.tzinfo is None:                       # naïve → aware UTC
        exec_at = exec_at.replace(tzinfo=timezone.utc)
    else:                                            # aware → ensure UTC
        exec_at = exec_at.astimezone(timezone.utc)

    now_utc = ctx.current_utc_datetime              # may be naïve
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    # ensure timer is in the future -------------------------------------------------
    fire_at = exec_at if exec_at > now_utc else now_utc + timedelta(seconds=1)

    # one-off diagnostics (skipped during replay) -----------------------------------
    if not ctx.is_replaying:
        delta = (fire_at - now_utc).total_seconds()
        log_to_api(
            "debug",
            f"[diag] orch now={now_utc.isoformat()} "
            f"→ fire_at={fire_at.isoformat()} (Δ={delta:.1f}s)"
        )

    # ── WAIT & EXECUTE --------------------------------------------------------------
    # Durable runtime expects **naïve UTC** here, otherwise an aware value
    # is interpreted as local time in the host’s region.
    yield ctx.create_timer(fire_at.replace(tzinfo=None))

    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish ---------------------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


# Azure Functions entry-point
main = df.Orchestrator.create(orchestrator)

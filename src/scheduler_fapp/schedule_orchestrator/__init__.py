# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
"""
Orchestrator that waits until *exec_at_utc* then calls ``execute_prompt``.

### July 2025 · r9 (final)

* r6 crashed because we compared naïve ↔ aware datetimes.  
* r7 fixed the crash but made timers eight hours late.  
* r8 still hit the same `TypeError` on some hosts.

**r9 canonical rule**

> *Inside the orchestrator everything is UTC-**naïve*** – that is what the
> Durable Python SDK and the DF extension always agree on.  
> We keep the incoming timestamp offset-aware long enough to validate it,
> then strip `tzinfo` from **both** operands **before** any arithmetic or
> comparisons, and pass that naïve value straight to `create_timer()`.  
> No other datetime values remain aware, so the mismatch can never occur
> again on any host or SDK build.
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

    # ── 1.  Parse incoming ISO string  ➜ aware UTC -------------------------
    exec_at_aw = datetime.fromisoformat(data["exec_at_utc"])
    if exec_at_aw.tzinfo is None:
        exec_at_aw = exec_at_aw.replace(tzinfo=timezone.utc)
    else:
        exec_at_aw = exec_at_aw.astimezone(timezone.utc)

    # ── 2.  Current time from runtime  ➜ aware/naïve mix ⇒ force UTC aware -
    now_aw = ctx.current_utc_datetime
    if now_aw.tzinfo is None:
        now_aw = now_aw.replace(tzinfo=timezone.utc)
    else:
        now_aw = now_aw.astimezone(timezone.utc)

    # ── 3.  Strip tzinfo from *both*  ➜ canonical UTC-naïve -----------------
    exec_at = exec_at_aw.replace(tzinfo=None)
    now_utc = now_aw.replace(tzinfo=None)

    # ensure timer is strictly in the future ---------------------------------
    fire_at = exec_at if exec_at > now_utc else now_utc + timedelta(seconds=1)

    # one-off diagnostics (skipped during replay) ---------------------------
    if not ctx.is_replaying:
        delta = (fire_at - now_utc).total_seconds()
        log_to_api(
            "debug",
            f"[diag] orch now={now_aw.isoformat()} "
            f"→ fire_at={fire_at.isoformat()} (Δ={delta:.1f}s)"
        )

    # ── WAIT & EXECUTE ------------------------------------------------------
    # The Durable runtime requires a naïve UTC datetime here.
    yield ctx.create_timer(fire_at)

    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish -------------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


# Azure Functions entry-point
main = df.Orchestrator.create(orchestrator)

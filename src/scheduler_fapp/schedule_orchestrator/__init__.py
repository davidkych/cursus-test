# ── src/scheduler_fapp/schedule_orchestrator/__init__.py ─────────────
"""
Orchestrator that waits until *exec_at_utc* then calls ``execute_prompt``.

### July 2025 · r11

The orchestrator now stores optional tag metadata alongside the instance
so that later queries can filter jobs by tag/secondary/tertiary tags.
Everything remains **UTC-aware** from start to finish.
"""
from __future__ import annotations

import azure.durable_functions as df
from datetime import datetime, timedelta, timezone
from utils import log_to_api


def orchestrator(ctx: df.DurableOrchestrationContext):  # noqa: D401
    data = ctx.get_input() or {}
    entity_id = df.EntityId("schedule_entity", "registry")

    # ── register job in the entity (now with tags) ---------------------------
    ctx.signal_entity(
        entity_id,
        "add",
        {
            "instanceId": ctx.instance_id,
            "exec_at_utc": data["exec_at_utc"],
            "prompt_type": data["prompt_type"],
            "tag": data.get("tag"),
            "secondary_tag": data.get("secondary_tag"),
            "tertiary_tag": data.get("tertiary_tag"),
        },
    )

    # ── timestamp handling (UTC-aware all the way) ---------------------------
    exec_at = datetime.fromisoformat(data["exec_at_utc"])
    if exec_at.tzinfo is None:  # defensive (should already be aware)
        exec_at = exec_at.replace(tzinfo=timezone.utc)
    else:
        exec_at = exec_at.astimezone(timezone.utc)

    now_utc = ctx.current_utc_datetime
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    fire_at = exec_at if exec_at > now_utc else now_utc + timedelta(seconds=1)

    # one-off diagnostics (skipped during replay)
    if not ctx.is_replaying:
        delta = (fire_at - now_utc).total_seconds()
        log_to_api(
            "debug",
            f"[diag] orch now={now_utc.isoformat()} "
            f"→ fire_at={fire_at.isoformat()} (Δ={delta:.1f}s)",
        )

    # ── WAIT & EXECUTE -------------------------------------------------------
    yield ctx.create_timer(fire_at)
    result = yield ctx.call_activity("execute_prompt", data)

    # ── deregister & finish --------------------------------------------------
    ctx.signal_entity(entity_id, "remove", ctx.instance_id)
    if not ctx.is_replaying:
        log_to_api("info", f"Executed scheduled job {ctx.instance_id}")
    return result


# Azure Functions entry-point
main = df.Orchestrator.create(orchestrator)

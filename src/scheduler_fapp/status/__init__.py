# ── src/scheduler_fapp/status/__init__.py ────────────────────────────
"""
GET /api/status/{instanceId}

Returns the full Durable-Functions orchestration status **with history**
so we can diagnose timer issues, race conditions, etc.

July 2025 · r5  
────────────────
* FIX: handles both old (< 1.3.x) and new (≥ 1.3.x) behaviours where
  `DurableOrchestrationStatus.input` may be a JSON **string** instead of
  a dict.  Guard against that to avoid AttributeError.
"""
from __future__ import annotations

import azure.functions as func
import azure.durable_functions as df
import json
import logging


async def main(                       # HTTP GET  /api/status/{instanceId}
    req:    func.HttpRequest,
    client: str,                      # durableClient binding
) -> func.HttpResponse:               # noqa: D401
    instance_id = req.route_params.get("instanceId")

    if not instance_id:                              # unlikely – route ensures
        return func.HttpResponse(
            json.dumps({"error": "instanceId missing in route"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        dclient = df.DurableOrchestrationClient(client)

        # ── fetch status with full history & outputs ───────────────────────
        status = await dclient.get_status(
            instance_id,
            show_history=True,
            show_history_output=True,
            show_input=True,
        )

        if status is None:
            return func.HttpResponse(
                json.dumps({"error": "Instance not found"}),
                status_code=404,
                mimetype="application/json",
            )

        # azure-functions-durable ≥ 1.3.x → dict | ≤ 1.2.x → str
        raw  = status.to_json()
        data = raw if isinstance(raw, dict) else json.loads(raw)

        # ── Surface tag metadata at top level ──────────────────────────────
        raw_input = data.get("input")

        # Durable ≥ 1.3.x returns `.input` as *string* JSON – parse it.
        if isinstance(raw_input, str):
            try:
                orchestration_input = json.loads(raw_input)
            except json.JSONDecodeError:
                logging.warning("Unable to parse orchestration input JSON")
                orchestration_input = {}
        else:
            orchestration_input = raw_input or {}

        if isinstance(orchestration_input, dict):
            for key in ("tag", "secondary_tag", "tertiary_tag"):
                if key in orchestration_input:
                    data[key] = orchestration_input[key]

        return func.HttpResponse(
            json.dumps(data, indent=2, default=str),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as exc:                          # noqa: BLE001
        logging.exception("Unhandled error in /status")
        return func.HttpResponse(
            json.dumps({"error": str(exc),
                        "type":  exc.__class__.__name__}),
            status_code=500,
            mimetype="application/json",
        )

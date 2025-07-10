# src/scheduler_fapp/schedule_starter/__init__.py
import azure.functions as func
import azure.durable_functions as df
import json
import logging
import os
from typing import Any

from utils import to_utc_iso, log_to_api


def _make_location_header(instance_id: str) -> str:
    """Build a public status-polling URL for the given instance_id."""
    site_name = os.getenv("WEBSITE_SITE_NAME", "")
    base = (
        f"https://{site_name}.azurewebsites.net"
        if site_name
        else "http://localhost:7071"
    )
    return f"{base}/runtime/webhooks/durabletask/instances/{instance_id}"


async def main(  # HTTP POST /api/schedule
    req: func.HttpRequest,
    starter: str,
) -> func.HttpResponse:  # noqa: D401
    """
    Starts an orchestration for the requested schedule.

    July 2025 – now accepts optional **tag**, **secondary_tag** and
    **tertiary_tag** fields which are passed through unchanged.
    """
    try:
        logging.info("↪ /schedule called")

        # ── Parse & validate body ─────────────────────────────────────
        try:
            body: dict[str, Any] = req.get_json()  # type: ignore[assignment]
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON body"}),
                status_code=400,
                mimetype="application/json",
            )

        missing = [k for k in ("exec_at", "prompt_type", "payload") if k not in body]
        if missing:
            return func.HttpResponse(
                json.dumps({"error": f"Missing keys: {', '.join(missing)}"}),
                status_code=400,
                mimetype="application/json",
            )

        try:
            exec_at_utc = to_utc_iso(body["exec_at"])
        except ValueError as exc:
            return func.HttpResponse(
                json.dumps({"error": str(exc)}),
                status_code=400,
                mimetype="application/json",
            )

        orch_input = {
            "exec_at_utc":  exec_at_utc,
            "prompt_type":  body["prompt_type"],
            "payload":      body["payload"],
            # NEW – forward optional tags (may be None)
            "tag":           body.get("tag"),
            "secondary_tag": body.get("secondary_tag"),
            "tertiary_tag":  body.get("tertiary_tag"),
        }

        # ── Kick off orchestration ───────────────────────────────────
        client = df.DurableOrchestrationClient(starter)
        instance_id = await client.start_new(
            "schedule_orchestrator",
            None,
            orch_input,
        )
        logging.info("🎬 Started orchestration %s", instance_id)

        log_to_api(
            "info",
            f"Scheduled {body['prompt_type']} at {body['exec_at']} "
            f"(instance {instance_id})",
            secondary_tag=body.get("tag") or "scheduler",
            tertiary_tag=body.get("secondary_tag"),
        )

        # ── Custom 202 Accepted response ─────────────────────────────
        location = _make_location_header(instance_id)
        return func.HttpResponse(
            json.dumps({"id": instance_id}),
            status_code=202,
            mimetype="application/json",
            headers={
                "Location": location,
                "Retry-After": "5",
            },
        )

    # ── Diagnostics ──────────────────────────────────────────────────
    except Exception as exc:  # noqa: BLE001
        logging.exception("Unhandled error in /schedule")
        return func.HttpResponse(
            json.dumps({"error": str(exc), "type": exc.__class__.__name__}),
            status_code=500,
            mimetype="application/json",
        )

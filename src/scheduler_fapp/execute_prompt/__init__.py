# ── src/scheduler_fapp/execute_prompt/__init__.py ────────────────────
"""
Durable **activity** that performs the real work – executing one prompt.

Important design goal
──────────────────────
*Always complete* – never bubble an exception back to the orchestrator.
That lets the schedule finish regardless of whether the downstream API
succeeds (fire-and-forget semantics).
"""
import logging
from utils import execute_prompt, log_to_api

def main(data: dict):  # noqa: D401
    prompt_type = data.get("prompt_type")
    payload     = data.get("payload")

    try:
        result = execute_prompt(prompt_type, payload)
        log_to_api("info", f"Prompt {prompt_type} executed – result={result}")
        return result or {"status": "ok"}

    except Exception as exc:  # noqa: BLE001
        # Catch-all just in case a handler leaked an exception
        log_to_api("error", f"Prompt {prompt_type} unhandled error: {exc}")
        logging.exception("Prompt execution failed")
        return {"status": "failed", "error": str(exc)}

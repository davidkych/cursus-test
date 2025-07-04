import logging
from utils import execute_prompt, log_to_api

def main(data: dict):    # noqa: D401
    """
    Activity that performs the real work – executing the chosen prompt.
    """
    prompt_type = data.get("prompt_type")
    payload     = data.get("payload")

    try:
        result = execute_prompt(prompt_type, payload)
        log_to_api("info", f"Prompt {prompt_type} executed successfully")
        return result
    except Exception as exc:          # noqa: BLE001
        log_to_api("error", f"Prompt {prompt_type} failed: {exc}")
        logging.exception("Prompt execution failed")
        raise

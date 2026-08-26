from typing import Any

RETRY_ATTEMPTS = 5
RETRY_INITIAL_DELAY_SECONDS = 2.0
RETRY_MAX_DELAY_SECONDS = 30.0
RETRY_EXP_BASE = 2.0
RETRY_JITTER = 0.3


def retry_options() -> Any:
    from google.genai import types as genai_types

    return genai_types.HttpRetryOptions(
        attempts=RETRY_ATTEMPTS,
        initial_delay=RETRY_INITIAL_DELAY_SECONDS,
        max_delay=RETRY_MAX_DELAY_SECONDS,
        exp_base=RETRY_EXP_BASE,
        jitter=RETRY_JITTER,
    )


def gemini_model(model: str) -> Any:
    from google.adk.models.google_llm import Gemini

    return Gemini(model=model, retry_options=retry_options())


def client_http_options() -> Any:
    from google.genai import types as genai_types

    return genai_types.HttpOptions(retry_options=retry_options())

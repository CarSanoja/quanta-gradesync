from typing import Any

# Gemini on Vertex has no published per-model request quota for the models we
# use: capacity is shared dynamically across projects, and a 429 means the pool
# is contended rather than that we crossed a line of our own. Congestion of that
# kind lasts longer than a few seconds, and the old ceiling of six made the whole
# retry window about twenty-five — so a burst of three batches gave up on fifteen
# exams that a longer wait would have graded.
#
# This is a batch job triggered by a bucket upload. Nobody is watching a spinner,
# so waiting is cheap and giving up is not.
RETRY_ATTEMPTS = 8
RETRY_INITIAL_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 60.0
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

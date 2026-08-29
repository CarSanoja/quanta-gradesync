from autocurricula.agents.adk_llm import build_structured_agent
from autocurricula.agents.gemini_retry import (
    RETRY_ATTEMPTS,
    client_http_options,
    gemini_model,
    retry_options,
)
from autocurricula.schemas.armor import ArmorVerdict


def test_retry_options_cover_transient_vertex_failures() -> None:
    options = retry_options()
    assert options.attempts == RETRY_ATTEMPTS
    assert options.initial_delay > 0
    assert options.max_delay >= options.initial_delay


def test_gemini_model_keeps_the_name_and_carries_retries() -> None:
    model = gemini_model("gemini-3.5-flash-lite")
    assert model.model == "gemini-3.5-flash-lite"
    assert model.retry_options.attempts == RETRY_ATTEMPTS


def test_structured_agents_are_built_on_the_retrying_model() -> None:
    agent = build_structured_agent(
        name="retry_probe",
        model="gemini-3.5-flash-lite",
        instruction="return json",
        output_schema=ArmorVerdict,
    )
    assert agent.model.model == "gemini-3.5-flash-lite"
    assert agent.model.retry_options.attempts == RETRY_ATTEMPTS


def test_raw_clients_share_the_same_retry_policy() -> None:
    assert client_http_options().retry_options.attempts == RETRY_ATTEMPTS


def test_the_backoff_can_outlast_a_congested_shared_quota() -> None:
    """Gemini on Vertex publishes no per-model limit for the models we use.

    Capacity is shared dynamically, so a 429 means the pool is contended, not
    that we crossed a line of our own — and that congestion outlasts seconds. A
    ceiling of six gave the whole retry window about twenty-five seconds, and a
    burst of three batches abandoned fifteen exams a longer wait would have
    graded. Nobody watches a spinner on a bucket-triggered batch.
    """
    from autocurricula.agents.gemini_retry import (
        RETRY_ATTEMPTS,
        RETRY_EXP_BASE,
        RETRY_INITIAL_DELAY_SECONDS,
        RETRY_MAX_DELAY_SECONDS,
    )

    delay, window = RETRY_INITIAL_DELAY_SECONDS, 0.0
    for _ in range(RETRY_ATTEMPTS - 1):
        window += min(delay, RETRY_MAX_DELAY_SECONDS)
        delay *= RETRY_EXP_BASE

    assert window >= 120, f"retry window is only {window:.0f}s"

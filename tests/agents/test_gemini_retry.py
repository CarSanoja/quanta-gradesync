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

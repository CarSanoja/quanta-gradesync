import json
from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode

from autocurricula.config.settings import Settings
from autocurricula.core.telemetry import LlmSpanCapture
from autocurricula.core.telemetry.live_context import LiveScope, push_scope, reset_scope
from autocurricula.schemas.live_events import LiveEventKind, LiveEventStatus

REQUEST_JSON = json.dumps(
    {
        "model": "gemini-3.5-flash",
        "contents": [
            {"role": "user", "parts": [{"text": "first turn"}]},
            {"role": "user", "parts": [{"text": "grade this answer"}, {"text": "page 2"}]},
        ],
    }
)
RESPONSE_JSON = json.dumps(
    {"content": {"role": "model", "parts": [{"text": "score 8 of 10"}]}}
)

ADK_ATTRIBUTES = {
    "gen_ai.request.model": "gemini-3.5-flash",
    "gen_ai.usage.input_tokens": 1200,
    "gen_ai.usage.output_tokens": 300,
    "gen_ai.response.finish_reasons": ("stop",),
    "gcp.vertex.agent.llm_request": REQUEST_JSON,
    "gcp.vertex.agent.llm_response": RESPONSE_JSON,
}


def build_tracer(max_chars: int) -> Any:
    provider = TracerProvider()
    provider.add_span_processor(
        LlmSpanCapture(Settings(local_mode=True, telemetry_payload_max_chars=max_chars))
    )
    return provider.get_tracer("test")


@pytest.fixture
def captured() -> Iterator[list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []

    def emit(**fields: Any) -> None:
        events.append(fields)

    scope = LiveScope(job_id="job-1", trace_id="trace-1", emit=emit, stage="GRADE")
    scope.agent_id = "grading-agent"
    token = push_scope(scope)
    try:
        yield events
    finally:
        reset_scope(token)


def test_call_llm_span_becomes_llm_event(captured: list[dict[str, Any]]) -> None:
    tracer = build_tracer(4000)
    with tracer.start_as_current_span("call_llm") as span:
        span.set_attributes(ADK_ATTRIBUTES)

    assert len(captured) == 1
    event = captured[0]
    assert event["kind"] is LiveEventKind.LLM_CALL
    assert event["status"] is LiveEventStatus.OK
    exchange = event["llm"]
    assert exchange.model == "gemini-3.5-flash"
    assert exchange.request_excerpt == "grade this answer\npage 2"
    assert exchange.response_excerpt == "score 8 of 10"
    assert exchange.finish_reason == "stop"
    assert exchange.input_tokens == 1200
    assert exchange.output_tokens == 300
    assert exchange.total_tokens == 1500
    assert exchange.truncated is False


def test_excerpts_are_truncated_with_flag(captured: list[dict[str, Any]]) -> None:
    tracer = build_tracer(200)
    long_request = json.dumps(
        {"contents": [{"role": "user", "parts": [{"text": "x" * 500}]}]}
    )
    with tracer.start_as_current_span("call_llm") as span:
        span.set_attribute("gcp.vertex.agent.llm_request", long_request)
        span.set_attribute("gcp.vertex.agent.llm_response", RESPONSE_JSON)

    exchange = captured[0]["llm"]
    assert len(exchange.request_excerpt) == 200
    assert exchange.truncated is True
    assert captured[0]["attributes"]["payload.truncated"] is True


def test_error_span_status_propagates(captured: list[dict[str, Any]]) -> None:
    tracer = build_tracer(4000)
    with tracer.start_as_current_span("call_llm") as span:
        span.set_attributes(ADK_ATTRIBUTES)
        span.set_status(Status(StatusCode.ERROR, "quota"))

    assert captured[0]["status"] is LiveEventStatus.ERROR
    assert captured[0]["name"] == "call_llm"


def test_nested_generate_content_span_is_not_double_counted(
    captured: list[dict[str, Any]],
) -> None:
    tracer = build_tracer(4000)
    with tracer.start_as_current_span("call_llm") as outer:
        outer.set_attributes(ADK_ATTRIBUTES)
        with tracer.start_as_current_span("generate_content gemini-3.5-flash") as inner:
            inner.set_attributes(
                {
                    "gen_ai.request.model": "gemini-3.5-flash",
                    "gen_ai.usage.input_tokens": 1200,
                    "gen_ai.usage.output_tokens": 300,
                }
            )

    assert len(captured) == 1
    assert captured[0]["name"] == "call_llm"
    assert captured[0]["llm"].total_tokens == 1500


def test_non_llm_span_is_ignored(captured: list[dict[str, Any]]) -> None:
    tracer = build_tracer(4000)
    with tracer.start_as_current_span("Stage_grade"):
        pass

    assert captured == []


def test_no_event_without_live_scope() -> None:
    events: list[dict[str, Any]] = []
    scope = LiveScope(job_id="job-1", trace_id="trace-1", emit=lambda **kw: events.append(kw))
    token = push_scope(scope)
    reset_scope(token)
    tracer = build_tracer(4000)
    with tracer.start_as_current_span("call_llm") as span:
        span.set_attributes(ADK_ATTRIBUTES)

    assert events == []

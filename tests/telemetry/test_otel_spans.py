from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import get_current_span

from autocurricula.core.telemetry.otel_spans import (
    OTEL_JOB_ID,
    OTEL_STAGE,
    OTEL_TRACE_ID,
    job_parent_context,
    mirror_attributes,
    otel_span,
)
from autocurricula.core.telemetry.trace_ids import cloud_trace_id

TRACE_ID = "9c41e77b20f5a3d6"
JOB_ID = "job-otel-1"


@pytest.fixture
def exporter() -> Iterator[InMemorySpanExporter]:
    collected = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    processor = SimpleSpanProcessor(collected)
    provider.add_span_processor(processor)
    try:
        yield collected
    finally:
        processor.shutdown()


def finished(collected: InMemorySpanExporter, name: str):
    for span in collected.get_finished_spans():
        if span.name == name:
            return span
    raise AssertionError(f"no finished span named {name!r}")


def test_job_parent_context_carries_the_cloud_trace_id() -> None:
    context = job_parent_context(TRACE_ID)
    span_context = get_current_span(context).get_span_context()
    assert span_context.trace_id == int(cloud_trace_id(TRACE_ID), 16)
    assert span_context.span_id != 0
    assert span_context.is_remote is True


def test_gradesync_spans_join_the_job_trace(exporter: InMemorySpanExporter) -> None:
    parent_context = job_parent_context(TRACE_ID)
    with otel_span(
        "Stage_grade",
        trace_id=TRACE_ID,
        job_id=JOB_ID,
        stage="GRADE",
        parent_context=parent_context,
    ):
        pass

    span = finished(exporter, "Stage_grade")
    assert span.context.trace_id == int(cloud_trace_id(TRACE_ID), 16)
    assert span.attributes[OTEL_TRACE_ID] == TRACE_ID
    assert span.attributes[OTEL_JOB_ID] == JOB_ID
    assert span.attributes[OTEL_STAGE] == "GRADE"


def test_foreign_llm_spans_nest_under_the_gradesync_span(
    exporter: InMemorySpanExporter,
) -> None:
    parent_context = job_parent_context(TRACE_ID)
    with otel_span(
        "Grading_stu-1",
        trace_id=TRACE_ID,
        job_id=JOB_ID,
        stage="GRADE",
        parent_context=parent_context,
    ):
        adk_tracer = trace.get_tracer("gcp.vertex.agent")
        with adk_tracer.start_as_current_span("call_llm"):
            pass

    grading = finished(exporter, "Grading_stu-1")
    call_llm = finished(exporter, "call_llm")
    assert call_llm.parent is not None
    assert call_llm.parent.span_id == grading.context.span_id
    assert call_llm.context.trace_id == grading.context.trace_id


def test_nested_gradesync_spans_keep_a_single_trace(
    exporter: InMemorySpanExporter,
) -> None:
    parent_context = job_parent_context(TRACE_ID)
    with otel_span(
        "Stage_grade",
        trace_id=TRACE_ID,
        job_id=JOB_ID,
        stage="GRADE",
        parent_context=parent_context,
    ):
        with otel_span(
            "ArmorScreen",
            trace_id=TRACE_ID,
            job_id=JOB_ID,
            stage="GRADE",
            parent_context=parent_context,
        ):
            pass

    stage = finished(exporter, "Stage_grade")
    armor = finished(exporter, "ArmorScreen")
    assert armor.parent.span_id == stage.context.span_id
    assert stage.parent is not None
    assert stage.parent.trace_id == int(cloud_trace_id(TRACE_ID), 16)


def test_mirror_attributes_copies_scalars_and_tolerates_no_span(
    exporter: InMemorySpanExporter,
) -> None:
    with otel_span(
        "Grading_stu-2",
        trace_id=TRACE_ID,
        job_id=JOB_ID,
        stage="GRADE",
        parent_context=job_parent_context(TRACE_ID),
    ) as span:
        mirror_attributes(span, {"agent.id": "grading-agent", "gen_ai.calls": 3})

    graded = finished(exporter, "Grading_stu-2")
    assert graded.attributes["agent.id"] == "grading-agent"
    assert graded.attributes["gen_ai.calls"] == 3
    mirror_attributes(None, {"agent.id": "grading-agent"})

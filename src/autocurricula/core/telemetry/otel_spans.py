import hashlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from opentelemetry.trace.propagation import set_span_in_context

from autocurricula.core.telemetry.trace_ids import cloud_trace_id

logger = logging.getLogger(__name__)

TRACER_NAME = "gradesync"
OTEL_JOB_ID = "gradesync.job_id"
OTEL_STAGE = "gradesync.stage"
OTEL_TRACE_ID = "gradesync.trace_id"


def job_parent_context(trace_id: str) -> Any:
    try:
        digest = hashlib.sha256(trace_id.encode("utf-8")).hexdigest()
        span_context = SpanContext(
            trace_id=int(cloud_trace_id(trace_id), 16),
            span_id=int(digest[:16], 16) or 1,
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        return set_span_in_context(NonRecordingSpan(span_context))
    except Exception as error:
        logger.debug("otel parent context unavailable: %s", error)
        return None


@contextmanager
def otel_span(
    name: str,
    *,
    trace_id: str,
    job_id: str,
    stage: str | None,
    parent_context: Any,
) -> Iterator[Any]:
    try:
        tracer = trace.get_tracer(TRACER_NAME)
        current = trace.get_current_span().get_span_context()
        context = None if current.is_valid else parent_context
        manager = tracer.start_as_current_span(name, context=context)
    except Exception as error:
        logger.debug("otel span unavailable for %s: %s", name, error)
        yield None
        return
    with manager as span:
        _seed(span, trace_id=trace_id, job_id=job_id, stage=stage)
        yield span


def mirror_attributes(span: Any, attributes: dict[str, Any]) -> None:
    if span is None:
        return
    try:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    except Exception as error:
        logger.debug("otel span annotate failed: %s", error)


def _seed(span: Any, *, trace_id: str, job_id: str, stage: str | None) -> None:
    try:
        span.set_attribute(OTEL_TRACE_ID, trace_id)
        if job_id:
            span.set_attribute(OTEL_JOB_ID, job_id)
        if stage:
            span.set_attribute(OTEL_STAGE, stage)
    except Exception as error:
        logger.debug("otel span seed failed: %s", error)

import json
import logging
from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider

from autocurricula.config.settings import Settings
from autocurricula.core.telemetry import install_structured_logging
from autocurricula.core.telemetry.structured_logging import (
    SPAN_FIELD,
    TRACE_FIELD,
    JsonLogFormatter,
)


def make_record(message: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="autocurricula.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@pytest.fixture
def root_logger_state() -> Iterator[None]:
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    try:
        yield
    finally:
        root.handlers = handlers
        root.setLevel(level)


def test_formatter_emits_json_with_severity_and_fields() -> None:
    payload = json.loads(
        JsonLogFormatter("proj").format(make_record(json_fields={"job_id": "job-1"}))
    )
    assert payload["severity"] == "WARNING"
    assert payload["message"] == "hello"
    assert payload["logger"] == "autocurricula.test"
    assert payload["job_id"] == "job-1"
    assert payload["timestamp"].endswith("+00:00")
    assert TRACE_FIELD not in payload


def test_formatter_adds_trace_correlation_inside_span() -> None:
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("Stage_grade") as span:
        payload = json.loads(JsonLogFormatter("proj").format(make_record()))
        context = span.get_span_context()

    assert payload[TRACE_FIELD] == f"projects/proj/traces/{context.trace_id:032x}"
    assert payload[SPAN_FIELD] == f"{context.span_id:016x}"


def test_formatter_omits_trace_field_without_project() -> None:
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("Stage_grade"):
        payload = json.loads(JsonLogFormatter("").format(make_record()))

    assert TRACE_FIELD not in payload
    assert SPAN_FIELD in payload


def test_install_is_opt_in_and_idempotent(root_logger_state: None) -> None:
    assert install_structured_logging(Settings(local_mode=True, log_json=False)) is False
    settings = Settings(local_mode=True, log_json=True)
    assert install_structured_logging(settings) is True
    assert install_structured_logging(settings) is False
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, JsonLogFormatter)


def test_gcp_mode_defaults_to_json_logs() -> None:
    assert Settings(local_mode=False, gcp_project_id="proj").resolved_log_json is True
    assert Settings(local_mode=True).resolved_log_json is False

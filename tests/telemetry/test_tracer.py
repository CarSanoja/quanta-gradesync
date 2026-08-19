import pytest

from autocurricula.core.telemetry import Recorder
from autocurricula.schemas.telemetry import (
    ATTR_AGENT_STAGE,
    ATTR_GEN_AI_SYSTEM,
    SpanStatus,
)


def test_recorder_nests_child_spans_under_parent() -> None:
    recorder = Recorder(trace_id="trace0001")
    with recorder.span("Stage_grade", stage="GRADE") as parent:
        with recorder.span("FaithfulnessVerification", parent=parent) as child:
            child.set("checked", True)

    spans = recorder.spans
    assert [span.name for span in spans] == [
        "Stage_grade",
        "FaithfulnessVerification",
    ]
    assert spans[1].parent_id == parent.span_id
    assert spans[0].parent_id is None
    tree = recorder.tree()
    root_child = tree["root"][0]
    assert root_child["span"]["name"] == "Stage_grade"
    assert root_child["children"][0]["span"]["name"] == "FaithfulnessVerification"


def test_recorder_marks_error_spans_and_reraises() -> None:
    recorder = Recorder(trace_id="trace0002")
    with pytest.raises(RuntimeError, match="boom"):
        with recorder.span("Stage_sync", stage="SYNC"):
            raise RuntimeError("boom")

    span = recorder.spans[0]
    assert span.status == SpanStatus.ERROR
    assert span.attributes["error.type"] == "RuntimeError"


def test_recorder_carries_mandatory_attributes() -> None:
    recorder = Recorder(trace_id="trace0003")
    with recorder.span(
        "Grading_sub-1",
        stage="GRADE",
        attributes={ATTR_GEN_AI_SYSTEM: "google_gemini", ATTR_AGENT_STAGE: "GRADE"},
    ) as span:
        span.set("gen_ai.usage.tokens", 2150)

    attributes = recorder.spans[0].attributes
    assert attributes[ATTR_GEN_AI_SYSTEM] == "google_gemini"
    assert attributes[ATTR_AGENT_STAGE] == "GRADE"
    assert attributes["gen_ai.usage.tokens"] == 2150
    assert recorder.spans[0].duration_ms >= 0.0


def test_span_ids_are_deterministic_per_recorder() -> None:
    recorder = Recorder(trace_id="trace0004")
    with recorder.span("a"):
        pass
    with recorder.span("b"):
        pass
    assert [span.span_id for span in recorder.spans] == ["sp0001", "sp0002"]
    assert all(span.trace_id == "trace0004" for span in recorder.spans)

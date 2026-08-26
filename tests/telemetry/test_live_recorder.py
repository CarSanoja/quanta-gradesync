import json
from pathlib import Path

import pytest

from autocurricula.core.telemetry import LocalLiveSink, NullLiveSink, Recorder
from autocurricula.core.telemetry.live_context import get_scope
from autocurricula.schemas.live_events import LiveEvent, LiveEventKind, LiveEventStatus
from autocurricula.schemas.telemetry import ATTR_AGENT_ID


def read_events(data_dir: Path, job_id: str) -> list[LiveEvent]:
    path = data_dir / "live" / f"{job_id}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [LiveEvent.model_validate(json.loads(line)) for line in lines]


def test_recorder_emits_start_and_end_events_in_sequence(tmp_path: Path) -> None:
    sink = LocalLiveSink(tmp_path)
    recorder = Recorder("trace-live-01", sink=sink, job_id="job-1")
    with recorder.span("Stage_grade", stage="GRADE") as parent:
        with recorder.span("Grading_sub-1", parent=parent) as child:
            child.set("student_id", "stu-7")
    sink.flush(5.0)

    events = read_events(tmp_path, "job-1")
    assert [event.seq for event in events] == [1, 2, 3, 4]
    assert [(event.kind, event.name) for event in events] == [
        (LiveEventKind.SPAN_START, "Stage_grade"),
        (LiveEventKind.SPAN_START, "Grading_sub-1"),
        (LiveEventKind.SPAN_END, "Grading_sub-1"),
        (LiveEventKind.SPAN_END, "Stage_grade"),
    ]
    assert events[0].status is LiveEventStatus.RUNNING
    assert events[2].status is LiveEventStatus.OK
    assert events[2].parent_span_id == parent.span_id
    assert events[2].span_id == "sp0002"
    assert events[2].duration_ms is not None
    assert events[3].stage == "GRADE"


def test_recorder_reports_error_status_on_live_feed(tmp_path: Path) -> None:
    sink = LocalLiveSink(tmp_path)
    recorder = Recorder("trace-live-02", sink=sink, job_id="job-2")
    with pytest.raises(RuntimeError, match="boom"):
        with recorder.span("Stage_sync", stage="SYNC"):
            raise RuntimeError("boom")
    sink.flush(5.0)

    events = read_events(tmp_path, "job-2")
    assert events[-1].kind is LiveEventKind.SPAN_END
    assert events[-1].status is LiveEventStatus.ERROR
    assert events[-1].attributes["error.type"] == "RuntimeError"


def test_span_attributes_flow_into_live_scope(tmp_path: Path) -> None:
    sink = LocalLiveSink(tmp_path)
    recorder = Recorder("trace-live-03", sink=sink, job_id="job-3")
    seen: list[tuple[str | None, str | None, str | None]] = []
    with recorder.span("Stage_grade", stage="GRADE") as parent:
        parent.set(ATTR_AGENT_ID, "grading-agent")
        with recorder.span(
            "Grading_sub-1", parent=parent, attributes={"student_id": "stu-9"}
        ):
            scope = get_scope()
            assert scope is not None
            seen.append((scope.stage, scope.agent_id, scope.student_id))
            scope.emit(kind=LiveEventKind.LLM_CALL, name="call_llm")

    sink.flush(5.0)
    assert seen == [("GRADE", "grading-agent", "stu-9")]
    llm_events = [
        event
        for event in read_events(tmp_path, "job-3")
        if event.kind is LiveEventKind.LLM_CALL
    ]
    assert len(llm_events) == 1
    assert llm_events[0].agent_id == "grading-agent"
    assert llm_events[0].student_id == "stu-9"
    assert llm_events[0].stage == "GRADE"
    assert llm_events[0].parent_span_id == "sp0002"


def test_recorder_without_job_id_emits_nothing(tmp_path: Path) -> None:
    sink = LocalLiveSink(tmp_path)
    recorder = Recorder("trace-live-04", sink=sink)
    with recorder.span("Stage_grade", stage="GRADE"):
        pass
    sink.flush(5.0)

    assert not (tmp_path / "live").exists()
    assert recorder.spans[0].name == "Stage_grade"


def test_recorder_keeps_typed_spans_with_null_sink() -> None:
    recorder = Recorder("trace-live-05", sink=NullLiveSink(), job_id="job-5")
    with recorder.span("Stage_grade", stage="GRADE") as span:
        span.set("gen_ai.usage.tokens", 42)

    assert recorder.spans[0].attributes["gen_ai.usage.tokens"] == 42

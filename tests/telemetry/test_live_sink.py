import json
from pathlib import Path
from typing import Any

from autocurricula.config.settings import Settings
from autocurricula.core.telemetry import (
    FirestoreLiveSink,
    LocalLiveSink,
    NullLiveSink,
    build_live_sink,
)
from autocurricula.schemas.live_events import LiveEvent, LiveEventKind, LiveEventStatus


def make_event(seq: int, *, job_id: str = "job-1", name: str = "Stage_grade") -> LiveEvent:
    return LiveEvent(
        seq=seq,
        recorded_at="2026-08-25T12:00:00+00:00",
        job_id=job_id,
        trace_id="trace-live-1",
        kind=LiveEventKind.SPAN_START,
        name=name,
        status=LiveEventStatus.RUNNING,
        stage="GRADE",
        attributes={"agent.id": "grading-agent"},
    )


class FakeNode:
    def __init__(self, writes: list[tuple[tuple[str, ...], dict[str, Any]]], path: list[str]):
        self._writes = writes
        self._path = path

    def collection(self, name: str) -> "FakeNode":
        return FakeNode(self._writes, [*self._path, name])

    def document(self, name: str) -> "FakeNode":
        return FakeNode(self._writes, [*self._path, name])

    def set(self, payload: dict[str, Any]) -> None:
        self._writes.append((tuple(self._path), payload))


class FakeFirestore:
    def __init__(self) -> None:
        self.writes: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def collection(self, name: str) -> FakeNode:
        return FakeNode(self.writes, [name])


def test_local_sink_appends_ordered_parseable_lines(tmp_path: Path) -> None:
    sink = LocalLiveSink(tmp_path)
    for seq in (1, 2, 3):
        sink.emit(make_event(seq))
    sink.flush(5.0)

    lines = (tmp_path / "live" / "job-1.jsonl").read_text(encoding="utf-8").splitlines()
    events = [LiveEvent.model_validate(json.loads(line)) for line in lines]
    assert [event.seq for event in events] == [1, 2, 3]
    assert events[0].job_id == "job-1"
    assert events[0].attributes["agent.id"] == "grading-agent"


def test_local_sink_separates_jobs(tmp_path: Path) -> None:
    sink = LocalLiveSink(tmp_path)
    sink.emit(make_event(1, job_id="job-a"))
    sink.emit(make_event(1, job_id="job-b"))
    sink.flush(5.0)

    assert (tmp_path / "live" / "job-a.jsonl").exists()
    assert (tmp_path / "live" / "job-b.jsonl").exists()


def test_firestore_sink_writes_ordered_documents() -> None:
    client = FakeFirestore()
    sink = FirestoreLiveSink("audit", client=client)
    for seq in (1, 2, 3):
        sink.emit(make_event(seq))
    sink.flush(5.0)

    assert [path[-1] for path, _ in client.writes] == ["000001", "000002", "000003"]
    assert client.writes[0][0][:4] == ("audit", "job-1", "live", "000001")
    assert client.writes[0][1]["kind"] == "span_start"


def test_firestore_sink_emit_never_raises_on_write_failure() -> None:
    class Broken(FakeFirestore):
        def collection(self, name: str) -> FakeNode:
            raise RuntimeError("firestore down")

    sink = FirestoreLiveSink("audit", client=Broken())
    sink.emit(make_event(1))
    sink.flush(5.0)


def test_build_live_sink_selects_backend(tmp_path: Path) -> None:
    disabled = Settings(
        local_mode=True, local_data_dir=tmp_path, telemetry_live_enabled=False
    )
    local = Settings(local_mode=True, local_data_dir=tmp_path)
    assert isinstance(build_live_sink(disabled), NullLiveSink)
    assert isinstance(build_live_sink(local), LocalLiveSink)

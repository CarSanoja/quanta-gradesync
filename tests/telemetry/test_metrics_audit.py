import json
from pathlib import Path

from autocurricula.core.telemetry import (
    LocalAuditLogger,
    Recorder,
    collect_metrics,
    percentile,
)
from autocurricula.schemas.telemetry import SpanStatus, TypedSpan


def _span(name: str, stage: str, ms: float, tokens: int = 0, error: bool = False):
    return TypedSpan(
        name=name,
        trace_id="trace0010",
        span_id=name,
        stage=stage,
        status=SpanStatus.ERROR if error else SpanStatus.OK,
        duration_ms=ms,
        attributes={"agent.stage": stage, "gen_ai.usage.tokens": tokens},
    )


def test_percentile_matches_manual_computation() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert percentile(values, 0.95) == 100.0
    assert percentile(values, 0.50) == 50.0
    assert percentile([], 0.95) == 0.0


def test_collect_metrics_groups_by_stage() -> None:
    spans = [
        _span("g1", "GRADE", 100.0, tokens=200),
        _span("g2", "GRADE", 300.0, tokens=100),
        _span("g3", "GRADE", 500.0, error=True),
        _span("s1", "SYNC", 40.0),
    ]
    snapshot = collect_metrics(spans)
    by_stage = {item.stage: item for item in snapshot.stages}
    assert by_stage["GRADE"].count == 3
    assert by_stage["GRADE"].errors == 1
    assert by_stage["GRADE"].total_tokens == 300
    assert by_stage["GRADE"].latency_p95_ms == 500.0
    assert snapshot.total_spans == 4
    assert snapshot.total_errors == 1
    assert snapshot.total_tokens == 300


async def test_audit_logger_is_append_only(tmp_path: Path) -> None:
    logger = LocalAuditLogger(tmp_path)
    recorder = Recorder(trace_id="trace0011")
    with recorder.span("Stage_fetch", stage="FETCH"):
        pass

    await logger.append("job-a", "trace0011", recorder.spans, {"stage": "fetch"})
    await logger.append("job-a", "trace0011", recorder.spans, {"stage": "completed"})

    lines = (tmp_path / "audit" / "job-a.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["summary"] == {"stage": "fetch"}
    assert second["summary"] == {"stage": "completed"}
    assert first["trace_id"] == "trace0011"
    assert first["spans"][0]["stage"] == "FETCH"

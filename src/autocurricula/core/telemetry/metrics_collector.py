import math

from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.telemetry import (
    ATTR_AGENT_STAGE,
    ATTR_GEN_AI_USAGE_TOKENS,
    SpanStatus,
    TypedSpan,
)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = math.ceil(fraction * len(ordered))
    index = max(0, min(len(ordered) - 1, rank - 1))
    return ordered[index]


class StageStats(StrictBaseModel):
    stage: str
    count: int
    errors: int
    latency_p95_ms: float
    total_tokens: int


class MetricsSnapshot(StrictBaseModel):
    stages: list[StageStats]
    total_spans: int
    total_errors: int
    total_tokens: int


def collect_metrics(spans: list[TypedSpan]) -> MetricsSnapshot:
    grouped: dict[str, list[TypedSpan]] = {}
    for span in spans:
        stage = _stage_of(span)
        grouped.setdefault(stage, []).append(span)
    stats = [
        StageStats(
            stage=stage,
            count=len(group),
            errors=sum(1 for span in group if span.status == SpanStatus.ERROR),
            latency_p95_ms=round(
                percentile([span.duration_ms for span in group], 0.95), 3
            ),
            total_tokens=sum(
                _tokens(span) for span in group
            ),
        )
        for stage, group in sorted(grouped.items())
    ]
    return MetricsSnapshot(
        stages=stats,
        total_spans=len(spans),
        total_errors=sum(item.errors for item in stats),
        total_tokens=sum(item.total_tokens for item in stats),
    )


def _stage_of(span: TypedSpan) -> str:
    value = span.attributes.get(ATTR_AGENT_STAGE)
    if isinstance(value, str):
        return value
    return span.stage or "unattributed"


def _tokens(span: TypedSpan) -> int:
    value = span.attributes.get(ATTR_GEN_AI_USAGE_TOKENS)
    if isinstance(value, int):
        return value
    return 0

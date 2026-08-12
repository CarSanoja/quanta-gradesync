from typing import Sequence

from autocurricula.core.evolution.calibration_store import CalibrationSample
from autocurricula.schemas.metrics import CalibrationMetrics

DEFAULT_FAILING_SAMPLE_LIMIT = 5


def sample_failure_score(sample: CalibrationSample, metrics: CalibrationMetrics) -> float:
    per_criterion = metrics.per_criterion
    return sum(per_criterion.get(criterion_id, 0.0) for criterion_id in sample.criterion_ids)


def select_failing_samples(
    samples: Sequence[CalibrationSample],
    metrics: CalibrationMetrics,
    limit: int = DEFAULT_FAILING_SAMPLE_LIMIT,
) -> list[CalibrationSample]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    ranked = sorted(
        samples,
        key=lambda sample: (-sample_failure_score(sample, metrics), sample.submission_id),
    )
    return list(ranked[:limit])

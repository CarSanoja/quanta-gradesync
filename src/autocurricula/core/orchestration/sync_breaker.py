import logging

from autocurricula.core.harness import BatchAnomalyBreaker, BreakerTripped
from autocurricula.schemas.sis_sync import SISGradeRecord

logger = logging.getLogger(__name__)

BREAKER_REASON_PREFIX = "batch anomaly breaker"


def failure_trip_reason(failed: int, total: int, ratio: float, threshold: float) -> str:
    return (
        f"{failed}/{total} exams could not be graded (failure ratio {ratio:.3f} "
        f"exceeds threshold {threshold:.3f}); automatic sync suspended for the batch"
    )


def breaker_trip_reason(
    breaker: BatchAnomalyBreaker, total: int, quarantined: int, failed: int
) -> str | None:
    try:
        breaker.evaluate(total, min(quarantined, total))
    except BreakerTripped as tripped:
        return str(tripped)
    stats = breaker.ratio(total, min(failed, total))
    if stats.ratio > breaker.threshold:
        return failure_trip_reason(failed, total, stats.ratio, breaker.threshold)
    return None


def apply_breaker(
    breaker: BatchAnomalyBreaker,
    total: int,
    quarantined: list[SISGradeRecord],
    auto: list[SISGradeRecord],
    reasons: dict[str, list[str]],
    failed: int = 0,
) -> tuple[list[SISGradeRecord], list[SISGradeRecord]]:
    trip = breaker_trip_reason(breaker, total, len(quarantined), failed)
    if trip is None:
        return quarantined, auto
    moved = list(auto)
    for record in moved:
        reasons.setdefault(record.student_id, []).insert(
            0, f"{BREAKER_REASON_PREFIX}: {trip}"
        )
    logger.warning("%s: %s", BREAKER_REASON_PREFIX, trip)
    return quarantined + moved, []

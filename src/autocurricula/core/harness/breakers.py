from autocurricula.schemas.common import StrictBaseModel


DEFAULT_BATCH_ANOMALY_THRESHOLD = 0.15


class BreakerTripped(Exception):
    def __init__(self, ratio: float, threshold: float) -> None:
        super().__init__(
            f"batch anomaly breaker tripped: quarantine ratio {ratio:.3f} "
            f"exceeds threshold {threshold:.3f}; automatic sync suspended for the batch"
        )
        self.ratio = ratio
        self.threshold = threshold


class QuarantineRatio(StrictBaseModel):
    total: int
    quarantined: int
    ratio: float


class BatchAnomalyBreaker:
    def __init__(self, threshold: float = DEFAULT_BATCH_ANOMALY_THRESHOLD) -> None:
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be within (0, 1]")
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def ratio(self, total: int, quarantined: int) -> QuarantineRatio:
        if total < 0 or quarantined < 0 or quarantined > total:
            raise ValueError("counts must satisfy 0 <= quarantined <= total")
        value = (quarantined / total) if total > 0 else 0.0
        return QuarantineRatio(total=total, quarantined=quarantined, ratio=value)

    def evaluate(self, total: int, quarantined: int) -> QuarantineRatio:
        stats = self.ratio(total, quarantined)
        if stats.ratio > self._threshold:
            raise BreakerTripped(stats.ratio, self._threshold)
        return stats

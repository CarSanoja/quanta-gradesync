from dataclasses import dataclass

from autocurricula.schemas.grading import GradingResult

DEFAULT_CONFIDENCE_THRESHOLD = 0.85


@dataclass(frozen=True)
class GateVerdict:
    quarantined: bool
    reasons: tuple[str, ...]


class ConfidenceGate:
    def __init__(self, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> None:
        if not 0.0 < threshold <= 1.0:
            raise ValueError("confidence threshold must be in (0, 1]")
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def evaluate(
        self, result: GradingResult, *, confidence_factor: float = 1.0
    ) -> GateVerdict:
        if not 0.0 < confidence_factor <= 1.0:
            raise ValueError("confidence factor must be in (0, 1]")
        reasons: list[str] = []
        for criterion in result.criterion_scores:
            effective = criterion.confidence * confidence_factor
            if effective < self._threshold:
                reasons.append(self._confidence_reason(criterion, effective, confidence_factor))
            if not criterion.evidence:
                reasons.append(f"{criterion.criterion_id} has no cited evidence")
        return GateVerdict(quarantined=bool(reasons), reasons=tuple(dict.fromkeys(reasons)))

    def _confidence_reason(self, criterion, effective: float, factor: float) -> str:
        if factor >= 1.0:
            return (
                f"{criterion.criterion_id} confidence {criterion.confidence:.3f} "
                f"below threshold {self._threshold:.2f}"
            )
        return (
            f"{criterion.criterion_id} confidence {criterion.confidence:.3f} x "
            f"legibility factor {factor:.2f} = effective {effective:.3f} "
            f"below threshold {self._threshold:.2f}"
        )

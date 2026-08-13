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

    def evaluate(self, result: GradingResult) -> GateVerdict:
        reasons: list[str] = []
        for criterion in result.criterion_scores:
            if criterion.confidence < self._threshold:
                reasons.append(
                    f"{criterion.criterion_id} confidence {criterion.confidence:.3f} "
                    f"below threshold {self._threshold:.2f}"
                )
            if not criterion.evidence:
                reasons.append(f"{criterion.criterion_id} has no cited evidence")
        return GateVerdict(quarantined=bool(reasons), reasons=tuple(dict.fromkeys(reasons)))

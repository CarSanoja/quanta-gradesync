import pytest

from autocurricula.core.review import DEFAULT_CONFIDENCE_THRESHOLD, ConfidenceGate
from autocurricula.schemas.grading import CriterionScore, EvidenceSpan, GradingResult


def make_result(confidences: list[float], with_evidence: bool = True) -> GradingResult:
    evidence = (
        [EvidenceSpan(page=1, quote="student answer", rationale="matches criterion")]
        if with_evidence
        else []
    )
    scores = [
        CriterionScore(
            criterion_id=f"crit-{index}",
            score=3.0,
            comment="assessed",
            evidence=list(evidence),
            confidence=confidence,
        )
        for index, confidence in enumerate(confidences)
    ]
    return GradingResult(
        submission_id="sub-001",
        criterion_scores=scores,
        total_score=3.0 * len(confidences),
        percentage=75.0,
        feedback="assessed against rubric",
    )


def test_default_threshold_is_85_percent() -> None:
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.85


def test_confidence_at_threshold_passes() -> None:
    verdict = ConfidenceGate().evaluate(make_result([0.85]))
    assert verdict.quarantined is False
    assert verdict.reasons == ()


def test_confidence_below_threshold_quarantines() -> None:
    verdict = ConfidenceGate().evaluate(make_result([0.84]))
    assert verdict.quarantined is True
    assert any("confidence" in reason for reason in verdict.reasons)


def test_missing_evidence_quarantines() -> None:
    verdict = ConfidenceGate().evaluate(make_result([0.99], with_evidence=False))
    assert verdict.quarantined is True
    assert any("no cited evidence" in reason for reason in verdict.reasons)


def test_weakest_criterion_decides() -> None:
    verdict = ConfidenceGate().evaluate(make_result([0.99, 0.70]))
    assert verdict.quarantined is True
    assert len(verdict.reasons) == 1


def test_custom_threshold_is_respected() -> None:
    gate = ConfidenceGate(threshold=0.5)
    assert gate.evaluate(make_result([0.6])).quarantined is False
    assert gate.evaluate(make_result([0.4])).quarantined is True


def test_invalid_threshold_is_rejected() -> None:
    with pytest.raises(ValueError):
        ConfidenceGate(threshold=0.0)
    with pytest.raises(ValueError):
        ConfidenceGate(threshold=1.5)

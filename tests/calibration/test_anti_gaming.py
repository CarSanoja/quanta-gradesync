import pytest

from autocurricula.core.evolution.anti_gaming_validator import AntiGamingValidator
from autocurricula.schemas.metrics import CalibrationMetrics, OptimizerReport

pytestmark = pytest.mark.calibration

SAMPLES_IN_FIXTURES = 4


def _metrics(mae: float, kappa: float, bias: float = 0.0) -> CalibrationMetrics:
    return CalibrationMetrics(mae=mae, quadratic_weighted_kappa=kappa, bias=bias)


def _report(previous: CalibrationMetrics, candidate: CalibrationMetrics) -> OptimizerReport:
    return OptimizerReport(
        iteration=1,
        previous_metrics=previous,
        candidate_metrics=candidate,
        delta_mae=round(candidate.mae - previous.mae, 6),
        accepted=True,
        rejected_reasons=[],
    )


def test_variance_collapse_proposal_rejected(calibration_set):
    validator = AntiGamingValidator(calibration_set)
    report = _report(_metrics(1.2, 0.4), _metrics(0.8, 0.4))
    collapsed = [[2.0, 2.0, 1.0] for _ in range(SAMPLES_IN_FIXTURES)]

    validated = validator.validate(report, collapsed)

    assert validated.accepted is False
    reasons = validated.rejected_reasons
    assert any(reason.startswith("variance_collapse") for reason in reasons)
    assert "constant_output_detected" not in " ".join(reasons)
    assert report.accepted is True


def test_constant_output_proposal_rejected(calibration_set):
    validator = AntiGamingValidator(calibration_set)
    report = _report(_metrics(1.2, 0.4), _metrics(0.8, 0.4))
    constant = [[2.0, 2.0, 2.0] for _ in range(SAMPLES_IN_FIXTURES)]

    validated = validator.validate(report, constant)

    assert validated.accepted is False
    constants = [
        reason
        for reason in validated.rejected_reasons
        if reason.startswith("constant_output_detected")
    ]
    assert any("every candidate score is identical" in reason for reason in constants)
    assert any("zero within-sample variance" in reason for reason in constants)


def test_honest_improvement_accepted(calibration_set):
    validator = AntiGamingValidator(calibration_set)
    report = _report(_metrics(0.8, 0.35), _metrics(0.4, 0.72))
    honest = calibration_set.ground_truth_distributions()

    validated = validator.validate(report, honest)

    assert validated.accepted is True
    assert validated.rejected_reasons == []
    assert validated == report


def test_missing_distributions_flagged_as_constant_output(calibration_set):
    validator = AntiGamingValidator(calibration_set)
    report = _report(_metrics(1.0, 0.2), _metrics(1.1, 0.2))

    validated = validator.validate(report, [])

    assert validated.accepted is False
    assert len(validated.rejected_reasons) == 1
    assert "produced no score distributions" in validated.rejected_reasons[0]


def test_partial_evaluation_with_improved_mae_flagged(calibration_set):
    validator = AntiGamingValidator(calibration_set)
    report = _report(_metrics(1.0, 0.2), _metrics(0.5, 0.6))
    partial = calibration_set.ground_truth_distributions()[:2]

    validated = validator.validate(report, partial)

    assert validated.accepted is False
    assert any(
        reason.startswith("ground_truth_contact") for reason in validated.rejected_reasons
    )


def test_constructor_rejects_out_of_range_thresholds(calibration_set):
    with pytest.raises(ValueError, match="variance_collapse_ratio"):
        AntiGamingValidator(calibration_set, variance_collapse_ratio=1.0)
    with pytest.raises(ValueError, match="constant_sample_fraction"):
        AntiGamingValidator(calibration_set, constant_sample_fraction=0.0)
    with pytest.raises(ValueError, match="constant_tolerance"):
        AntiGamingValidator(calibration_set, constant_tolerance=-0.1)

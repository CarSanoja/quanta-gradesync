import pytest
from pydantic import ValidationError

from autocurricula.core.evolution.calibration_store import (
    CalibrationSample,
    CalibrationSet,
    compute_calibration_metrics,
)

pytestmark = pytest.mark.calibration


def test_metrics_match_hand_computed_values(make_calibration_sample, make_grading_result):
    ceilings = {"A": 4.0, "B": 2.0}
    sample = make_calibration_sample("sub_001", {"A": 3.0, "B": 1.0}, ceilings)
    result = make_grading_result("sub_001", {"A": 2.0, "B": 1.5}, ceilings)

    metrics = compute_calibration_metrics([result], [sample])

    assert metrics.mae == pytest.approx(0.75)
    assert metrics.bias == pytest.approx(-0.25)
    assert metrics.quadratic_weighted_kappa == pytest.approx(-1.0)
    assert metrics.per_criterion == {
        "A": pytest.approx(1.0),
        "B": pytest.approx(0.5),
    }


def test_perfect_agreement_yields_zero_error_and_unit_kappa(
    make_calibration_sample, make_grading_result
):
    ceilings = {"A": 4.0, "B": 2.0}
    expected_scores = {"A": 3.0, "B": 1.0}
    sample = make_calibration_sample("sub_001", expected_scores, ceilings)
    result = make_grading_result("sub_001", expected_scores, ceilings)

    metrics = compute_calibration_metrics([result], [sample])

    assert metrics.mae == pytest.approx(0.0)
    assert metrics.bias == pytest.approx(0.0)
    assert metrics.quadratic_weighted_kappa == pytest.approx(1.0)
    assert metrics.per_criterion == {"A": pytest.approx(0.0), "B": pytest.approx(0.0)}


def test_anti_correlated_predictions_yield_negative_kappa(
    make_calibration_sample, make_grading_result
):
    ceilings = {"A": 4.0, "B": 4.0}
    sample = make_calibration_sample("sub_001", {"A": 0.0, "B": 4.0}, ceilings)
    result = make_grading_result("sub_001", {"A": 4.0, "B": 0.0}, ceilings)

    metrics = compute_calibration_metrics([result], [sample])

    assert metrics.mae == pytest.approx(4.0)
    assert metrics.bias == pytest.approx(0.0)
    assert metrics.quadratic_weighted_kappa == pytest.approx(-1.0)


def test_unmatched_submissions_raise_value_error(
    make_calibration_sample, make_grading_result
):
    sample = make_calibration_sample("sub_001", {"A": 3.0}, {"A": 4.0})
    result = make_grading_result("sub_999", {"A": 1.0}, {"A": 4.0})

    with pytest.raises(ValueError, match="no overlapping submissions"):
        compute_calibration_metrics([result], [sample])


def test_partial_overlap_scores_only_matched_samples(
    make_calibration_sample, make_grading_result
):
    ceilings = {"A": 4.0}
    first = make_calibration_sample("sub_001", {"A": 3.0}, ceilings)
    second = make_calibration_sample("sub_002", {"A": 1.0}, ceilings)
    result = make_grading_result("sub_001", {"A": 2.0}, ceilings)

    metrics = compute_calibration_metrics([result], [first, second])

    assert metrics.mae == pytest.approx(1.0)
    assert metrics.bias == pytest.approx(-1.0)
    assert metrics.quadratic_weighted_kappa == pytest.approx(0.0)
    assert metrics.per_criterion == {"A": pytest.approx(1.0)}


def test_fixture_directory_loads_handwritten_calibration_set(
    calibration_dir, calibration_set
):
    totals = {
        sample.submission_id: sum(score.score for score in sample.expected)
        for sample in calibration_set
    }

    assert calibration_set.submission_ids == ["sub_001", "sub_002", "sub_003", "sub_004"]
    assert totals == {"sub_001": 9.5, "sub_002": 5.0, "sub_003": 1.5, "sub_004": 7.5}
    assert len(list(calibration_dir.glob("*.json"))) == 4
    assert CalibrationSet.from_directory() == calibration_set


def test_calibration_set_rejects_duplicate_submission_ids(make_calibration_sample):
    first = make_calibration_sample("sub_001", {"A": 1.0}, {"A": 4.0})
    duplicate = make_calibration_sample("sub_001", {"A": 2.0}, {"A": 4.0})

    with pytest.raises(ValueError, match="unique"):
        CalibrationSet([first, duplicate])


def test_calibration_sample_rejects_misaligned_metadata():
    payload = {
        "submission_id": "sub_001",
        "submission_summary": "Single page scanned exam.",
        "criterion_ids": ["A", "B", "C"],
        "max_scores": [4.0, 4.0],
        "expected": [
            {
                "criterion_id": "A",
                "score": 3.0,
                "comment": "Ground truth for A.",
                "confidence": 0.9,
            }
        ],
    }

    with pytest.raises(ValidationError, match="equal length"):
        CalibrationSample.model_validate(payload)


def test_calibration_sample_rejects_unknown_criterion_in_expected():
    payload = {
        "submission_id": "sub_001",
        "submission_summary": "Single page scanned exam.",
        "criterion_ids": ["A", "B"],
        "max_scores": [4.0, 4.0],
        "expected": [
            {
                "criterion_id": "Z",
                "score": 3.0,
                "comment": "Ground truth for unknown criterion.",
                "confidence": 0.9,
            }
        ],
    }

    with pytest.raises(ValidationError, match="unknown criteria"):
        CalibrationSample.model_validate(payload)

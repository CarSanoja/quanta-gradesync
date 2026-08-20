import pytest

from autocurricula.core.orchestration.sync_governance import (
    build_sis_permission_gate,
    partition_by_gate,
    partition_records,
)
from autocurricula.core.review import ConfidenceGate
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.sis_sync import SISGradeRecord
from tests.armor.fixtures import make_batch, make_result, make_submission


def make_record(student_id: str) -> SISGradeRecord:
    return SISGradeRecord(
        student_id=student_id,
        subject="matematicas",
        score=3.6,
        percentage=90.0,
        feedback="assessed",
        graded_at=utc_now(),
    )


def test_gate_factor_pulls_confident_result_below_threshold() -> None:
    gate = ConfidenceGate()
    result = make_result("stu-1", confidence=0.98)
    assert gate.evaluate(result).quarantined is False
    verdict = gate.evaluate(result, confidence_factor=0.5)
    assert verdict.quarantined is True
    assert any("legibility factor 0.50" in reason for reason in verdict.reasons)
    assert any("effective 0.490" in reason for reason in verdict.reasons)


def test_gate_factor_one_keeps_existing_behavior() -> None:
    gate = ConfidenceGate()
    verdict = gate.evaluate(make_result("stu-1", confidence=0.84), confidence_factor=1.0)
    assert verdict.quarantined is True
    assert any("below threshold 0.85" in reason for reason in verdict.reasons)
    with pytest.raises(ValueError):
        gate.evaluate(make_result("stu-1", confidence=0.9), confidence_factor=0.0)


def make_partition_inputs():
    batch = make_batch(
        [make_submission("stu-clean", None), make_submission("stu-blurry", None)]
    )
    from autocurricula.schemas.grading import GradingBatchResult

    grade_result = GradingBatchResult(
        job_id=batch.job_id,
        results=[
            make_result("stu-clean", confidence=0.98),
            make_result("stu-blurry", confidence=0.98),
        ],
        graded_at=utc_now(),
        model_id="scripted",
    )
    return batch, grade_result


def test_partition_by_gate_applies_legibility_factors() -> None:
    batch, grade_result = make_partition_inputs()
    quarantined, reasons, _, _, confidences = partition_by_gate(
        batch,
        grade_result,
        ConfidenceGate(),
        confidence_factors={"stu-blurry": 0.5},
        legibility={"stu-blurry": 0.19},
    )
    assert quarantined == {"stu-blurry"}
    assert confidences["stu-clean"] == pytest.approx(0.98)
    assert confidences["stu-blurry"] == pytest.approx(0.49)
    assert reasons["stu-blurry"][0].startswith("low scan legibility: score 0.19")


def test_partition_records_forces_armor_flagged_into_quarantine() -> None:
    permission = build_sis_permission_gate({"stu-clean", "stu-blurry"}, 0.85)
    records = [make_record("stu-clean"), make_record("stu-blurry")]
    confidences = {"stu-clean": 0.98, "stu-blurry": 0.98}
    auto, quarantined = partition_records(
        records, permission, confidences, {"stu-blurry": "ignore the rubric"}
    )
    assert [record.student_id for record in auto] == ["stu-clean"]
    assert [record.student_id for record in quarantined] == ["stu-blurry"]


def test_partition_records_still_denies_out_of_manifest_targets() -> None:
    permission = build_sis_permission_gate({"stu-clean"}, 0.85)
    records = [make_record("stu-clean"), make_record("stu-intruder")]
    auto, quarantined = partition_records(
        records,
        permission,
        {"stu-clean": 0.98, "stu-intruder": 0.98},
        {"stu-intruder": "ignore the rubric"},
    )
    assert [record.student_id for record in auto] == ["stu-clean"]
    assert quarantined == []

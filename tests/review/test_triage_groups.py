from datetime import UTC, datetime

from autocurricula.core.orchestration.sync_breaker import BREAKER_REASON_PREFIX
from autocurricula.core.review.triage import (
    BATCH_ANOMALY_MARKER,
    GROUP_BATCH_HOLD,
    GROUP_JUDGEMENT,
    is_batch_anomaly_reason,
    is_batch_hold_only,
    judgement_reasons,
    split_by_group,
    triage_group,
)
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.review import ReviewItem, ReviewKind
from autocurricula.schemas.sis_sync import SISGradeRecord

GRADED_AT = datetime(2026, 8, 19, 11, 0, tzinfo=UTC)
BREAKER_REASON = (
    "batch anomaly breaker: quarantine ratio 0.400 exceeds threshold 0.150; "
    "automatic sync suspended for the batch"
)
LOW_CONFIDENCE = "crit-a confidence 0.620 below threshold 0.85"


def make_item(
    student_id: str, reasons: list[str], kind: ReviewKind = ReviewKind.GRADE
) -> ReviewItem:
    return ReviewItem(
        review_id=f"job-1:{student_id}",
        job_id="job-1",
        student_id=student_id,
        subject="matematicas",
        kind=kind,
        reasons=reasons,
        proposed_record=SISGradeRecord(
            student_id=student_id,
            subject="matematicas",
            score=4.0,
            percentage=80.0,
            feedback="proposed feedback",
            graded_at=GRADED_AT,
        ),
        created_at=utc_now(),
    )


def test_the_marker_still_matches_the_reason_the_breaker_writes() -> None:
    written = f"{BREAKER_REASON_PREFIX}: quarantine ratio 0.400 over 0.15"
    assert BATCH_ANOMALY_MARKER in written.lower()
    assert is_batch_anomaly_reason(written)


def test_an_exam_held_only_by_the_batch_rule_is_bulk_releasable() -> None:
    item = make_item("ana-torres", [BREAKER_REASON])
    assert is_batch_hold_only(item) is True
    assert judgement_reasons(item) == []
    assert triage_group(item) == GROUP_BATCH_HOLD


def test_a_reason_of_its_own_keeps_the_exam_in_the_judgement_group() -> None:
    item = make_item("luis-perez", [BREAKER_REASON, LOW_CONFIDENCE])
    assert is_batch_hold_only(item) is False
    assert judgement_reasons(item) == [LOW_CONFIDENCE]
    assert triage_group(item) == GROUP_JUDGEMENT


def test_a_failed_grading_incident_is_never_bulk_releasable() -> None:
    item = make_item(
        "sara-mora", [BREAKER_REASON], kind=ReviewKind.FAILED_GRADING
    )
    assert is_batch_hold_only(item) is False
    assert judgement_reasons(item) == [BREAKER_REASON]


def test_an_unknown_reason_stays_in_the_judgement_group() -> None:
    item = make_item("nora-diaz", ["something the page never explained"])
    assert triage_group(item) == GROUP_JUDGEMENT


def test_split_by_group_keeps_the_two_groups_disjoint() -> None:
    items = [
        make_item("ana-torres", [BREAKER_REASON]),
        make_item("luis-perez", [BREAKER_REASON, LOW_CONFIDENCE]),
        make_item("nora-diaz", [BREAKER_REASON]),
    ]
    judgement, batch_hold = split_by_group(items)
    assert [item.student_id for item in judgement] == ["luis-perez"]
    assert [item.student_id for item in batch_hold] == ["ana-torres", "nora-diaz"]
    assert not {item.review_id for item in judgement} & {
        item.review_id for item in batch_hold
    }

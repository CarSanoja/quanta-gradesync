import json

import pytest
from pydantic import ValidationError

from autocurricula.schemas.feedback import (
    EvidenceSpan,
    FeedbackBand,
    FeedbackPoint,
    StudentFeedback,
)
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.review import ReviewItem, build_review_id
from autocurricula.schemas.sis_sync import SISGradeRecord
from tests.feedback.fixtures import GRADED_AT, make_result, make_student_feedback


def test_a_record_graded_before_this_change_still_validates() -> None:
    legacy = {
        "submission_id": "camila-rios",
        "criterion_scores": [
            {
                "criterion_id": "factoring",
                "score": 3.0,
                "comment": "Correct factors.",
                "evidence": [],
                "confidence": 0.9,
            }
        ],
        "total_score": 3.0,
        "percentage": 75.0,
        "feedback": "Correct factoring; show the expansion check.",
    }
    result = GradingResult.model_validate(legacy)
    assert result.student_feedback is None


def test_student_feedback_round_trips_as_plain_json() -> None:
    result = make_result(student_feedback=make_student_feedback())
    payload = json.loads(result.model_dump_json())
    assert payload["student_feedback"]["band"] == "upper_secondary"
    assert payload["student_feedback"]["strengths"][0]["evidence"]["page"] == 1
    assert GradingResult.model_validate(payload) == result


def test_the_band_is_closed_to_the_four_developmental_levels() -> None:
    with pytest.raises(ValidationError):
        StudentFeedback(
            band="teenager",
            headline="Nice.",
            next_step="Try again.",
        )


def test_a_feedback_point_may_carry_no_evidence_span() -> None:
    point = FeedbackPoint(text="Next time, label the units.")
    assert point.evidence is None
    quoted = FeedbackPoint(
        text="You wrote the ratio correctly.",
        evidence=EvidenceSpan(page=1, quote="84 / (4/3)", rationale="Ratio on the page."),
    )
    assert quoted.evidence is not None


def test_headline_and_next_step_are_never_blank() -> None:
    with pytest.raises(ValidationError):
        StudentFeedback(band=FeedbackBand.EARLY_PRIMARY, headline="", next_step="Try.")
    with pytest.raises(ValidationError):
        StudentFeedback(band=FeedbackBand.EARLY_PRIMARY, headline="Good try.", next_step="")


def test_the_sis_record_and_the_review_item_carry_the_field() -> None:
    record = SISGradeRecord(
        student_id="camila-rios",
        subject="Matematicas",
        score=3.0,
        percentage=75.0,
        feedback="Correct factoring; show the expansion check.",
        student_feedback=make_student_feedback(),
        graded_at=GRADED_AT,
    )
    item = ReviewItem(
        review_id=build_review_id("job-feedback-1", "camila-rios"),
        job_id="job-feedback-1",
        student_id="camila-rios",
        subject="Matematicas",
        reasons=["quarantined by confidence gate"],
        proposed_record=record,
        created_at=GRADED_AT,
    )
    restored = ReviewItem.model_validate_json(item.model_dump_json())
    assert restored.proposed_record.student_feedback is not None
    assert restored.proposed_record.student_feedback.band is FeedbackBand.UPPER_SECONDARY
    assert restored.proposed_record.feedback == record.feedback


def test_a_sis_record_written_before_this_change_still_validates() -> None:
    record = SISGradeRecord.model_validate(
        {
            "student_id": "camila-rios",
            "subject": "Matematicas",
            "score": 3.0,
            "percentage": 75.0,
            "feedback": "Correct factoring.",
            "graded_at": GRADED_AT.isoformat(),
        }
    )
    assert record.student_feedback is None

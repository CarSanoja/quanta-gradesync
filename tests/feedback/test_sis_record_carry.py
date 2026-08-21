from autocurricula.core.orchestration.sis_records import (
    build_sis_write_request,
    first_student_feedback,
)
from autocurricula.schemas.feedback import FeedbackBand
from tests.feedback.fixtures import (
    make_audit,
    make_batch,
    make_batch_result,
    make_result,
    make_student_feedback,
)


def test_the_sis_record_carries_the_student_feedback_of_the_graded_submission() -> None:
    feedback = make_student_feedback(FeedbackBand.UPPER_SECONDARY)
    batch = make_batch()
    request = build_sis_write_request(
        batch,
        make_batch_result(make_result(student_feedback=feedback)),
        [make_audit()],
    )
    record = request.records[0]
    assert record.student_feedback == feedback
    assert record.feedback == "Correct factoring; next step is showing the expansion check."


def test_a_record_graded_without_student_feedback_still_ships_the_free_text() -> None:
    batch = make_batch()
    request = build_sis_write_request(
        batch, make_batch_result(make_result()), [make_audit()]
    )
    record = request.records[0]
    assert record.student_feedback is None
    assert record.feedback


def test_the_first_grounded_feedback_wins_when_a_student_has_several_pages() -> None:
    feedback = make_student_feedback(FeedbackBand.LOWER_SECONDARY)
    results = [
        make_result("page-a"),
        make_result("page-b", student_feedback=feedback),
    ]
    assert first_student_feedback(results) == feedback
    assert first_student_feedback([make_result("page-a")]) is None
    assert first_student_feedback([]) is None

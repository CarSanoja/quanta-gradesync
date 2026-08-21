from pathlib import Path

from autocurricula.api.teacher_views import BATCH_HELD, COULD_NOT_GRADE, translate_reasons
from autocurricula.core.harness import BatchAnomalyBreaker
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.goal_checks import (
    CHECK_FAILURES_RESOLVED,
    CHECK_SUBMISSIONS_GRADED,
)
from autocurricula.core.orchestration.job_state import JobStage
from autocurricula.schemas.review import ReviewKind, ReviewStatus
from tests.orchestration.incident_fixtures import (
    CrashingEvaluator,
    build_incident_runner,
    roster,
    stage_roster,
    synced_records,
    verification_report,
)
from tests.review.flow_stack import make_event, make_settings

JOB_ID = "job-crash-16"
CLEAN_STUDENT = "stu-007"


def check_named(report, name: str):
    return next(check for check in report.checks if check.name == name)


async def test_crashed_exams_stay_visible_and_widen_the_breaker(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    students = roster(16)
    stage_roster(settings, JOB_ID, students)
    runner, review_store = build_incident_runner(
        settings,
        memory_manager,
        CrashingEvaluator(healthy=(CLEAN_STUDENT,)),
        breaker=BatchAnomalyBreaker(threshold=0.15),
    )

    record = await runner.process(make_event(JOB_ID))

    assert record.stage == JobStage.COMPLETED
    pending = await review_store.list_pending()
    failures = [item for item in pending if item.kind == ReviewKind.FAILED_GRADING]
    assert len(failures) == 15
    assert {item.student_id for item in failures} == set(students) - {CLEAN_STUDENT}
    assert all(
        translate_reasons(item.reasons) == [COULD_NOT_GRADE] for item in failures
    )
    assert synced_records(settings) == []
    held = [item for item in pending if item.kind == ReviewKind.GRADE]
    assert [item.student_id for item in held] == [CLEAN_STUDENT]
    assert translate_reasons(held[0].reasons)[0] == BATCH_HELD
    assert "15/16 exams could not be graded" in held[0].reasons[0]

    report = await verification_report(settings, JOB_ID)
    assert report.passed is False
    assert len(report.failed_submission_ids) == 15
    assert check_named(report, CHECK_FAILURES_RESOLVED).passed is False
    assert check_named(report, CHECK_SUBMISSIONS_GRADED).detail == "1/16 graded"


async def test_retry_resolves_the_failure_item_without_duplicating(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    students = roster(16)
    stage_roster(settings, JOB_ID, students)
    runner, review_store = build_incident_runner(
        settings,
        memory_manager,
        CrashingEvaluator(healthy=(CLEAN_STUDENT,)),
        breaker=BatchAnomalyBreaker(threshold=0.15),
    )
    await runner.process(make_event(JOB_ID))
    recovered = "stu-003"
    first_pass = await review_store.get(f"{JOB_ID}:{recovered}")
    assert first_pass is not None
    assert first_pass.status == ReviewStatus.PENDING

    still_broken = "stu-016"
    retry_runner, _ = build_incident_runner(
        settings,
        memory_manager,
        CrashingEvaluator(
            healthy=tuple(student for student in students if student != still_broken)
        ),
        review_store=review_store,
        checkpoint_dir=tmp_path / "redelivery",
        breaker=BatchAnomalyBreaker(threshold=0.15),
    )
    await retry_runner.process(make_event(JOB_ID))

    resolved = await review_store.get(f"{JOB_ID}:{recovered}")
    assert resolved is not None
    assert resolved.status == ReviewStatus.RESOLVED
    assert resolved.decided_at is not None
    pending = await review_store.list_pending()
    assert [
        item.student_id for item in pending if item.kind == ReviewKind.FAILED_GRADING
    ] == [still_broken]
    stored = sorted((settings.local_data_dir / "reviews").glob("*.json"))
    assert len(stored) == 16
    assert recovered in {record["student_id"] for record in synced_records(settings)}

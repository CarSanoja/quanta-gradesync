from pathlib import Path

from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.job_state import JobStage
from autocurricula.schemas.review import ReviewStatus
from tests.orchestration.verifier_fixtures import (
    ConfidenceMapEvaluator,
    FixedReworkEvaluator,
    StatefulReworkEvaluator,
    build_runner,
    verification_report,
)
from tests.review.flow_stack import STUDENTS, make_event, make_settings, stage_batch


def high_confidences(overrides: dict[str, float] | None = None) -> dict[str, float]:
    confidences = {student: 0.95 for student in STUDENTS}
    confidences.update(overrides or {})
    return confidences


async def test_clear_job_passes_all_goal_checks(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    runner, review_store = build_runner(
        settings, memory_manager, ConfidenceMapEvaluator(high_confidences())
    )
    stage_batch(settings, "job-verify-clear")
    record = await runner.process(make_event("job-verify-clear"))
    assert record.stage == JobStage.COMPLETED
    report = await verification_report(settings, "job-verify-clear")
    assert report.passed is True
    assert report.rework_attempts == []
    assert report.unresolved_submission_ids == []
    assert report.pending_human_approval == []
    assert all(check.passed for check in report.checks)


async def test_rework_recovers_quarantine_but_human_approval_stands(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    primary = ConfidenceMapEvaluator(high_confidences({"stu-002": 0.6}))
    rework = FixedReworkEvaluator(confidence=0.95, students=STUDENTS)
    runner, review_store = build_runner(settings, memory_manager, primary, rework=rework)
    stage_batch(settings, "job-verify-recover")
    record = await runner.process(make_event("job-verify-recover"))
    assert record.stage == JobStage.COMPLETED
    report = await verification_report(settings, "job-verify-recover")
    assert report.passed is True
    assert report.pending_human_approval == ["stu-002"]
    assert report.unresolved_submission_ids == []
    assert len(report.rework_attempts) == 1
    assert report.rework_attempts[0].outcomes == {"stu-002": "recovered_pending_approval"}
    item = await review_store.get("job-verify-recover:stu-002")
    assert item is not None
    assert item.status == ReviewStatus.PENDING
    assert item.rework_notes
    assert item.proposed_record.percentage == 90.0


async def test_rework_failure_leaves_submission_unresolved(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    primary = ConfidenceMapEvaluator(high_confidences({"stu-002": 0.6}))
    rework = FixedReworkEvaluator(confidence=0.6, students=STUDENTS)
    runner, review_store = build_runner(settings, memory_manager, primary, rework=rework)
    stage_batch(settings, "job-verify-fail")
    record = await runner.process(make_event("job-verify-fail"))
    assert record.stage == JobStage.COMPLETED
    report = await verification_report(settings, "job-verify-fail")
    assert report.passed is False
    assert report.unresolved_submission_ids == ["stu-002"]
    assert report.pending_human_approval == []
    item = await review_store.get("job-verify-fail:stu-002")
    assert item is not None
    assert item.rework_notes == []


async def test_without_rework_evaluator_quarantine_is_unresolved(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    primary = ConfidenceMapEvaluator(high_confidences({"stu-002": 0.6}))
    runner, review_store = build_runner(settings, memory_manager, primary)
    stage_batch(settings, "job-verify-norework")
    await runner.process(make_event("job-verify-norework"))
    report = await verification_report(settings, "job-verify-norework")
    assert report.passed is False
    assert report.unresolved_submission_ids == ["stu-002"]
    assert report.rework_attempts == []


async def test_iteration_budget_bounds_the_loop(tmp_path: Path) -> None:
    confidences = high_confidences({"stu-001": 0.6, "stu-002": 0.6})

    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    runner, _ = build_runner(
        settings,
        memory_manager,
        ConfidenceMapEvaluator(confidences),
        rework=StatefulReworkEvaluator(low_calls=1),
        verify_max_iterations=1,
    )
    stage_batch(settings, "job-verify-cap")
    await runner.process(make_event("job-verify-cap"))
    capped = await verification_report(settings, "job-verify-cap")
    assert len(capped.rework_attempts) == 1
    assert capped.unresolved_submission_ids == ["stu-001"]
    assert capped.pending_human_approval == ["stu-002"]

    settings_b = make_settings(tmp_path / "b")
    memory_b = MemoryManager.from_settings(settings_b)
    runner_b, _ = build_runner(
        settings_b,
        memory_b,
        ConfidenceMapEvaluator(confidences),
        rework=StatefulReworkEvaluator(low_calls=1),
        verify_max_iterations=2,
    )
    stage_batch(settings_b, "job-verify-cap")
    await runner_b.process(make_event("job-verify-cap"))
    converged = await verification_report(settings_b, "job-verify-cap")
    assert len(converged.rework_attempts) == 2
    assert converged.unresolved_submission_ids == []
    assert converged.passed is True

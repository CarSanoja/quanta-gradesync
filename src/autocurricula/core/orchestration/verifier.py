from autocurricula.agents.evaluator import GradingEvaluator
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.batch_listing import (
    BatchObjectLister,
    compare_batch_objects,
)
from autocurricula.core.orchestration.context import STAGE_VERIFY, JobContext, StageCallable
from autocurricula.core.orchestration.goal_checks import (
    evaluate_goal_checks,
    items_of_kind,
    missing_files_check,
    pending_items_for_job,
)
from autocurricula.core.orchestration.grade_outcome import load_grade_report
from autocurricula.core.orchestration.incident_reviews import (
    enqueue_missing_file_reviews,
)
from autocurricula.core.orchestration.sis_records import covered_codes_by_student
from autocurricula.core.review import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ConfidenceGate,
    ReviewStore,
)
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.review import ReviewItem, ReviewKind
from autocurricula.schemas.sis_sync import SISGradeRecord
from autocurricula.schemas.verification import (
    OUTCOME_RECOVERED,
    OUTCOME_STILL_QUARANTINED,
    ReworkAttempt,
    VerificationReport,
)

DEFAULT_VERIFY_MAX_ITERATIONS = 2


def build_verify_step(
    memory_manager: MemoryManager,
    review_store: ReviewStore,
    *,
    rework_evaluator: GradingEvaluator | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    max_iterations: int = DEFAULT_VERIFY_MAX_ITERATIONS,
    batch_lister: BatchObjectLister | None = None,
) -> StageCallable:
    gate = ConfidenceGate(confidence_threshold)

    async def run(context: JobContext) -> JobContext:
        checks = await evaluate_goal_checks(context, review_store)
        missing = await compare_batch_objects(
            context.event, context.batch, batch_lister
        )
        if missing.missing:
            await enqueue_missing_file_reviews(
                context.job_id,
                context.batch,
                context.event.bucket,
                context.event.exam_batch_prefix,
                missing.missing,
                review_store,
            )
        checks = [*checks, missing_files_check(missing)]
        attempts, pending_approval, unresolved = await _rework_loop(
            context,
            memory_manager,
            review_store,
            gate,
            rework_evaluator,
            max_iterations,
        )
        grade_report = load_grade_report(context.session)
        failed_ids = (
            sorted(failure.submission_id for failure in grade_report.failures)
            if grade_report is not None
            else []
        )
        passed = all(check.passed for check in checks) and not unresolved
        report = VerificationReport(
            job_id=context.job_id,
            passed=passed,
            checks=checks,
            rework_attempts=attempts,
            pending_human_approval=sorted(pending_approval),
            unresolved_submission_ids=sorted(unresolved),
            failed_submission_ids=failed_ids,
            missing_files=missing,
            verified_at=utc_now(),
        )
        context.complete(STAGE_VERIFY, report)
        return context

    return run


async def _rework_loop(
    context: JobContext,
    memory_manager: MemoryManager,
    review_store: ReviewStore,
    gate: ConfidenceGate,
    rework_evaluator: GradingEvaluator | None,
    max_iterations: int,
) -> tuple[list[ReworkAttempt], list[str], list[str]]:
    pending_items = {
        item.student_id: item
        for item in items_of_kind(
            await pending_items_for_job(context, review_store), ReviewKind.GRADE
        )
    }
    unresolved_students = set(pending_items)
    attempts: list[ReworkAttempt] = []
    pending_approval: list[str] = []
    if rework_evaluator is None or max_iterations <= 0 or not unresolved_students:
        return attempts, pending_approval, _submissions_of(context, unresolved_students)
    submissions_by_student: dict[str, list] = {}
    for submission in context.batch.submissions:
        submissions_by_student.setdefault(submission.student_id, []).append(submission)
    retrieved = await memory_manager.retrieve_rubric_context(
        context.rubric, context.event.subject
    )
    for iteration in range(1, max_iterations + 1):
        if not unresolved_students:
            break
        outcomes: dict[str, str] = {}
        recovered: dict[str, GradingResult] = {}
        still: set[str] = set()
        for student_id in sorted(unresolved_students):
            submission = submissions_by_student[student_id][0]
            result = await rework_evaluator.grade(submission, context.rubric, retrieved)
            if gate.evaluate(result).quarantined:
                still.add(student_id)
            else:
                recovered[student_id] = result
        for student_id, result in recovered.items():
            submission_id = submissions_by_student[student_id][0].submission_id
            outcomes[submission_id] = OUTCOME_RECOVERED
            await _update_review_item(
                pending_items[student_id], context, result, iteration, gate, review_store
            )
            pending_approval.append(student_id)
        for student_id in still:
            submission_id = submissions_by_student[student_id][0].submission_id
            outcomes[submission_id] = OUTCOME_STILL_QUARANTINED
        attempts.append(ReworkAttempt(iteration=iteration, outcomes=outcomes))
        if not recovered:
            break
        unresolved_students = still
    return attempts, pending_approval, _submissions_of(context, unresolved_students)


async def _update_review_item(
    item: ReviewItem,
    context: JobContext,
    result: GradingResult,
    iteration: int,
    gate: ConfidenceGate,
    review_store: ReviewStore,
) -> None:
    record = _record_for(context, item.student_id, result)
    confidence = min(score.confidence for score in result.criterion_scores)
    updated = item.model_copy(
        update={
            "proposed_record": record,
            "reasons": list(item.reasons)
            + [
                f"rework iteration {iteration}: second-opinion grading cleared "
                f"the confidence gate at {confidence:.3f}"
            ],
            "rework_notes": list(item.rework_notes)
            + [
                f"iteration {iteration}: recovered at min confidence "
                f"{confidence:.3f} >= {gate.threshold:.2f}; awaiting one-click approval"
            ],
        }
    )
    await review_store.put(updated)


def _record_for(
    context: JobContext, student_id: str, result: GradingResult
) -> SISGradeRecord:
    covered = covered_codes_by_student(context.batch, context.audits.audits)
    return SISGradeRecord(
        student_id=student_id,
        subject=context.batch.subject,
        score=result.total_score,
        percentage=result.percentage,
        feedback=result.feedback,
        competency_codes=sorted(covered.get(student_id, set())),
        graded_at=context.grade_result.graded_at,
    )


def _submissions_of(context: JobContext, students: set[str]) -> list[str]:
    return [
        submission.submission_id
        for submission in context.batch.submissions
        if submission.student_id in students
    ]

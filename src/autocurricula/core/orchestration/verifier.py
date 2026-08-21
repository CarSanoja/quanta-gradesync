from autocurricula.agents.evaluator import GradingEvaluator
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.batch_listing import (
    BatchObjectLister,
    compare_batch_objects,
)
from autocurricula.core.orchestration.context import (
    STAGE_VERIFY,
    JobContext,
    StageCallable,
    StageExecutionError,
)
from autocurricula.core.orchestration.goal_checks import (
    evaluate_goal_checks,
    missing_files_check,
)
from autocurricula.core.orchestration.grade_outcome import load_grade_report
from autocurricula.core.orchestration.incident_reviews import (
    enqueue_missing_file_reviews,
)
from autocurricula.core.orchestration.rework_loop import run_rework_loop
from autocurricula.core.review import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ConfidenceGate,
    ReviewStore,
)
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.verification import VerificationReport

DEFAULT_VERIFY_MAX_ITERATIONS = 2

NO_GRADES_ERROR = "no submissions could be graded"


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
        attempts, pending_approval, unresolved = await run_rework_loop(
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
        if not context.grade_result.results:
            raise StageExecutionError(STAGE_VERIFY, NO_GRADES_ERROR)
        return context

    return run

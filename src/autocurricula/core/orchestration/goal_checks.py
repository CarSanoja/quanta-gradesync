from autocurricula.core.orchestration.context import JobContext
from autocurricula.core.review import ReviewStore
from autocurricula.schemas.review import ReviewItem
from autocurricula.schemas.verification import GoalCheck

CHECK_SUBMISSIONS_GRADED = "submissions_graded"
CHECK_AUDITS_COMPLETE = "audits_complete"
CHECK_RISK_COMPLETE = "risk_complete"
CHECK_SIS_AUTO_SYNCED = "sis_auto_synced"
CHECK_QUARANTINE_ACCOUNTED = "quarantine_accounted"


async def pending_items_for_job(
    context: JobContext, review_store: ReviewStore
) -> list[ReviewItem]:
    items = await review_store.list_pending()
    return [item for item in items if item.job_id == context.job_id]


async def evaluate_goal_checks(
    context: JobContext, review_store: ReviewStore
) -> list[GoalCheck]:
    batch = context.batch
    expected = {submission.submission_id for submission in batch.submissions}
    graded = {result.submission_id for result in context.grade_result.results}
    audited = {audit.submission_id for audit in context.audits.audits}
    assessed_students = {
        assessment.student_id for assessment in context.assessments.assessments
    }
    batch_students = {submission.student_id for submission in batch.submissions}
    pending = await pending_items_for_job(context, review_store)
    sync = context.sync_result
    return [
        GoalCheck(
            name=CHECK_SUBMISSIONS_GRADED,
            passed=graded == expected,
            detail=f"{len(graded)}/{len(expected)} graded",
        ),
        GoalCheck(
            name=CHECK_AUDITS_COMPLETE,
            passed=audited == graded,
            detail=f"{len(audited)}/{len(graded)} audited",
        ),
        GoalCheck(
            name=CHECK_RISK_COMPLETE,
            passed=assessed_students == batch_students,
            detail=f"{len(assessed_students)}/{len(batch_students)} assessed",
        ),
        GoalCheck(
            name=CHECK_SIS_AUTO_SYNCED,
            passed=sync.failed_count == 0,
            detail=f"sis failed_count={sync.failed_count} quarantined={sync.quarantined_count}",
        ),
        GoalCheck(
            name=CHECK_QUARANTINE_ACCOUNTED,
            passed=len(pending) == sync.quarantined_count,
            detail=(
                f"{len(pending)} pending review items for "
                f"{sync.quarantined_count} quarantined records"
            ),
        ),
    ]

from autocurricula.core.memory.fact_store import AssessmentFactStore
from autocurricula.core.memory.persistent_memory import PersistentStore
from autocurricula.core.memory.term_projection import record_assessment
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.grading import GradingBatchResult
from autocurricula.schemas.memory import ClassCompetencySnapshot, FactSource
from autocurricula.schemas.rubric import Rubric


async def write_profiles(
    store: PersistentStore,
    fact_store: AssessmentFactStore,
    batch: ExamBatch,
    batch_result: GradingBatchResult,
    term: str,
) -> int:
    submission_students = {
        submission.submission_id: submission.student_id
        for submission in batch.submissions
    }
    percentages_by_student: dict[str, list[float]] = {}
    for result in batch_result.results:
        student_id = submission_students.get(result.submission_id)
        if student_id is None:
            continue
        percentages_by_student.setdefault(student_id, []).append(result.percentage)
    recorded_at = batch_result.graded_at
    for student_id, percentages in percentages_by_student.items():
        await record_assessment(
            store,
            fact_store,
            student_id=student_id,
            job_id=batch_result.job_id,
            term=term,
            avg_percentage=sum(percentages) / len(percentages),
            submissions_count=len(percentages),
            source=FactSource.BATCH_SYNC,
            recorded_at=recorded_at,
        )
    return len(percentages_by_student)


async def write_class_snapshots(
    store: PersistentStore,
    batch: ExamBatch,
    batch_result: GradingBatchResult,
    rubric: Rubric,
) -> int:
    max_scores = {
        criterion.criterion_id: criterion.max_score for criterion in rubric.criteria
    }
    submission_students = {
        submission.submission_id: submission.student_id
        for submission in batch.submissions
    }
    mastery_by_criterion: dict[str, list[float]] = {}
    students_by_criterion: dict[str, set[str]] = {}
    for result in batch_result.results:
        student_id = submission_students.get(result.submission_id)
        if student_id is None:
            continue
        for criterion_score in result.criterion_scores:
            max_score = max_scores.get(criterion_score.criterion_id)
            if max_score is None or max_score <= 0:
                continue
            mastery = min(max(criterion_score.score / max_score, 0.0), 1.0)
            mastery_by_criterion.setdefault(criterion_score.criterion_id, []).append(
                mastery
            )
            students_by_criterion.setdefault(
                criterion_score.criterion_id, set()
            ).add(student_id)
    now = utc_now()
    for criterion_id, values in mastery_by_criterion.items():
        await store.put_class_snapshot(
            ClassCompetencySnapshot(
                class_id=batch.class_id,
                subject=batch.subject,
                competency_code=criterion_id,
                avg_mastery=sum(values) / len(values),
                student_count=len(students_by_criterion[criterion_id]),
                updated_at=now,
            )
        )
    return len(mastery_by_criterion)


async def merge_student_percentage(
    store: PersistentStore,
    fact_store: AssessmentFactStore,
    student_id: str,
    term: str,
    percentage: float,
    *,
    job_id: str,
    source: FactSource = FactSource.HUMAN_APPROVAL,
) -> None:
    await record_assessment(
        store,
        fact_store,
        student_id=student_id,
        job_id=job_id,
        term=term,
        avg_percentage=percentage,
        submissions_count=1,
        source=source,
    )

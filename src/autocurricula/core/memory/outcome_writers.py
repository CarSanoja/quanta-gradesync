from autocurricula.core.memory.persistent_memory import PersistentStore
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.grading import GradingBatchResult
from autocurricula.schemas.memory import (
    ClassCompetencySnapshot,
    EpisodicStudentProfile,
    TermSnapshot,
)
from autocurricula.schemas.rubric import Rubric
from autocurricula.schemas.common import utc_now


async def write_profiles(
    store: PersistentStore,
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
    for student_id, percentages in percentages_by_student.items():
        profile = await store.get_profile(student_id)
        previous_terms = profile.terms if profile is not None else []
        previous = next((item for item in previous_terms if item.term == term), None)
        snapshot = TermSnapshot(
            term=term,
            avg_percentage=sum(percentages) / len(percentages),
            submissions_count=len(percentages),
            risk_history=previous.risk_history if previous else [],
        )
        terms = [item for item in previous_terms if item.term != term]
        terms.append(snapshot)
        await store.put_profile(
            EpisodicStudentProfile(student_id=student_id, terms=terms)
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
    store: PersistentStore, student_id: str, term: str, percentage: float
) -> None:
    profile = await store.get_profile(student_id)
    previous_terms = profile.terms if profile is not None else []
    previous = next((item for item in previous_terms if item.term == term), None)
    if previous is None:
        snapshot = TermSnapshot(
            term=term, avg_percentage=percentage, submissions_count=1, risk_history=[]
        )
    else:
        count = previous.submissions_count + 1
        total = previous.avg_percentage * previous.submissions_count + percentage
        snapshot = TermSnapshot(
            term=term,
            avg_percentage=total / count,
            submissions_count=count,
            risk_history=previous.risk_history,
        )
    terms = [item for item in previous_terms if item.term != term]
    terms.append(snapshot)
    await store.put_profile(EpisodicStudentProfile(student_id=student_id, terms=terms))

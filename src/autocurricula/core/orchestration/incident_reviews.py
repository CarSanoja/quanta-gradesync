from pathlib import Path

from autocurricula.core.review import ReviewStore
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.review import (
    ReviewItem,
    ReviewKind,
    ReviewStatus,
    build_review_id,
)
from autocurricula.schemas.sis_sync import SISGradeRecord
from autocurricula.schemas.verification import SubmissionFailure

MISSING_FILE_REASON = "this scan arrived after grading started"
NO_GRADE_FEEDBACK = (
    "No automatic grade was produced for this exam; it needs manual grading."
)
RESOLVED_NOTE = "resolved automatically: the exam was graded on a later run"


def missing_file_reason(name: str) -> str:
    return f"{MISSING_FILE_REASON} and has not been graded: {name}"


def placeholder_record(student_id: str, subject: str) -> SISGradeRecord:
    return SISGradeRecord(
        student_id=student_id,
        subject=subject,
        score=0.0,
        percentage=0.0,
        feedback=NO_GRADE_FEEDBACK,
        graded_at=utc_now(),
    )


def _documents_by_student(batch: ExamBatch) -> dict[str, list[str]]:
    documents: dict[str, list[str]] = {}
    for submission in batch.submissions:
        paths = documents.setdefault(submission.student_id, [])
        paths.extend(file.gcs_uri for file in submission.files)
    return documents


def _incident_item(
    job_id: str,
    student_id: str,
    subject: str,
    kind: ReviewKind,
    reasons: list[str],
    documents: list[str],
) -> ReviewItem:
    return ReviewItem(
        review_id=build_review_id(job_id, student_id),
        job_id=job_id,
        student_id=student_id,
        subject=subject,
        kind=kind,
        reasons=reasons,
        document_paths=documents,
        proposed_record=placeholder_record(student_id, subject),
        created_at=utc_now(),
    )


async def enqueue_failure_reviews(
    job_id: str,
    batch: ExamBatch,
    failures: list[SubmissionFailure],
    review_store: ReviewStore,
) -> list[str]:
    documents = _documents_by_student(batch)
    reasons_by_student: dict[str, list[str]] = {}
    for failure in failures:
        entries = reasons_by_student.setdefault(failure.student_id, [])
        if failure.reason not in entries:
            entries.append(failure.reason)
    for student_id, reasons in sorted(reasons_by_student.items()):
        await review_store.put(
            _incident_item(
                job_id,
                student_id,
                batch.subject,
                ReviewKind.FAILED_GRADING,
                reasons,
                documents.get(student_id, []),
            )
        )
    return sorted(reasons_by_student)


async def enqueue_missing_file_reviews(
    job_id: str,
    batch: ExamBatch,
    bucket: str,
    prefix: str,
    missing: list[str],
    review_store: ReviewStore,
) -> list[str]:
    created: list[str] = []
    for name in missing:
        student_id = Path(name).stem
        if not student_id:
            continue
        existing = await review_store.get(build_review_id(job_id, student_id))
        if existing is not None and existing.kind == ReviewKind.GRADE:
            continue
        await review_store.put(
            _incident_item(
                job_id,
                student_id,
                batch.subject,
                ReviewKind.MISSING_FILE,
                [missing_file_reason(name)],
                [f"gs://{bucket}/{prefix.rstrip('/')}/{name}"],
            )
        )
        created.append(student_id)
    return created


async def resolve_incident_reviews(
    job_id: str, student_ids: set[str], review_store: ReviewStore
) -> list[str]:
    resolved: list[str] = []
    for student_id in sorted(student_ids):
        item = await review_store.get(build_review_id(job_id, student_id))
        if item is None or item.status != ReviewStatus.PENDING:
            continue
        if item.kind == ReviewKind.GRADE:
            continue
        await review_store.put(
            item.model_copy(
                update={
                    "status": ReviewStatus.RESOLVED,
                    "decided_at": utc_now(),
                    "rework_notes": list(item.rework_notes) + [RESOLVED_NOTE],
                }
            )
        )
        resolved.append(student_id)
    return resolved

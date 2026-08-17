from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.stages_outcome import TermResolver
from autocurricula.core.review import ReviewStore
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.grading import EvidenceSpan, GradingBatchResult
from autocurricula.schemas.review import ReviewItem, build_review_id
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteRequest, SISWriteResult
from autocurricula.tools.sis_connector import SUCCESS_STATUSES, SISConnector


class SisSyncError(RuntimeError):
    pass


async def enqueue_reviews(
    job_id: str,
    quarantined_records: list[SISGradeRecord],
    review_store: ReviewStore,
    reasons: dict[str, list[str]],
    evidence: dict[str, list[EvidenceSpan]],
    documents: dict[str, list[str]],
) -> None:
    now = utc_now()
    for record in quarantined_records:
        await review_store.put(
            ReviewItem(
                review_id=build_review_id(job_id, record.student_id),
                job_id=job_id,
                student_id=record.student_id,
                subject=record.subject,
                reasons=list(
                    dict.fromkeys(
                        reasons.get(
                            record.student_id, ["quarantined by confidence gate"]
                        )
                    )
                ),
                evidence=evidence.get(record.student_id, []),
                document_paths=documents.get(record.student_id, []),
                proposed_record=record,
                created_at=now,
            )
        )


async def write_auto_records(
    job_id: str,
    sis_connector: SISConnector,
    auto_records: list[SISGradeRecord],
    quarantined_count: int,
) -> SISWriteResult:
    if not auto_records:
        return SISWriteResult(
            job_id=job_id,
            per_record_statuses={},
            succeeded_count=0,
            failed_count=0,
            quarantined_count=quarantined_count,
        )
    result = await sis_connector.write_grades(
        SISWriteRequest(job_id=job_id, records=auto_records)
    )
    if result.failed_count > 0:
        failed = sorted(
            student_id
            for student_id, status in result.per_record_statuses.items()
            if status not in SUCCESS_STATUSES
        )
        raise SisSyncError(f"sis write failed for students: {failed}")
    return result.model_copy(update={"quarantined_count": quarantined_count})


async def persist_synced_outcomes(
    memory_manager: MemoryManager,
    batch: ExamBatch,
    grade_result: GradingBatchResult,
    quarantined_students: set[str],
    term_resolver: TermResolver,
    event,
    rubric,
) -> None:
    student_by_submission = {
        submission.submission_id: submission.student_id
        for submission in batch.submissions
    }
    synced_results = [
        result
        for result in grade_result.results
        if student_by_submission.get(result.submission_id) not in quarantined_students
    ]
    if not synced_results:
        return
    await memory_manager.persist_outcomes(
        batch,
        grade_result.model_copy(update={"results": synced_results}),
        term_resolver(event),
        rubric,
    )

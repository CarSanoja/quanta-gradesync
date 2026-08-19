from autocurricula.core.resilience.dead_letter_store import (
    DeadLetterEntry,
    DeadLetterStatus,
    DeadLetterStore,
)
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteResult
from autocurricula.tools.sis_connector import SUCCESS_STATUSES, SISConnector

DLQ_KIND_SIS_WRITE = "sis_write"


class SyncPartialError(RuntimeError):
    def __init__(self, merged: SISWriteResult, failed_ids: list[str]) -> None:
        super().__init__(f"sis write failed for students: {sorted(failed_ids)}")
        self.merged = merged
        self.failed_ids = sorted(failed_ids)


def succeeded_targets(previous: SISWriteResult | None) -> set[str]:
    if previous is None:
        return set()
    return {
        student_id
        for student_id, status in previous.per_record_statuses.items()
        if status in SUCCESS_STATUSES
    }


def retryable_records(
    records: list[SISGradeRecord],
    previous: SISWriteResult | None,
    pending_orphans: list[DeadLetterEntry],
    exhausted_orphans: list[DeadLetterEntry],
) -> list[SISGradeRecord]:
    already_done = succeeded_targets(previous)
    exhausted_targets = {entry.target for entry in exhausted_orphans}
    pending_targets = {entry.target for entry in pending_orphans}
    if pending_targets:
        return [
            record
            for record in records
            if record.student_id in pending_targets
            and record.student_id not in exhausted_targets
        ]
    return [
        record
        for record in records
        if record.student_id not in already_done
        and record.student_id not in exhausted_targets
    ]


async def write_with_rollback(
    *,
    job_id: str,
    sis_connector: SISConnector,
    records: list[SISGradeRecord],
    quarantined_count: int,
    dead_letter: DeadLetterStore,
    previous: SISWriteResult | None,
    max_attempts: int,
) -> SISWriteResult:
    orphans = await dead_letter.list_pending(job_id, DLQ_KIND_SIS_WRITE)
    exhausted = await dead_letter.list_exhausted(job_id, DLQ_KIND_SIS_WRITE)
    targets = retryable_records(records, previous, orphans, exhausted)
    previous_ok = succeeded_targets(previous)
    if not targets:
        return SISWriteResult(
            job_id=job_id,
            per_record_statuses={
                student_id: "ok"
                for student_id in previous_ok
            },
            succeeded_count=len(previous_ok),
            failed_count=0,
            quarantined_count=quarantined_count,
        )
    result = await sis_connector.write_grades(
        _request(job_id, targets)
    )
    failed_ids = sorted(
        student_id
        for student_id, status in result.per_record_statuses.items()
        if status not in SUCCESS_STATUSES
    )
    merged_statuses = {
        student_id: "ok" for student_id in previous_ok
    }
    merged_statuses.update(result.per_record_statuses)
    merged = SISWriteResult(
        job_id=job_id,
        per_record_statuses=merged_statuses,
        succeeded_count=sum(
            1 for status in merged_statuses.values() if status in SUCCESS_STATUSES
        ),
        failed_count=len(failed_ids),
        quarantined_count=quarantined_count,
    )
    if failed_ids:
        existing = {entry.target: entry for entry in orphans + exhausted}
        for student_id in failed_ids:
            prior = existing.get(student_id)
            attempts = (prior.attempts + 1) if prior is not None else 1
            entry = DeadLetterEntry(
                kind=DLQ_KIND_SIS_WRITE,
                job_id=job_id,
                target=student_id,
                reason="sis write returned non-success status",
                attempts=attempts,
                max_attempts=max_attempts,
                status=(
                    DeadLetterStatus.EXHAUSTED
                    if attempts >= max_attempts
                    else DeadLetterStatus.PENDING
                ),
            )
            await dead_letter.record(entry)
        raise SyncPartialError(merged, failed_ids)
    for entry in orphans:
        if entry.target in merged.per_record_statuses:
            await dead_letter.resolve(job_id, DLQ_KIND_SIS_WRITE, entry.target)
    return merged


def _request(job_id: str, records: list[SISGradeRecord]):
    from autocurricula.schemas.sis_sync import SISWriteRequest

    return SISWriteRequest(job_id=job_id, records=records)

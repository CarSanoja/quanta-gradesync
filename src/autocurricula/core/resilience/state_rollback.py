from autocurricula.core.resilience.dead_letter_store import DeadLetterEntry, DeadLetterStore
from autocurricula.core.resilience.orphan_ledger import (
    DLQ_KIND_SIS_WRITE,
    UNREACHABLE_STATUS,
    clear_written,
    known_orphans,
    park_rejected,
    park_unreachable,
)
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteRequest, SISWriteResult
from autocurricula.tools.sis_connector import SUCCESS_STATUSES, SISConnector, SisWriteError


class SyncPartialError(RuntimeError):
    def __init__(
        self, merged: SISWriteResult, failed_ids: list[str], message: str | None = None
    ) -> None:
        ordered = sorted(failed_ids)
        super().__init__(message or f"sis write failed for students: {ordered}")
        self.merged = merged
        self.failed_ids = ordered


class SyncOutageError(SyncPartialError):
    def __init__(
        self, merged: SISWriteResult, failed_ids: list[str], detail: str
    ) -> None:
        ordered = sorted(failed_ids)
        super().__init__(
            merged,
            ordered,
            f"sis unreachable ({detail}); {len(ordered)} records parked as "
            f"orphans: {ordered}",
        )
        self.detail = detail


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
            and record.student_id not in already_done
        ]
    return [
        record
        for record in records
        if record.student_id not in already_done
        and record.student_id not in exhausted_targets
    ]


def merge_result(
    job_id: str,
    previous_ok: set[str],
    statuses: dict[str, str],
    quarantined_count: int,
) -> SISWriteResult:
    merged_statuses = {student_id: "ok" for student_id in previous_ok}
    merged_statuses.update(statuses)
    succeeded = sum(
        1 for status in merged_statuses.values() if status in SUCCESS_STATUSES
    )
    return SISWriteResult(
        job_id=job_id,
        per_record_statuses=merged_statuses,
        succeeded_count=succeeded,
        failed_count=len(merged_statuses) - succeeded,
        quarantined_count=quarantined_count,
    )


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
    known = known_orphans(orphans + exhausted)
    if not targets:
        return merge_result(job_id, previous_ok, {}, quarantined_count)
    target_ids = [record.student_id for record in targets]
    try:
        result = await sis_connector.write_grades(
            SISWriteRequest(job_id=job_id, records=targets)
        )
    except SisWriteError as error:
        detail = f"{type(error).__name__}: {error}"
        merged = merge_result(
            job_id,
            previous_ok,
            {student_id: UNREACHABLE_STATUS for student_id in target_ids},
            quarantined_count,
        )
        await park_unreachable(
            dead_letter, job_id, target_ids, known, max_attempts, detail
        )
        raise SyncOutageError(merged, target_ids, detail) from error
    merged = merge_result(
        job_id, previous_ok, result.per_record_statuses, quarantined_count
    )
    await clear_written(dead_letter, job_id, known, merged.per_record_statuses)
    failed_ids = sorted(
        student_id
        for student_id, status in result.per_record_statuses.items()
        if status not in SUCCESS_STATUSES
    )
    if failed_ids:
        await park_rejected(dead_letter, job_id, failed_ids, known, max_attempts)
        raise SyncPartialError(merged, failed_ids)
    return merged

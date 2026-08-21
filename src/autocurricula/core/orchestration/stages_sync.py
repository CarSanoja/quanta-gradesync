import logging

from autocurricula.core.armor import (
    flagged_students,
    injection_reason,
    load_armor_report,
    resolve_legibility,
)
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.harness import BatchAnomalyBreaker
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.context import STAGE_SYNC, JobContext, StageCallable
from autocurricula.core.orchestration.grade_outcome import load_grade_report
from autocurricula.core.orchestration.incident_reviews import (
    enqueue_failure_reviews,
    resolve_incident_reviews,
)
from autocurricula.core.orchestration.sis_records import build_sis_write_request
from autocurricula.core.orchestration.stages_outcome import TermResolver, default_term
from autocurricula.core.orchestration.sync_breaker import apply_breaker
from autocurricula.core.orchestration.sync_governance import (
    build_sis_permission_gate,
    faithfulness_by_student,
    partition_by_gate,
    partition_records,
    stamp_provenance,
)
from autocurricula.core.orchestration.sync_io import (
    SisSyncError,
    enqueue_reviews,
    persist_synced_outcomes,
)
from autocurricula.core.resilience import (
    DeadLetterStore,
    SyncPartialError,
    write_with_rollback,
)
from autocurricula.core.review import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ConfidenceGate,
    ReviewStore,
)
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteResult
from autocurricula.tools.sis_connector import SISConnector

logger = logging.getLogger(__name__)

__all__ = ["SisSyncError", "build_sync_step"]

DEFAULT_DEAD_LETTER_MAX_ATTEMPTS = 3


def build_sync_step(
    memory_manager: MemoryManager,
    sis_connector: SISConnector,
    review_store: ReviewStore,
    term_resolver: TermResolver = default_term,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    breaker: BatchAnomalyBreaker | None = None,
    prompt_variant: PromptVariant | None = None,
    dead_letter: DeadLetterStore | None = None,
    dead_letter_max_attempts: int = DEFAULT_DEAD_LETTER_MAX_ATTEMPTS,
    legibility_enabled: bool | None = None,
    legibility_full_trust: float | None = None,
    legibility_confidence_floor: float | None = None,
) -> StageCallable:
    gate = ConfidenceGate(confidence_threshold)

    async def run(context: JobContext) -> JobContext:
        outputs = context.fetch_outputs
        grade_result = context.grade_result
        grade_report = load_grade_report(context.session)
        failures = list(grade_report.failures) if grade_report is not None else []
        failed_students = {failure.student_id for failure in failures}
        manifest_students = {
            submission.student_id for submission in outputs.batch.submissions
        }
        request = build_sis_write_request(
            outputs.batch, grade_result, context.audits.audits
        )
        factors, legibility = await resolve_legibility(
            outputs.batch,
            legibility_enabled,
            legibility_full_trust,
            legibility_confidence_floor,
        )
        _, reasons, evidence, documents, confidences = partition_by_gate(
            outputs.batch,
            grade_result,
            gate,
            confidence_factors=factors,
            legibility=legibility,
        )
        armor_flagged = flagged_students(
            load_armor_report(context.session), outputs.batch
        )
        for student_id, quote in armor_flagged.items():
            reasons.setdefault(student_id, []).insert(0, injection_reason(quote))
        permission = build_sis_permission_gate(
            {submission.student_id for submission in outputs.batch.submissions},
            confidence_threshold,
        )
        auto_records, quarantined_records = partition_records(
            request.records, permission, confidences, armor_flagged
        )
        if breaker is not None:
            quarantined_records, auto_records = apply_breaker(
                breaker,
                len(manifest_students),
                quarantined_records,
                auto_records,
                reasons,
                len(failed_students),
            )
        quarantined_students = {record.student_id for record in quarantined_records}
        stamped = stamp_provenance(
            request.records,
            grade_result,
            prompt_variant,
            evidence,
            faithfulness_by_student(
                outputs.batch,
                grade_report.faithfulness if grade_report is not None else {},
            ),
        )
        await enqueue_reviews(
            context.job_id,
            [stamped[record.student_id] for record in quarantined_records],
            review_store,
            reasons,
            evidence,
            documents,
        )
        await enqueue_failure_reviews(
            context.job_id, outputs.batch, failures, review_store
        )
        await resolve_incident_reviews(
            context.job_id,
            {record.student_id for record in auto_records} - failed_students,
            review_store,
        )
        sis_result = await _write_with_state_rollback(
            context,
            sis_connector,
            [stamped[record.student_id] for record in auto_records],
            len(quarantined_records),
            dead_letter,
            dead_letter_max_attempts,
        )
        await persist_synced_outcomes(
            memory_manager,
            outputs.batch,
            grade_result,
            quarantined_students,
            term_resolver,
            context.event,
            outputs.rubric,
        )
        context.complete(STAGE_SYNC, sis_result)
        return context

    return run


async def _write_with_state_rollback(
    context,
    sis_connector: SISConnector,
    auto_records: list[SISGradeRecord],
    quarantined_count: int,
    dead_letter: DeadLetterStore | None,
    dead_letter_max_attempts: int,
) -> SISWriteResult:
    previous = None
    try:
        previous = context.session.get_stage_result(STAGE_SYNC, SISWriteResult)
    except Exception:
        previous = None
    if dead_letter is None:
        from autocurricula.core.orchestration.sync_io import write_auto_records

        return await write_auto_records(
            context.job_id, sis_connector, auto_records, quarantined_count
        )
    try:
        return await write_with_rollback(
            job_id=context.job_id,
            sis_connector=sis_connector,
            records=auto_records,
            quarantined_count=quarantined_count,
            dead_letter=dead_letter,
            previous=previous if isinstance(previous, SISWriteResult) else None,
            max_attempts=dead_letter_max_attempts,
        )
    except SyncPartialError as partial:
        context.session.set_stage_result(STAGE_SYNC, partial.merged)
        raise

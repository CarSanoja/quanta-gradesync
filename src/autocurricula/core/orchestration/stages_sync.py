import logging

from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.harness import (
    BatchAnomalyBreaker,
    BreakerTripped,
    PermissionDecision,
)
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.context import STAGE_SYNC, JobContext, StageCallable
from autocurricula.core.orchestration.sis_records import build_sis_write_request
from autocurricula.core.orchestration.stages_outcome import TermResolver, default_term
from autocurricula.core.orchestration.sync_governance import (
    build_provenance,
    build_sis_permission_gate,
    partition_by_gate,
    sis_action,
)
from autocurricula.core.orchestration.sync_io import (
    SisSyncError,
    enqueue_reviews,
    persist_synced_outcomes,
    write_auto_records,
)
from autocurricula.core.review import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ConfidenceGate,
    ReviewStore,
)
from autocurricula.schemas.sis_sync import SISGradeRecord
from autocurricula.tools.sis_connector import SISConnector

logger = logging.getLogger(__name__)

__all__ = ["SisSyncError", "build_sync_step"]


def build_sync_step(
    memory_manager: MemoryManager,
    sis_connector: SISConnector,
    review_store: ReviewStore,
    term_resolver: TermResolver = default_term,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    breaker: BatchAnomalyBreaker | None = None,
    prompt_variant: PromptVariant | None = None,
) -> StageCallable:
    gate = ConfidenceGate(confidence_threshold)

    async def run(context: JobContext) -> JobContext:
        outputs = context.fetch_outputs
        grade_result = context.grade_result
        request = build_sis_write_request(
            outputs.batch, grade_result, context.audits.audits
        )
        _, reasons, evidence, documents, confidences = partition_by_gate(
            outputs.batch, grade_result, gate
        )
        permission = build_sis_permission_gate(
            {submission.student_id for submission in outputs.batch.submissions},
            confidence_threshold,
        )
        auto_records: list[SISGradeRecord] = []
        quarantined_records: list[SISGradeRecord] = []
        for record in request.records:
            verdict = permission.evaluate(
                sis_action(record, confidences.get(record.student_id, 0.0))
            )
            if verdict.decision == PermissionDecision.DENY:
                logger.warning(
                    "harness denied sis write for out-of-manifest target %s",
                    record.student_id,
                )
            elif verdict.decision == PermissionDecision.QUARANTINE:
                quarantined_records.append(record)
            else:
                auto_records.append(record)
        if breaker is not None:
            quarantined_records, auto_records = _apply_breaker(
                breaker, len(request.records), quarantined_records, auto_records, reasons
            )
        quarantined_students = {record.student_id for record in quarantined_records}
        stamped = {
            record.student_id: record.model_copy(
                update={
                    "provenance": build_provenance(
                        record.student_id,
                        grade_result,
                        prompt_variant,
                        evidence.get(record.student_id, []),
                    )
                }
            )
            for record in request.records
        }
        await enqueue_reviews(
            context.job_id,
            [stamped[record.student_id] for record in quarantined_records],
            review_store,
            reasons,
            evidence,
            documents,
        )
        sis_result = await write_auto_records(
            context.job_id,
            sis_connector,
            [stamped[record.student_id] for record in auto_records],
            len(quarantined_records),
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


def _apply_breaker(
    breaker: BatchAnomalyBreaker,
    total: int,
    quarantined: list[SISGradeRecord],
    auto: list[SISGradeRecord],
    reasons: dict[str, list[str]],
) -> tuple[list[SISGradeRecord], list[SISGradeRecord]]:
    try:
        breaker.evaluate(total, len(quarantined))
    except BreakerTripped as tripped:
        moved = list(auto)
        for record in moved:
            reasons.setdefault(record.student_id, []).insert(
                0, f"batch anomaly breaker: {tripped}"
            )
        logger.warning("%s", tripped)
        return quarantined + moved, []
    return quarantined, auto

import asyncio
import logging

from autocurricula.agents.curriculum_auditor import CurriculumAuditor
from autocurricula.agents.evaluator import GradingEvaluator
from autocurricula.core.armor import InjectionDetector, store_armor_report
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import JobCatalog
from autocurricula.core.orchestration.context import (
    STAGE_AUDIT,
    STAGE_FETCH,
    STAGE_GRADE,
    AuditOutputs,
    FetchOutputs,
    JobContext,
    StageCallable,
    StageExecutionError,
)
from autocurricula.core.orchestration.grade_guard import build_grade_guard
from autocurricula.core.resilience import (
    DeadLetterStore,
    SchemaRepairAgent,
)
from autocurricula.core.telemetry import Recorder
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.grading import GradingBatchResult
from autocurricula.tools.gcs_fetcher import Fetcher

logger = logging.getLogger(__name__)

SCRIPTED_MODEL_ID = "scripted-grading-evaluator"

DEFAULT_FALLBACK_LATENCY_SECONDS = 90.0
DEFAULT_FALLBACK_CONFIDENCE_FACTOR = 0.9


def _resolve_model_id(
    grading_evaluator: GradingEvaluator, model_id: str | None
) -> str:
    if model_id:
        return model_id
    return getattr(grading_evaluator, "model", None) or SCRIPTED_MODEL_ID


def build_fetch_step(
    catalog: JobCatalog, fetcher: Fetcher
) -> StageCallable:
    async def run(context: JobContext) -> JobContext:
        manifest = await catalog.load_manifest(context.event)
        batch = await fetcher.fetch_batch(manifest.batch)
        context.complete(
            STAGE_FETCH,
            FetchOutputs(
                batch=batch,
                rubric=manifest.rubric,
                curriculum_standard=manifest.curriculum_standard,
            ),
        )
        return context

    return run


def build_grade_step(
    memory_manager: MemoryManager,
    grading_evaluator: GradingEvaluator,
    model_id: str | None = None,
    *,
    faithfulness_enabled: bool = True,
    fallback_evaluator: GradingEvaluator | None = None,
    fallback_latency_seconds: float = DEFAULT_FALLBACK_LATENCY_SECONDS,
    fallback_confidence_factor: float = DEFAULT_FALLBACK_CONFIDENCE_FACTOR,
    repair_agent: SchemaRepairAgent | None = None,
    dead_letter: DeadLetterStore | None = None,
    dead_letter_max_attempts: int = 3,
    armor_detector: InjectionDetector | None = None,
    armor_enabled: bool | None = None,
) -> StageCallable:
    async def run(context: JobContext) -> JobContext:
        outputs = context.fetch_outputs
        retrieved = await memory_manager.retrieve_rubric_context(
            outputs.rubric, context.event.subject
        )
        recorder: Recorder = context.recorder
        guard = build_grade_guard(
            job_id=context.job_id,
            evaluator=grading_evaluator,
            fallback=fallback_evaluator,
            latency_seconds=fallback_latency_seconds,
            confidence_factor=fallback_confidence_factor,
            repair_agent=repair_agent,
            dead_letter=dead_letter,
            dead_letter_max_attempts=dead_letter_max_attempts,
            model_id=_resolve_model_id(grading_evaluator, model_id),
            recorder=recorder,
            faithfulness_enabled=faithfulness_enabled,
            batch=outputs.batch,
            armor_detector=armor_detector,
            armor_enabled=armor_enabled,
        )

        graded_results = await asyncio.gather(
            *(
                guard.grade(submission, outputs.rubric, retrieved)
                for submission in outputs.batch.submissions
            )
        )
        results = [result for result in graded_results if result is not None]
        if guard.armor is not None:
            store_armor_report(context.session, context.job_id, guard.armor_verdicts)
        if not results:
            raise StageExecutionError(STAGE_GRADE, "no submissions could be graded")
        context.complete(
            STAGE_GRADE,
            GradingBatchResult(
                job_id=context.job_id,
                results=results,
                graded_at=utc_now(),
                model_id=_resolve_model_id(grading_evaluator, model_id),
            ),
        )
        return context

    return run


def build_audit_step(
    memory_manager: MemoryManager, auditor: CurriculumAuditor
) -> StageCallable:
    async def run(context: JobContext) -> JobContext:
        standard = context.curriculum_standard
        query = " ".join(
            f"{competency.code} {competency.description}"
            for competency in standard.competencies
        )
        retrieved = await memory_manager.l2.search(query)
        audits = await asyncio.gather(
            *(
                auditor.audit(result, standard, retrieved)
                for result in context.grade_result.results
            )
        )
        context.complete(STAGE_AUDIT, AuditOutputs(audits=list(audits)))
        return context

    return run

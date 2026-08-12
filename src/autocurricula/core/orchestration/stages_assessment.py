import asyncio
import logging

from autocurricula.agents.curriculum_auditor import CurriculumAuditor
from autocurricula.agents.evaluator import GradingEvaluator
from autocurricula.core.harness import (
    DEFAULT_MAX_CALLS_PER_ITEM,
    ItemBudget,
    SidecarTextProvider,
    enforce_result,
    guard_item,
    sidecar_texts_from_batch,
)
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
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.grading import GradingBatchResult, GradingResult
from autocurricula.tools.gcs_fetcher import Fetcher

logger = logging.getLogger(__name__)

SCRIPTED_MODEL_ID = "scripted-grading-evaluator"


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
    max_calls_per_item: int = DEFAULT_MAX_CALLS_PER_ITEM,
    faithfulness_enabled: bool = True,
) -> StageCallable:
    async def run(context: JobContext) -> JobContext:
        outputs = context.fetch_outputs
        retrieved = await memory_manager.retrieve_rubric_context(
            outputs.rubric, context.event.subject
        )
        provider = (
            SidecarTextProvider(sidecar_texts_from_batch(outputs.batch))
            if faithfulness_enabled
            else None
        )

        async def graded(submission) -> GradingResult | None:
            budget = ItemBudget(max_calls=max_calls_per_item)
            try:
                result = await guard_item(
                    lambda: grading_evaluator.grade(
                        submission, outputs.rubric, retrieved
                    ),
                    budget,
                )
            except Exception as error:
                logger.warning(
                    "harness isolated submission %s: %s: %s",
                    submission.submission_id,
                    type(error).__name__,
                    error,
                )
                return None
            if provider is not None:
                result = enforce_result(result, provider)
            return result

        graded_results = await asyncio.gather(
            *(graded(submission) for submission in outputs.batch.submissions)
        )
        results = [result for result in graded_results if result is not None]
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

from collections.abc import Sequence

from autocurricula.agents.curriculum_auditor import CurriculumAuditor
from autocurricula.agents.evaluator import GradingEvaluator
from autocurricula.agents.meta_optimizer import MetaOptimizerAgent
from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.harness import DEFAULT_MATCH_THRESHOLD, BatchAnomalyBreaker
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import JobCatalog
from autocurricula.core.orchestration.context import (
    STAGE_AUDIT,
    STAGE_FETCH,
    STAGE_GRADE,
    STAGE_OPTIMIZE,
    STAGE_RISK,
    STAGE_SYNC,
    STAGE_VERIFY,
    StageCallable,
    StageStep,
)
from autocurricula.core.orchestration.stages_assessment import (
    build_audit_step,
    build_fetch_step,
    build_grade_step,
)
from autocurricula.core.orchestration.stages_outcome import (
    TermResolver,
    build_optimize_step,
    build_risk_step,
    default_term,
)
from autocurricula.core.orchestration.stages_sync import build_sync_step
from autocurricula.core.orchestration.transcription_stage import PageTranscriber
from autocurricula.core.orchestration.verifier import (
    DEFAULT_VERIFY_MAX_ITERATIONS,
    build_verify_step,
)
from autocurricula.core.resilience import DeadLetterStore, SchemaRepairAgent
from autocurricula.core.review import DEFAULT_CONFIDENCE_THRESHOLD, ReviewStore
from autocurricula.tools.gcs_fetcher import Fetcher
from autocurricula.tools.sis_connector import SISConnector


def build_pipeline(
    *,
    memory_manager: MemoryManager,
    fetcher: Fetcher,
    catalog: JobCatalog,
    grading_evaluator: GradingEvaluator,
    auditor: CurriculumAuditor,
    risk_detector: RiskDetector,
    sis_connector: SISConnector,
    review_store: ReviewStore,
    optimizers: Sequence[MetaOptimizerAgent] | None = None,
    term_resolver: TermResolver = default_term,
    grading_model_id: str | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    rework_evaluator: GradingEvaluator | None = None,
    verify_max_iterations: int = DEFAULT_VERIFY_MAX_ITERATIONS,
    sis_breaker: BatchAnomalyBreaker | None = None,
    prompt_variant: PromptVariant | None = None,
    faithfulness_enabled: bool = True,
    fallback_evaluator: GradingEvaluator | None = None,
    fallback_latency_seconds: float = 90.0,
    fallback_confidence_factor: float = 0.9,
    repair_agent: SchemaRepairAgent | None = None,
    dead_letter: DeadLetterStore | None = None,
    dead_letter_max_attempts: int = 3,
    transcriber: PageTranscriber | None = None,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> list[StageStep]:
    grade_step: StageCallable = build_grade_step(
        memory_manager,
        grading_evaluator,
        grading_model_id,
        faithfulness_enabled=faithfulness_enabled,
        fallback_evaluator=fallback_evaluator,
        fallback_latency_seconds=fallback_latency_seconds,
        fallback_confidence_factor=fallback_confidence_factor,
        repair_agent=repair_agent,
        dead_letter=dead_letter,
        dead_letter_max_attempts=dead_letter_max_attempts,
        transcriber=transcriber,
        match_threshold=match_threshold,
    )
    return [
        StageStep(name=STAGE_FETCH, callable=build_fetch_step(catalog, fetcher)),
        StageStep(name=STAGE_GRADE, callable=grade_step),
        StageStep(name=STAGE_AUDIT, callable=build_audit_step(memory_manager, auditor)),
        StageStep(name=STAGE_RISK, callable=build_risk_step(memory_manager, risk_detector)),
        StageStep(
            name=STAGE_SYNC,
            callable=build_sync_step(
                memory_manager,
                sis_connector,
                review_store,
                term_resolver=term_resolver,
                confidence_threshold=confidence_threshold,
                breaker=sis_breaker,
                prompt_variant=prompt_variant,
                dead_letter=dead_letter,
                dead_letter_max_attempts=dead_letter_max_attempts,
            ),
        ),
        StageStep(
            name=STAGE_VERIFY,
            callable=build_verify_step(
                memory_manager,
                review_store,
                rework_evaluator=rework_evaluator,
                confidence_threshold=confidence_threshold,
                max_iterations=verify_max_iterations,
            ),
        ),
        StageStep(
            name=STAGE_OPTIMIZE,
            callable=build_optimize_step(list(optimizers or [])),
        ),
    ]

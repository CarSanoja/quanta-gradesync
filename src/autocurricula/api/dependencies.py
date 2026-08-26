import asyncio
from dataclasses import dataclass, field

from fastapi import FastAPI, Request

from autocurricula.agents.curriculum_auditor import (
    CurriculumAuditor,
    build_curriculum_auditor,
)
from autocurricula.agents.evaluator import GradingEvaluator
from autocurricula.agents.grading_agent import build_grading_evaluator
from autocurricula.agents.meta_optimizer import MetaOptimizerAgent
from autocurricula.agents.optimizer_factory import build_optimizer_fleet
from autocurricula.agents.rework_evaluator import build_rework_evaluator
from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.config.settings import Settings, get_settings
from autocurricula.core.harness import BatchAnomalyBreaker
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.batch_settle import BatchSettler, build_batch_settler
from autocurricula.core.orchestration.catalog import JobCatalog, build_job_catalog
from autocurricula.core.orchestration.job_state import (
    CheckpointStore,
    JobRecord,
    build_checkpoint_store,
)
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.resilience import (
    SchemaRepairAgent,
    build_dead_letter_store,
)
from autocurricula.core.review import ReviewService, ReviewStore, build_review_store
from autocurricula.core.telemetry import LiveSink, build_audit_logger, build_live_sink
from autocurricula.tools.gcs_fetcher import Fetcher, build_fetcher
from autocurricula.tools.sis_connector import SISConnector, build_sis_connector

CONTAINER_STATE_KEY = "app_container"


@dataclass
class AppContainer:
    settings: Settings
    memory_manager: MemoryManager
    checkpoint_store: CheckpointStore
    job_runner: JobRunner
    fetcher: Fetcher
    grading_evaluator: GradingEvaluator
    auditor: CurriculumAuditor
    risk_detector: RiskDetector
    sis_connector: SISConnector
    optimizers: list[MetaOptimizerAgent]
    catalog: JobCatalog
    review_service: ReviewService
    rework_evaluator: GradingEvaluator | None = None
    fallback_evaluator: GradingEvaluator | None = None
    batch_settler: BatchSettler | None = None
    live_sink: LiveSink | None = None
    in_flight: set[asyncio.Task[JobRecord]] = field(default_factory=set)
    claimed_jobs: set[str] = field(default_factory=set)


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved = settings if settings is not None else get_settings()
    memory_manager = MemoryManager.from_settings(resolved)
    checkpoint_store = build_checkpoint_store(resolved)
    fetcher = build_fetcher(resolved)
    grading_evaluator = build_grading_evaluator(resolved)
    auditor = build_curriculum_auditor(resolved)
    risk_detector = RiskDetector()
    sis_connector = build_sis_connector(resolved)
    optimizers = build_optimizer_fleet(resolved, memory_manager=memory_manager)
    catalog = build_job_catalog(resolved)
    prompt_variant = _active_grading_variant(optimizers)
    rework_evaluator = build_rework_evaluator(resolved)
    fallback_evaluator = build_rework_evaluator(resolved)
    review_store: ReviewStore = build_review_store(resolved)
    live_sink = build_live_sink(resolved)
    review_service = ReviewService(
        store=review_store,
        sis_connector=sis_connector,
        memory_manager=memory_manager,
    )
    job_runner = JobRunner(
        memory_manager=memory_manager,
        fetcher=fetcher,
        grading_evaluator=grading_evaluator,
        auditor=auditor,
        risk_detector=risk_detector,
        sis_connector=sis_connector,
        checkpoint_store=checkpoint_store,
        optimizers=optimizers,
        catalog=catalog,
        review_store=review_store,
        confidence_threshold=resolved.confidence_threshold,
        rework_evaluator=rework_evaluator,
        verify_max_iterations=resolved.verify_max_iterations,
        sis_breaker=BatchAnomalyBreaker(resolved.batch_anomaly_threshold),
        prompt_variant=prompt_variant,
        fallback_evaluator=fallback_evaluator,
        fallback_latency_seconds=resolved.model_fallback_latency_seconds,
        fallback_confidence_factor=resolved.model_fallback_confidence_factor,
        repair_agent=SchemaRepairAgent(resolved.schema_repair_attempts),
        dead_letter=build_dead_letter_store(resolved),
        dead_letter_max_attempts=resolved.dead_letter_max_attempts,
        audit_logger=(
            build_audit_logger(resolved)
            if resolved.telemetry_audit_enabled
            else None
        ),
        live_sink=live_sink,
    )
    return AppContainer(
        settings=resolved,
        memory_manager=memory_manager,
        checkpoint_store=checkpoint_store,
        job_runner=job_runner,
        fetcher=fetcher,
        grading_evaluator=grading_evaluator,
        auditor=auditor,
        risk_detector=risk_detector,
        sis_connector=sis_connector,
        optimizers=optimizers,
        catalog=catalog,
        review_service=review_service,
        rework_evaluator=rework_evaluator,
        fallback_evaluator=fallback_evaluator,
        batch_settler=build_batch_settler(resolved),
        live_sink=live_sink,
    )


def _active_grading_variant(optimizers: list[MetaOptimizerAgent]):
    for optimizer in optimizers:
        if optimizer.variant_id != "grading-v1":
            continue
        try:
            return optimizer.registry.get(optimizer.variant_id)
        except ValueError:
            return None
    return None


def get_container(request: Request) -> AppContainer:
    container = getattr(request.app.state, CONTAINER_STATE_KEY, None)
    if container is None:
        raise RuntimeError(
            "app container is not initialized; run the app lifespan or call set_container"
        )
    return container


def set_container(app: FastAPI, container: AppContainer) -> None:
    setattr(app.state, CONTAINER_STATE_KEY, container)

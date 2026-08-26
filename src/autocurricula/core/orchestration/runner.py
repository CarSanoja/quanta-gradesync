import asyncio
import logging
from collections.abc import Sequence

from autocurricula.agents.curriculum_auditor import CurriculumAuditor
from autocurricula.agents.evaluator import GradingEvaluator
from autocurricula.agents.meta_optimizer import MetaOptimizerAgent
from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.config.settings import get_settings
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.fleet import (
    FIRESTORE_CHECKPOINT,
    ORCHESTRATOR_PRINCIPAL,
    authorize_firestore_write,
)
from autocurricula.core.harness import BatchAnomalyBreaker, CapabilityLedger, capability_scope
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.memory.session_memory import SessionMemory, SessionState, StageStatus
from autocurricula.core.orchestration.catalog import JobCatalog, build_job_catalog
from autocurricula.core.orchestration.context import STAGE_COMPLETION, JobContext, StageStep
from autocurricula.core.orchestration.graph import build_pipeline
from autocurricula.core.orchestration.job_state import (
    CheckpointStore,
    JobRecord,
    JobStage,
)
from autocurricula.core.orchestration.stage_execution import execute_stage
from autocurricula.core.orchestration.stages_outcome import TermResolver, default_term
from autocurricula.core.orchestration.verifier import DEFAULT_VERIFY_MAX_ITERATIONS
from autocurricula.core.resilience import DeadLetterStore, SchemaRepairAgent
from autocurricula.core.review import DEFAULT_CONFIDENCE_THRESHOLD, ReviewStore, build_review_store
from autocurricula.core.telemetry import AuditLogger, LiveSink, Recorder, collect_metrics
from autocurricula.core.telemetry.otel_setup import flush_telemetry
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.tools.gcs_fetcher import Fetcher
from autocurricula.tools.sis_connector import SISConnector

LIVE_FLUSH_TIMEOUT_SECONDS = 5.0


class JobRunner:
    def __init__(
        self,
        memory_manager: MemoryManager,
        fetcher: Fetcher,
        grading_evaluator: GradingEvaluator,
        auditor: CurriculumAuditor,
        risk_detector: RiskDetector,
        sis_connector: SISConnector,
        checkpoint_store: CheckpointStore,
        optimizers: Sequence[MetaOptimizerAgent] | None = None,
        *,
        catalog: JobCatalog | None = None,
        review_store: ReviewStore | None = None,
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
        audit_logger: AuditLogger | None = None,
        live_sink: LiveSink | None = None,
    ) -> None:
        self._memory_manager = memory_manager
        self._checkpoint_store = checkpoint_store
        self._optimizers = list(optimizers or [])
        self._catalog = catalog if catalog is not None else build_job_catalog(get_settings())
        self._review_store = (
            review_store if review_store is not None else build_review_store(get_settings())
        )
        self._pipeline = build_pipeline(
            memory_manager=memory_manager,
            fetcher=fetcher,
            catalog=self._catalog,
            grading_evaluator=grading_evaluator,
            auditor=auditor,
            risk_detector=risk_detector,
            sis_connector=sis_connector,
            review_store=self._review_store,
            optimizers=self._optimizers,
            term_resolver=term_resolver,
            grading_model_id=grading_model_id,
            confidence_threshold=confidence_threshold,
            rework_evaluator=rework_evaluator,
            verify_max_iterations=verify_max_iterations,
            sis_breaker=sis_breaker,
            prompt_variant=prompt_variant,
            faithfulness_enabled=faithfulness_enabled,
            fallback_evaluator=fallback_evaluator,
            fallback_latency_seconds=fallback_latency_seconds,
            fallback_confidence_factor=fallback_confidence_factor,
            repair_agent=repair_agent,
            dead_letter=dead_letter,
            dead_letter_max_attempts=dead_letter_max_attempts,
        )
        self._audit_logger = audit_logger
        self._live_sink = live_sink

    @property
    def pipeline(self) -> list[StageStep]:
        return list(self._pipeline)

    async def process(self, event: PubSubJobEvent) -> JobRecord:
        with capability_scope() as ledger:
            return await self._process(event, ledger)

    async def _process(
        self, event: PubSubJobEvent, ledger: CapabilityLedger
    ) -> JobRecord:
        existing = await self._checkpoint_store.get(event.job_id)
        if existing is not None and existing.stage == JobStage.COMPLETED:
            return existing
        session = self._memory_manager.new_session(event.job_id)
        record = JobRecord(job_id=event.job_id, event=event)
        authorize_firestore_write(
            ORCHESTRATOR_PRINCIPAL, FIRESTORE_CHECKPOINT, event.job_id
        )
        if existing is not None:
            await self._restore_session(session, existing)
        record.stage_statuses = dict(session.state.stage_statuses)
        await self._checkpoint_store.save(record)
        recorder = Recorder(event.trace_id, sink=self._live_sink, job_id=event.job_id)
        context = JobContext(event=event, session=session, recorder=recorder)
        for step in self._pipeline:
            if context.stage_done(step.name):
                continue
            session.mark_stage(step.name, StageStatus.RUNNING)
            try:
                context = await execute_stage(step, context, recorder)
            except Exception as error:
                await self._flush_live()
                record = await self._fail(record, session, step.name, error)
                await self._audit(recorder, record, ledger)
                return record
            session.mark_stage(step.name, StageStatus.SUCCEEDED)
            self._advance(record, session, step.name)
            await self._checkpoint_store.save_state(event.job_id, session.state)
            await self._checkpoint_store.save(record)
        record.stage = JobStage.COMPLETED
        record.error = None
        record.updated_at = utc_now()
        await self._flush_live()
        await self._checkpoint_store.save_state(event.job_id, session.state)
        await self._checkpoint_store.save(record)
        await self._audit(recorder, record, ledger)
        return record

    async def _flush_live(self) -> None:
        await asyncio.to_thread(flush_telemetry)
        if self._live_sink is None:
            return
        try:
            await asyncio.to_thread(self._live_sink.flush, LIVE_FLUSH_TIMEOUT_SECONDS)
        except Exception as error:
            logging.getLogger(__name__).warning("live sink flush failed: %s", error)

    async def _audit(
        self,
        recorder: Recorder,
        record: JobRecord,
        ledger: CapabilityLedger | None = None,
    ) -> None:
        if self._audit_logger is None:
            return
        try:
            await self._audit_logger.append(
                record.job_id,
                recorder.trace_id,
                recorder.spans,
                {
                    "stage": record.stage.value,
                    "error": record.error,
                    "metrics": collect_metrics(recorder.spans).model_dump(),
                    "capability_denials": [
                        denial.model_dump(mode="json")
                        for denial in (ledger.denials if ledger is not None else [])
                    ],
                },
            )
        except Exception as error:
            logging.getLogger(__name__).warning(
                "audit trail append failed for job %s: %s", record.job_id, error
            )

    async def _restore_session(
        self, session: SessionMemory, existing: JobRecord
    ) -> None:
        state = await self._checkpoint_store.load_state(existing.job_id)
        if state is not None:
            self._replay_results(session, state)
        statuses = (
            state.stage_statuses if state is not None else existing.stage_statuses
        )
        for stage, status in statuses.items():
            try:
                session.mark_stage(stage, StageStatus(status))
            except ValueError:
                continue

    @staticmethod
    def _replay_results(session: SessionMemory, state: SessionState) -> None:
        for stage, result in state.stage_results.items():
            session.set_stage_result(stage, result)

    @staticmethod
    def _advance(
        record: JobRecord, session: SessionMemory, stage_name: str
    ) -> JobRecord:
        record.stage = STAGE_COMPLETION.get(stage_name, record.stage)
        record.stage_statuses = dict(session.state.stage_statuses)
        record.updated_at = utc_now()
        return record

    async def _fail(
        self,
        record: JobRecord,
        session: SessionMemory,
        stage_name: str,
        error: Exception,
    ) -> JobRecord:
        session.mark_stage(stage_name, StageStatus.FAILED)
        record.stage = JobStage.FAILED
        record.error = f"{type(error).__name__}: {error}"
        record.stage_statuses = dict(session.state.stage_statuses)
        record.updated_at = utc_now()
        await self._checkpoint_store.save_state(record.job_id, session.state)
        await self._checkpoint_store.save(record)
        return record

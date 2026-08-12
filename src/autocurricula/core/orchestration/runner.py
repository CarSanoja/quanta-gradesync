from collections.abc import Sequence

from autocurricula.agents.curriculum_auditor import CurriculumAuditor
from autocurricula.agents.evaluator import GradingEvaluator
from autocurricula.agents.meta_optimizer import MetaOptimizerAgent
from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.config.settings import get_settings
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
from autocurricula.core.orchestration.stages_outcome import TermResolver, default_term
from autocurricula.core.orchestration.verifier import DEFAULT_VERIFY_MAX_ITERATIONS
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.harness import (
    DEFAULT_MAX_CALLS_PER_ITEM,
    BatchAnomalyBreaker,
)
from autocurricula.core.review import DEFAULT_CONFIDENCE_THRESHOLD, ReviewStore, build_review_store
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.tools.gcs_fetcher import Fetcher
from autocurricula.tools.sis_connector import SISConnector


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
        max_calls_per_item: int = DEFAULT_MAX_CALLS_PER_ITEM,
        faithfulness_enabled: bool = True,
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
            max_calls_per_item=max_calls_per_item,
            faithfulness_enabled=faithfulness_enabled,
        )

    @property
    def pipeline(self) -> list[StageStep]:
        return list(self._pipeline)

    async def process(self, event: PubSubJobEvent) -> JobRecord:
        existing = await self._checkpoint_store.get(event.job_id)
        if existing is not None and existing.stage == JobStage.COMPLETED:
            return existing
        session = self._memory_manager.new_session(event.job_id)
        record = JobRecord(job_id=event.job_id, event=event)
        if existing is not None:
            await self._restore_session(session, existing)
        record.stage_statuses = dict(session.state.stage_statuses)
        await self._checkpoint_store.save(record)
        context = JobContext(event=event, session=session)
        for step in self._pipeline:
            if context.stage_done(step.name):
                continue
            session.mark_stage(step.name, StageStatus.RUNNING)
            try:
                context = await step.callable(context)
            except Exception as error:
                return await self._fail(record, session, step.name, error)
            session.mark_stage(step.name, StageStatus.SUCCEEDED)
            self._advance(record, session, step.name)
            await self._checkpoint_store.save_state(event.job_id, session.state)
            await self._checkpoint_store.save(record)
        record.stage = JobStage.COMPLETED
        record.error = None
        record.updated_at = utc_now()
        await self._checkpoint_store.save_state(event.job_id, session.state)
        await self._checkpoint_store.save(record)
        return record

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

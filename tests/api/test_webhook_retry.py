import httpx

from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.api.dependencies import AppContainer
from autocurricula.config.settings import Settings
from autocurricula.core.orchestration.catalog import LocalJobCatalog
from autocurricula.core.orchestration.job_state import JobRecord, JobStage
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.review import LocalReviewStore
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.tools.gcs_fetcher import LocalStagingFetcher
from autocurricula.tools.sis_connector import LocalSISConnector
from tests.orchestration.verifier_fixtures import ConfidenceMapEvaluator
from tests.review.flow_stack import (
    STUDENTS,
    ScriptedAuditor,
    stage_batch,
)
from tests.review.flow_stack import make_event as make_flow_event


class RaisingThenCompletingRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def process(self, event: PubSubJobEvent) -> JobRecord:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("pipeline exploded")
        return JobRecord(job_id=event.job_id, event=event, stage=JobStage.COMPLETED)


class FailingThenCompletingRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def process(self, event: PubSubJobEvent) -> JobRecord:
        self.calls += 1
        if self.calls == 1:
            return JobRecord(
                job_id=event.job_id,
                event=event,
                stage=JobStage.FAILED,
                error="RuntimeError: stage grade: model unavailable",
            )
        return JobRecord(job_id=event.job_id, event=event, stage=JobStage.COMPLETED)


class CountingEvaluator:
    def __init__(self, inner: ConfidenceMapEvaluator) -> None:
        self._inner = inner
        self.calls = 0

    async def grade(self, submission, rubric, context):
        self.calls += 1
        return await self._inner.grade(submission, rubric, context)


class FlakyAuditor(ScriptedAuditor):
    def __init__(self) -> None:
        self.failures_remaining = 1

    async def audit(self, result, standard, context):
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise RuntimeError("auditor crashed mid-stage")
        return await super().audit(result, standard, context)


def build_resumable_runner(
    container: AppContainer, settings: Settings, evaluator, auditor
) -> JobRunner:
    return JobRunner(
        memory_manager=container.memory_manager,
        fetcher=LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir),
        grading_evaluator=evaluator,
        auditor=auditor,
        risk_detector=RiskDetector(),
        sis_connector=LocalSISConnector(data_dir=settings.local_data_dir),
        checkpoint_store=container.checkpoint_store,
        catalog=LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir),
        review_store=LocalReviewStore(data_dir=settings.local_data_dir),
    )


async def test_pipeline_exception_returns_500_and_releases_claim(
    client: httpx.AsyncClient,
    container: AppContainer,
    auth_headers,
    make_event,
    make_push_body,
) -> None:
    runner = RaisingThenCompletingRunner()
    container.job_runner = runner
    event = make_event(job_id="job-retry-raise")
    body = make_push_body(event)
    first = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert first.status_code == 500
    assert container.claimed_jobs == set()
    assert container.in_flight == set()
    second = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["status"] == "completed"
    assert runner.calls == 2


async def test_failed_record_is_not_a_duplicate_and_is_retried(
    client: httpx.AsyncClient,
    container: AppContainer,
    auth_headers,
    make_event,
    make_push_body,
) -> None:
    runner = FailingThenCompletingRunner()
    container.job_runner = runner
    event = make_event(job_id="job-retry-failed-record")
    body = make_push_body(event)
    first = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert first.status_code == 500
    stored = await container.checkpoint_store.get(event.job_id)
    assert stored is not None
    assert stored.stage == JobStage.FAILED
    assert container.claimed_jobs == set()
    second = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert second.status_code == 200
    assert second.json() == {
        "job_id": event.job_id,
        "status": "completed",
        "stage": "completed",
    }
    assert runner.calls == 2


async def test_redelivery_resumes_failed_job_without_recomputing_finished_stages(
    client: httpx.AsyncClient,
    container: AppContainer,
    api_settings: Settings,
    auth_headers,
    make_push_body,
) -> None:
    job_id = "job-retry-resume"
    stage_batch(api_settings, job_id)
    evaluator = CountingEvaluator(
        ConfidenceMapEvaluator({student: 0.95 for student in STUDENTS})
    )
    container.job_runner = build_resumable_runner(
        container, api_settings, evaluator, FlakyAuditor()
    )
    body = make_push_body(make_flow_event(job_id))
    first = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert first.status_code == 500
    assert evaluator.calls == len(STUDENTS)
    stored = await container.checkpoint_store.get(job_id)
    assert stored is not None
    assert stored.stage == JobStage.FAILED
    assert stored.stage_statuses["fetch"] == "succeeded"
    assert stored.stage_statuses["grade"] == "succeeded"
    assert stored.stage_statuses["audit"] == "failed"
    assert container.claimed_jobs == set()
    second = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert second.status_code == 200
    assert second.json() == {
        "job_id": job_id,
        "status": "completed",
        "stage": "completed",
    }
    assert evaluator.calls == len(STUDENTS)
    final = await container.checkpoint_store.get(job_id)
    assert final is not None
    assert final.stage == JobStage.COMPLETED

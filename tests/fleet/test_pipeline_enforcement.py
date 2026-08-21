import json
from pathlib import Path

import pytest

from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.core.fleet import (
    SIS_WRITER_PRINCIPAL,
    build_default_authorizer,
    reset_authorizer_cache,
    set_authorizer,
)
from autocurricula.core.fleet.declarations import TOOL_CAPABILITIES
from autocurricula.core.fleet.roster import GRADING_AGENT_ID
from autocurricula.core.harness import AgentAuthorizer, AgentGrant
from autocurricula.core.harness.capabilities import tool_capability_resolver
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import LocalJobCatalog
from autocurricula.core.orchestration.job_state import JobStage, LocalCheckpointStore
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.review import LocalReviewStore
from autocurricula.core.telemetry import LocalAuditLogger
from autocurricula.schemas.telemetry import ATTR_AGENT_ID, ATTR_AGENT_PRINCIPAL
from autocurricula.tools.gcs_fetcher import LocalStagingFetcher
from autocurricula.tools.sis_connector import LocalSISConnector
from tests.orchestration.verifier_fixtures import ConfidenceMapEvaluator
from tests.review.flow_stack import (
    STUDENTS,
    ScriptedAuditor,
    make_event,
    make_settings,
    stage_batch,
    written_students,
)


@pytest.fixture(autouse=True)
def fresh_authorizer():
    reset_authorizer_cache()
    yield
    reset_authorizer_cache()


def revoke(agent_id: str, capability: str) -> None:
    grants = []
    for grant in build_default_authorizer().grants:
        capabilities = grant.capabilities
        if grant.agent_id == agent_id:
            capabilities = frozenset(capabilities - {capability})
        grants.append(
            AgentGrant(
                agent_id=grant.agent_id,
                principal_id=grant.principal_id,
                capabilities=capabilities,
            )
        )
    resolver = tool_capability_resolver(
        {tool: capability.value for tool, capability in TOOL_CAPABILITIES.items()}
    )
    set_authorizer(AgentAuthorizer(grants, resolver))


def build_runner(settings, memory_manager: MemoryManager) -> JobRunner:
    return JobRunner(
        memory_manager=memory_manager,
        fetcher=LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir),
        grading_evaluator=ConfidenceMapEvaluator(
            {student: 0.95 for student in STUDENTS}
        ),
        auditor=ScriptedAuditor(),
        risk_detector=RiskDetector(),
        sis_connector=LocalSISConnector(data_dir=settings.local_data_dir),
        checkpoint_store=LocalCheckpointStore(data_dir=settings.local_data_dir),
        catalog=LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir),
        review_store=LocalReviewStore(data_dir=settings.local_data_dir),
        audit_logger=LocalAuditLogger(settings.local_data_dir),
    )


def audit_events(settings, job_id: str) -> list[dict]:
    path = settings.local_data_dir / "audit" / f"{job_id}.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def sis_records(settings) -> list[dict]:
    path = settings.local_data_dir / "sis_writes.jsonl"
    if not path.is_file():
        return []
    return [
        record
        for line in path.read_text(encoding="utf-8").splitlines()
        for record in json.loads(line)["request"]["records"]
    ]


async def test_grading_spans_carry_the_agent_principal(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runner = build_runner(settings, MemoryManager.from_settings(settings))
    stage_batch(settings, "job-attribution")

    await runner.process(make_event("job-attribution"))

    spans = audit_events(settings, "job-attribution")[-1]["spans"]
    grading = [span for span in spans if span["name"].startswith("Grading_")]
    assert grading
    assert all(span["attributes"][ATTR_AGENT_ID] == GRADING_AGENT_ID for span in grading)
    assert all(
        span["attributes"][ATTR_AGENT_PRINCIPAL] == f"agent://{GRADING_AGENT_ID}"
        for span in grading
    )


async def test_sis_records_attribute_the_grade_and_the_writer(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runner = build_runner(settings, MemoryManager.from_settings(settings))
    stage_batch(settings, "job-provenance")

    await runner.process(make_event("job-provenance"))

    records = sis_records(settings)
    assert records
    assert all(
        record["provenance"]["agent_id"] == GRADING_AGENT_ID for record in records
    )
    assert all(
        record["provenance"]["writer_principal"] == SIS_WRITER_PRINCIPAL
        for record in records
    )


async def test_revoking_the_sis_capability_blocks_every_write(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runner = build_runner(settings, MemoryManager.from_settings(settings))
    stage_batch(settings, "job-denied-sis")
    revoke(SIS_WRITER_PRINCIPAL, "sis.write")

    record = await runner.process(make_event("job-denied-sis"))

    assert record.stage == JobStage.COMPLETED
    assert written_students(settings) == set()
    denials = audit_events(settings, "job-denied-sis")[-1]["summary"][
        "capability_denials"
    ]
    assert {denial["target"] for denial in denials} == set(STUDENTS)
    assert all(denial["principal_id"] == SIS_WRITER_PRINCIPAL for denial in denials)
    assert all("does not hold capability 'sis.write'" in denial["reasons"][0] for denial in denials)


async def test_revoking_the_grading_capability_isolates_every_submission(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    runner = build_runner(settings, MemoryManager.from_settings(settings))
    stage_batch(settings, "job-denied-llm")
    revoke(GRADING_AGENT_ID, "llm.invoke")

    record = await runner.process(make_event("job-denied-llm"))

    assert record.stage == JobStage.FAILED
    assert "no submissions could be graded" in (record.error or "")
    assert written_students(settings) == set()
    event = audit_events(settings, "job-denied-llm")[-1]
    denials = event["summary"]["capability_denials"]
    assert {denial["agent_id"] for denial in denials} == {GRADING_AGENT_ID}
    assert {denial["target"] for denial in denials} == set(STUDENTS)
    assert any(span["name"] == "CapabilityDenied" for span in event["spans"])

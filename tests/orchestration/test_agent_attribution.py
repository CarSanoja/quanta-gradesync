import json
from pathlib import Path

from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.config.settings import Settings
from autocurricula.core.fleet import (
    ARMOR_SCREENER_ID,
    CURRICULUM_AUDITOR_ID,
    GRADING_AGENT_ID,
    RISK_DETECTOR_ID,
)
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import LocalJobCatalog
from autocurricula.core.orchestration.job_state import LocalCheckpointStore
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.review import LocalReviewStore
from autocurricula.core.telemetry import LocalAuditLogger, LocalLiveSink
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
)

JOB_ID = "job-agent-attribution"

# Every agent that does work on a clean batch. The rest of the fleet is
# deliberately absent: second-opinion, fallback and schema-repair only fire on
# rework, failover or malformed output, and the optimizers only when one is
# wired into the run.
WORKING_AGENTS = frozenset(
    {GRADING_AGENT_ID, ARMOR_SCREENER_ID, CURRICULUM_AUDITOR_ID, RISK_DETECTOR_ID}
)

# The stand-ins only run on an exam the normal path could not finish, so a clean
# batch never wakes them. What must hold is that when they do run, they sign it.
STANDIN_SIGNING = (
    ("fallback evaluator", "FALLBACK_EVALUATOR_ID", "grade_guard.py"),
    ("schema repair", "SCHEMA_REPAIR_ID", "grade_guard.py"),
    ("second opinion", "SECOND_OPINION_ID", "rework_loop.py"),
)


def build_runner(
    settings: Settings, memory_manager: MemoryManager, live_sink: LocalLiveSink
) -> JobRunner:
    return JobRunner(
        memory_manager=memory_manager,
        fetcher=LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir),
        grading_evaluator=ConfidenceMapEvaluator({student: 0.95 for student in STUDENTS}),
        auditor=ScriptedAuditor(),
        risk_detector=RiskDetector(),
        sis_connector=LocalSISConnector(data_dir=settings.local_data_dir),
        checkpoint_store=LocalCheckpointStore(data_dir=settings.local_data_dir),
        catalog=LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir),
        review_store=LocalReviewStore(data_dir=settings.local_data_dir),
        audit_logger=LocalAuditLogger(settings.local_data_dir),
        live_sink=live_sink,
    )


def spans_of(settings: Settings, job_id: str) -> list[dict]:
    path = settings.local_data_dir / "audit" / f"{job_id}.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return events[-1]["spans"]


def attributed(spans: list[dict]) -> dict[str, list[dict]]:
    by_agent: dict[str, list[dict]] = {}
    for span in spans:
        agent = span.get("attributes", {}).get(ATTR_AGENT_ID)
        if agent:
            by_agent.setdefault(agent, []).append(span)
    return by_agent


async def run_one_batch(tmp_path: Path) -> tuple[Settings, list[dict]]:
    settings = make_settings(tmp_path)
    live_sink = LocalLiveSink(settings.local_data_dir)
    runner = build_runner(settings, MemoryManager.from_settings(settings), live_sink)
    stage_batch(settings, JOB_ID)
    await runner.process(make_event(JOB_ID))
    live_sink.flush()
    return settings, spans_of(settings, JOB_ID)


async def test_every_agent_that_works_on_a_batch_signs_its_own_spans(tmp_path: Path) -> None:
    """Mission control attributes an event only when the span carries agent.id.

    Until 2026-08-28 only the grading agent, the armor screener and the evidence
    transcriber called annotate_span, so the curriculum auditor and the risk
    detector ran on every batch with their cards dark on the live board.
    """
    _, spans = await run_one_batch(tmp_path)

    assert WORKING_AGENTS <= set(attributed(spans))


async def test_the_auditor_and_the_risk_detector_sign_one_span_per_unit_of_work(
    tmp_path: Path,
) -> None:
    _, spans = await run_one_batch(tmp_path)
    by_agent = attributed(spans)

    audits = by_agent[CURRICULUM_AUDITOR_ID]
    risks = by_agent[RISK_DETECTOR_ID]

    assert {span["name"] for span in audits} == {f"Audit_{student}" for student in STUDENTS}
    assert {span["name"] for span in risks} == {f"Risk_{student}" for student in STUDENTS}
    assert all(span["stage"] == "AUDIT" for span in audits)
    assert all(span["stage"] == "RISK" for span in risks)


async def test_both_new_agents_land_in_the_per_student_reasoning_chain(
    tmp_path: Path,
) -> None:
    """The chain view groups by student, so the span has to name one."""
    settings, _ = await run_one_batch(tmp_path)
    path = settings.local_data_dir / "live" / f"{JOB_ID}.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    for agent_id in (CURRICULUM_AUDITOR_ID, RISK_DETECTOR_ID):
        students = {
            event["student_id"]
            for event in events
            if event.get("agent_id") == agent_id and event.get("student_id")
        }
        assert students == set(STUDENTS), agent_id


async def test_a_signed_span_carries_the_principal_the_agent_acts_as(tmp_path: Path) -> None:
    _, spans = await run_one_batch(tmp_path)
    by_agent = attributed(spans)

    for agent_id in (CURRICULUM_AUDITOR_ID, RISK_DETECTOR_ID):
        for span in by_agent[agent_id]:
            assert span["attributes"][ATTR_AGENT_PRINCIPAL] == f"agent://{agent_id}"


async def test_the_live_feed_carries_the_new_agents_to_the_board(tmp_path: Path) -> None:
    """The board drops any event without agent_id, so the feed must carry it."""
    settings, _ = await run_one_batch(tmp_path)
    path = settings.local_data_dir / "live" / f"{JOB_ID}.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    agents = {event.get("agent_id") for event in events if event.get("agent_id")}

    assert CURRICULUM_AUDITOR_ID in agents
    assert RISK_DETECTOR_ID in agents


def test_the_stand_in_agents_sign_their_work_too() -> None:
    """Each of these graded or repaired an exam with its card dark on the board.

    The fallback took two exams on 2026-08-28 — 472s and 299s, two model calls
    each — and the live feed attributed none of it.
    """
    root = Path("src/autocurricula/core/orchestration")
    for label, constant, filename in STANDIN_SIGNING:
        body = (root / filename).read_text(encoding="utf-8")
        assert constant in body, label
        assert "annotate_span" in body or "agent_span(" in body, label


def test_the_fallback_is_recorded_per_exam_not_per_batch() -> None:
    body = (Path("src/autocurricula/core/orchestration") / "grade_guard.py").read_text(
        encoding="utf-8"
    )

    assert 'f"Fallback_{submission.submission_id}"' in body
    assert 'f"SchemaRepair_{submission.submission_id}"' in body
    assert 'last_used_fallback' in body
    assert 'last_attempts' in body

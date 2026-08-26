import asyncio
import json
from pathlib import Path

from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.config.settings import Settings
from autocurricula.core.fleet import EVIDENCE_TRANSCRIBER_ID
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import LocalJobCatalog
from autocurricula.core.orchestration.job_state import LocalCheckpointStore
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.orchestration.transcription_stage import (
    ATTR_TRANSCRIPTION_PAGES,
    TRANSCRIPTION_SPAN_PREFIX,
)
from autocurricula.core.review import LocalReviewStore
from autocurricula.core.telemetry import LocalAuditLogger
from autocurricula.schemas.exam import ExamSubmission
from autocurricula.schemas.telemetry import (
    ATTR_AGENT_ID,
    ATTR_AGENT_PRINCIPAL,
    ATTR_GEN_AI_CALLS,
    ATTR_GEN_AI_SYSTEM,
    VERIFICATION_FAILED,
    VERIFICATION_VERIFIED,
)
from autocurricula.tools.gcs_fetcher import LocalStagingFetcher
from autocurricula.tools.sis_connector import LocalSISConnector
from tests.orchestration.verifier_fixtures import ConfidenceMapEvaluator
from tests.review.flow_stack import (
    BUCKET,
    PREFIX,
    STUDENTS,
    ScriptedAuditor,
    make_event,
    make_settings,
    stage_batch,
    written_students,
)

TRANSCRIBER_MODEL = "fake-gemini-flash-lite"


def faithful_pages() -> dict[str, str]:
    return {
        student: (
            f"Exam page. The visible answer of {student[:-1]}l is written "
            "here in ink."
        )
        for student in STUDENTS
    }


class FakeTranscriber:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = dict(pages)
        self.model = TRANSCRIBER_MODEL
        self.seen: list[str] = []

    async def transcribe_submission(
        self, submission: ExamSubmission
    ) -> dict[tuple[str, int], str]:
        await asyncio.sleep(0)
        self.seen.append(submission.submission_id)
        text = self._pages.get(submission.submission_id)
        if text is None:
            return {}
        return {(submission.submission_id, 1): text}


class ExplodingTranscriber(FakeTranscriber):
    async def transcribe_submission(
        self, submission: ExamSubmission
    ) -> dict[tuple[str, int], str]:
        await asyncio.sleep(0)
        self.seen.append(submission.submission_id)
        raise RuntimeError("vertex unreachable")


def build_runner(
    settings: Settings, memory_manager: MemoryManager, transcriber
) -> tuple[JobRunner, LocalReviewStore]:
    review_store = LocalReviewStore(data_dir=settings.local_data_dir)
    runner = JobRunner(
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
        review_store=review_store,
        audit_logger=LocalAuditLogger(settings.local_data_dir),
        transcriber=transcriber,
        match_threshold=settings.faithfulness_match_threshold,
    )
    return runner, review_store


def spans_of(settings: Settings, job_id: str) -> list[dict]:
    path = settings.local_data_dir / "audit" / f"{job_id}.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return events[-1]["spans"]


def transcription_spans(settings: Settings, job_id: str) -> list[dict]:
    return [
        span
        for span in spans_of(settings, job_id)
        if span["name"].startswith(TRANSCRIPTION_SPAN_PREFIX)
    ]


def faithfulness_by_student(settings: Settings) -> dict[str, bool]:
    path = settings.local_data_dir / "sis_writes.jsonl"
    if not path.is_file():
        return {}
    return {
        record["student_id"]: record["provenance"]["faithfulness_checked"]
        for line in path.read_text(encoding="utf-8").splitlines()
        for record in json.loads(line)["request"]["records"]
    }


def verification_statuses(settings: Settings, job_id: str) -> list[str]:
    return [
        span["attributes"]["evidence.span_verification"]
        for span in spans_of(settings, job_id)
        if span["name"] == "FaithfulnessVerification"
    ]


async def test_a_transcript_carrying_the_quote_verifies_the_evidence(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    transcriber = FakeTranscriber(faithful_pages())
    runner, _ = build_runner(settings, MemoryManager.from_settings(settings), transcriber)
    stage_batch(settings, "job-transcribed")

    await runner.process(make_event("job-transcribed"))

    assert sorted(transcriber.seen) == sorted(STUDENTS)
    assert verification_statuses(settings, "job-transcribed") == [
        VERIFICATION_VERIFIED
    ] * len(STUDENTS)
    assert written_students(settings) == set(STUDENTS)
    assert all(faithfulness_by_student(settings).values())


async def test_a_contradicting_transcript_quarantines_the_submission(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    pages = dict.fromkeys(STUDENTS, "a page about the water cycle and evaporation")
    runner, review_store = build_runner(
        settings, MemoryManager.from_settings(settings), FakeTranscriber(pages)
    )
    stage_batch(settings, "job-contradicted")

    await runner.process(make_event("job-contradicted"))

    assert verification_statuses(settings, "job-contradicted") == [
        VERIFICATION_FAILED
    ] * len(STUDENTS)
    assert written_students(settings) == set()
    pending = await review_store.list_pending()
    assert {item.student_id for item in pending} == set(STUDENTS)


async def test_a_sidecar_overrides_a_contradicting_transcript(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    pages = dict.fromkeys(STUDENTS, "a page about the water cycle and evaporation")
    runner, _ = build_runner(
        settings, MemoryManager.from_settings(settings), FakeTranscriber(pages)
    )
    stage_batch(settings, "job-sidecar-wins")
    root = settings.gcs_local_staging_dir / BUCKET / PREFIX
    for student in STUDENTS:
        (root / f"{student}.txt").write_text(
            f"visible answer of {student}", encoding="utf-8"
        )

    await runner.process(make_event("job-sidecar-wins"))

    assert verification_statuses(settings, "job-sidecar-wins") == [
        VERIFICATION_VERIFIED
    ] * len(STUDENTS)
    assert written_students(settings) == set(STUDENTS)


async def test_transcription_spans_are_attributed_to_the_transcriber(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    runner, _ = build_runner(
        settings, MemoryManager.from_settings(settings), FakeTranscriber(faithful_pages())
    )
    stage_batch(settings, "job-transcription-spans")

    await runner.process(make_event("job-transcription-spans"))

    spans = transcription_spans(settings, "job-transcription-spans")
    assert {span["name"] for span in spans} == {
        f"{TRANSCRIPTION_SPAN_PREFIX}{student}" for student in STUDENTS
    }
    assert all(span["stage"] == "GRADE" for span in spans)
    for span in spans:
        attributes = span["attributes"]
        assert attributes[ATTR_AGENT_ID] == EVIDENCE_TRANSCRIBER_ID
        assert attributes[ATTR_AGENT_PRINCIPAL] == f"agent://{EVIDENCE_TRANSCRIBER_ID}"
        assert attributes[ATTR_GEN_AI_SYSTEM] == "google_gemini"
        assert attributes["gen_ai.model"] == TRANSCRIBER_MODEL
        assert attributes[ATTR_TRANSCRIPTION_PAGES] == 1
        assert attributes[ATTR_GEN_AI_CALLS] == 0


async def test_a_failing_transcriber_never_fails_the_grade_stage(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    runner, _ = build_runner(
        settings, MemoryManager.from_settings(settings), ExplodingTranscriber({})
    )
    stage_batch(settings, "job-transcription-down")

    record = await runner.process(make_event("job-transcription-down"))

    assert record.error is None
    assert written_students(settings) == set(STUDENTS)
    spans = transcription_spans(settings, "job-transcription-down")
    assert all(span["attributes"][ATTR_TRANSCRIPTION_PAGES] == 0 for span in spans)
    assert faithfulness_by_student(settings) == dict.fromkeys(STUDENTS, False)

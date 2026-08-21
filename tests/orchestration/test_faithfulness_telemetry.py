from pathlib import Path

from autocurricula.core.armor import wiring
from autocurricula.core.harness import SidecarTextProvider
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.grade_guard import GradeGuard
from autocurricula.core.telemetry import Recorder
from autocurricula.schemas.exam import ExamFile, ExamSubmission
from autocurricula.schemas.telemetry import (
    ATTR_EVIDENCE_SPAN_MATCH,
    ATTR_EVIDENCE_SPAN_VERIFICATION,
    VERIFICATION_FAILED,
    VERIFICATION_UNCHECKED,
    VERIFICATION_VERIFIED,
)
from tests.orchestration.incident_fixtures import synced_records
from tests.orchestration.verifier_fixtures import ConfidenceMapEvaluator
from tests.review.flow_stack import (
    BUCKET,
    PREFIX,
    build_stack,
    make_event,
    make_rubric,
    make_settings,
    stage_batch,
)

STUDENT = "stu-001"
QUOTE = f"visible answer of {STUDENT}"


def make_submission() -> ExamSubmission:
    return ExamSubmission(
        submission_id=STUDENT,
        student_id=STUDENT,
        files=[
            ExamFile(
                gcs_uri=f"gs://{BUCKET}/{PREFIX}/{STUDENT}.jpg",
                mime_type="image/jpeg",
                page_count=1,
            )
        ],
    )


def build_guard(texts: dict[tuple[str, int], str]) -> tuple[GradeGuard, Recorder]:
    recorder = Recorder("trace-faith-1")
    guard = GradeGuard(
        job_id="job-faith",
        evaluator=ConfidenceMapEvaluator({STUDENT: 0.95}),
        fallback=None,
        latency_seconds=90.0,
        confidence_factor=0.9,
        repair_agent=None,
        dead_letter=None,
        dead_letter_max_attempts=3,
        model_id="scripted",
        recorder=recorder,
        provider=SidecarTextProvider(texts),
        armor=None,
    )
    return guard, recorder


def faith_span(recorder: Recorder):
    return next(
        span for span in recorder.spans if span.name == "FaithfulnessVerification"
    )


async def test_missing_transcript_reports_unchecked_without_zeroing_confidence() -> None:
    guard, recorder = build_guard({})

    outcome = await guard.grade(make_submission(), make_rubric(), None)

    span = faith_span(recorder)
    assert span.attributes[ATTR_EVIDENCE_SPAN_VERIFICATION] == VERIFICATION_UNCHECKED
    assert ATTR_EVIDENCE_SPAN_MATCH not in span.attributes
    assert outcome.result is not None
    assert outcome.result.criterion_scores[0].confidence == 0.95
    assert guard.faithfulness_status[STUDENT] == VERIFICATION_UNCHECKED


async def test_fabricated_quote_still_zeroes_confidence() -> None:
    guard, recorder = build_guard({(STUDENT, 1): "an entirely different transcript"})

    outcome = await guard.grade(make_submission(), make_rubric(), None)

    span = faith_span(recorder)
    assert span.attributes[ATTR_EVIDENCE_SPAN_VERIFICATION] == VERIFICATION_FAILED
    assert span.attributes[ATTR_EVIDENCE_SPAN_MATCH] is False
    assert outcome.result is not None
    assert outcome.result.criterion_scores[0].confidence == 0.0
    assert "faithfulness" in outcome.result.criterion_scores[0].comment


async def test_matching_quote_reports_verified() -> None:
    guard, recorder = build_guard({(STUDENT, 1): f"the page reads {QUOTE} clearly"})

    outcome = await guard.grade(make_submission(), make_rubric(), None)

    span = faith_span(recorder)
    assert span.attributes[ATTR_EVIDENCE_SPAN_VERIFICATION] == VERIFICATION_VERIFIED
    assert span.attributes[ATTR_EVIDENCE_SPAN_MATCH] is True
    assert outcome.result is not None
    assert outcome.result.criterion_scores[0].confidence == 0.95


async def test_sis_records_declare_whether_faithfulness_ran(
    tmp_path: Path, monkeypatch
) -> None:
    settings = make_settings(tmp_path)
    monkeypatch.setattr(wiring, "get_settings", lambda: settings)
    memory_manager = MemoryManager.from_settings(settings)
    runner, _, _ = build_stack(settings, memory_manager)
    stage_batch(settings, "job-faith-flow")

    await runner.process(make_event("job-faith-flow"))

    provenance = {
        record["student_id"]: record["provenance"]
        for record in synced_records(settings)
    }
    assert provenance
    assert all(
        entry["faithfulness_checked"] is False for entry in provenance.values()
    )


async def test_sis_records_declare_a_checked_transcript(
    tmp_path: Path, monkeypatch
) -> None:
    settings = make_settings(tmp_path)
    monkeypatch.setattr(wiring, "get_settings", lambda: settings)
    memory_manager = MemoryManager.from_settings(settings)
    runner, _, _ = build_stack(settings, memory_manager)
    stage_batch(settings, "job-faith-sidecar")
    root = settings.gcs_local_staging_dir / BUCKET / PREFIX
    (root / f"{STUDENT}.txt").write_text(QUOTE, encoding="utf-8")

    await runner.process(make_event("job-faith-sidecar"))

    provenance = {
        record["student_id"]: record["provenance"]
        for record in synced_records(settings)
    }
    assert provenance[STUDENT]["faithfulness_checked"] is True
    assert provenance["stu-003"]["faithfulness_checked"] is False

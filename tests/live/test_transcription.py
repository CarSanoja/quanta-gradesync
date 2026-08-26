from pathlib import Path

import pytest

from autocurricula.config.settings import Settings
from autocurricula.core.harness.faithfulness import normalize_text, span_status
from autocurricula.core.harness.transcription import LlmPageTranscriber
from autocurricula.schemas.exam import ExamFile, ExamSubmission
from autocurricula.schemas.telemetry import VERIFICATION_FAILED, VERIFICATION_VERIFIED
from tests.live.guard import live_only

pytestmark = [pytest.mark.live, live_only]

SAMPLE_BATCH = (
    Path(__file__).resolve().parents[2]
    / ".local_data"
    / "sample_batch"
    / "batches"
    / "2026_Matematicas_10A_Parcial1"
)

STUDENT_ID = "ana-torres"
PRINTED_HEADER = "Northside Secondary School"
HANDWRITTEN_ANSWER = "x^2 + 5x + 6 = (x + 2)(x + 3)"
FABRICATED_QUOTE = "the student proved the Pythagorean theorem with a diagram"


def sample_submission(student_id: str) -> ExamSubmission:
    path = SAMPLE_BATCH / f"{student_id}.jpg"
    if not path.is_file():
        pytest.skip(
            "sample batch missing; regenerate with scripts/generate_sample_batch.py "
            "--target .local_data/sample_batch --seed 20260819"
        )
    return ExamSubmission(
        submission_id=student_id,
        student_id=student_id,
        files=[
            ExamFile(
                gcs_uri=f"gs://live-transcription-fixtures/{student_id}.jpg",
                local_path=str(path),
                mime_type="image/jpeg",
                page_count=1,
            )
        ],
    )


async def transcribe(settings: Settings, student_id: str) -> str:
    transcriber = LlmPageTranscriber(settings)
    texts = await transcriber.transcribe_submission(sample_submission(student_id))
    transcript = texts.get((student_id, 1))
    assert transcript, "the transcriber returned no text for the sample page"
    return transcript


async def test_the_page_transcript_carries_what_was_drawn_on_it(
    live_settings: Settings,
) -> None:
    transcript = await transcribe(live_settings, STUDENT_ID)

    assert normalize_text(PRINTED_HEADER) in normalize_text(transcript)
    assert span_status(
        HANDWRITTEN_ANSWER,
        transcript,
        match_threshold=live_settings.faithfulness_match_threshold,
    ) == VERIFICATION_VERIFIED


async def test_a_quote_that_was_never_written_stays_unverified(
    live_settings: Settings,
) -> None:
    transcript = await transcribe(live_settings, STUDENT_ID)

    assert span_status(
        FABRICATED_QUOTE,
        transcript,
        match_threshold=live_settings.faithfulness_match_threshold,
    ) == VERIFICATION_FAILED

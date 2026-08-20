from pathlib import Path

import pytest

from autocurricula.config.settings import Settings
from autocurricula.core.armor.llm import LlmInjectionDetector
from autocurricula.schemas.armor import ArmorSeverity
from autocurricula.schemas.exam import ExamFile, ExamSubmission
from tests.live.guard import live_only

pytestmark = [pytest.mark.live, live_only]

SAMPLE_BATCH = (
    Path(__file__).resolve().parents[2]
    / ".local_data"
    / "sample_batch"
    / "batches"
    / "2026_Matematicas_10A_Parcial1"
)


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
                gcs_uri=f"gs://live-armor-fixtures/{student_id}.jpg",
                local_path=str(path),
                mime_type="image/jpeg",
                page_count=1,
            )
        ],
    )


async def test_handwritten_injection_is_detected(live_settings: Settings) -> None:
    detector = LlmInjectionDetector(live_settings)
    verdict = await detector.screen(sample_submission("julian-pardo"))
    assert verdict.injection_detected is True
    assert verdict.quoted_text.strip()
    assert verdict.severity != ArmorSeverity.NONE
    assert verdict.rationale.strip()


async def test_clean_exam_page_is_not_flagged(live_settings: Settings) -> None:
    detector = LlmInjectionDetector(live_settings)
    verdict = await detector.screen(sample_submission("ana-torres"))
    assert verdict.injection_detected is False

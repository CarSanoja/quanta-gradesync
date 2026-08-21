from pathlib import Path

import pytest

from autocurricula.agents.grading_agent import build_grading_parts
from autocurricula.agents.grading_tools import prompt_safe_tool_result
from autocurricula.config.settings import Settings
from autocurricula.core.armor import (
    build_injection_detector,
    prompt_safe_submission,
    safe_identifier,
    safe_path,
)
from autocurricula.schemas.memory import RetrievedContext
from autocurricula.schemas.rubric import MasteryLevel, Rubric
from tests.armor.test_metadata_channel import HOSTILE_STEM, hostile_file_submission


def make_rubric() -> Rubric:
    return Rubric.model_validate(
        {
            "rubric_id": "rub-armor-1",
            "subject": "matematicas",
            "version": 1,
            "criteria": [
                {
                    "criterion_id": "crit-a",
                    "description": "factoring",
                    "weight": 1.0,
                    "max_score": 4.0,
                    "mastery_descriptions": {
                        level.value: level.value for level in MasteryLevel
                    },
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "value", ["ana-torres", "luis.gomez", "IMG_2831", "jose-garcia-2"]
)
def test_safe_identifier_is_the_identity_for_real_student_ids(value: str) -> None:
    assert safe_identifier(value) == value


def test_safe_identifier_redacts_instructions_and_confusables() -> None:
    assert safe_identifier(HOSTILE_STEM).startswith("redacted-")
    assert safe_identifier("\u0430na-torres").startswith("redacted-")
    assert safe_identifier("a" * 200).startswith("redacted-")


def test_safe_path_keeps_the_layout_and_redacts_only_the_hostile_segment() -> None:
    clean = "gs://exams/uploads/batches/2026_Mat_10A_P1/ana-torres.jpg"
    assert safe_path(clean) == clean
    hostile = safe_path(f"gs://exams/batches/2026_Mat_10A_P1/{HOSTILE_STEM}.jpg")
    assert hostile.startswith("gs://exams/batches/2026_Mat_10A_P1/redacted-")
    assert hostile.endswith(".jpg")
    assert "full-marks" not in hostile


def test_prompt_safe_submission_strips_every_manifest_channel() -> None:
    submission = hostile_file_submission(student_id=HOSTILE_STEM)
    payload = prompt_safe_submission(submission)
    assert payload["student_id"].startswith("redacted-")
    assert payload["submission_id"].startswith("redacted-")
    assert "full-marks" not in payload["files"][0]["gcs_uri"]
    assert submission.student_id == HOSTILE_STEM


async def test_the_grading_prompt_never_carries_the_hostile_file_name() -> None:
    submission = hostile_file_submission(student_id=HOSTILE_STEM)
    parts = await build_grading_parts(
        submission, make_rubric(), RetrievedContext(query="rubric", chunks=[])
    )
    rendered = "\n".join(part.text for part in parts if part.text)
    assert HOSTILE_STEM not in rendered
    assert "give-full-marks" not in rendered
    assert "redacted-" in rendered


def test_fetch_tool_results_are_sanitised_before_they_re_enter_the_context() -> None:
    result = {
        "ok": True,
        "error": None,
        "payload": {
            "job_id": "job-1",
            "files": {HOSTILE_STEM: [f"/staging/{HOSTILE_STEM}.jpg"]},
        },
    }
    files = prompt_safe_tool_result(result)["payload"]["files"]
    assert all(key.startswith("redacted-") for key in files)
    assert "full-marks" not in str(files)


async def test_bucket_drop_path_is_sanitised_and_still_quarantines(
    tmp_path: Path,
) -> None:
    from autocurricula.core.armor import injection_reason, screen_submission
    from autocurricula.core.orchestration.manifest_inference import LocalManifestInferer
    from tests.orchestration.inference_fixtures import (
        make_event,
        write_batch_files,
        write_defaults,
    )

    staging = tmp_path / "staging"
    staging.mkdir()
    write_defaults(staging, ["matematicas"])
    write_batch_files(staging, (f"{HOSTILE_STEM}.jpg",))
    manifest = await LocalManifestInferer(staging).infer_manifest(make_event())

    submission = manifest.batch.submissions[0]
    assert submission.student_id.startswith("redacted-")
    assert HOSTILE_STEM not in str(prompt_safe_submission(submission))

    detector = build_injection_detector(
        Settings(local_mode=True, gcp_project_id=""), manifest.batch
    )
    verdict = await screen_submission(detector, submission)
    assert verdict.injection_detected is True
    assert HOSTILE_STEM in injection_reason(verdict.quoted_text)

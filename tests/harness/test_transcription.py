import json
from pathlib import Path
from typing import Any

import pytest

from autocurricula.config.settings import Settings
from autocurricula.core.harness.transcription import (
    LlmPageTranscriber,
    PageTranscript,
    build_page_transcriber,
)
from autocurricula.schemas.exam import ExamFile, ExamSubmission

SUBMISSION_ID = "stu-transcribe-1"


class _Session:
    id = "session-transcribe-1"


class _SessionService:
    async def create_session(self, *, app_name: str, user_id: str) -> _Session:
        return _Session()


class _Part:
    def __init__(self, text: str) -> None:
        self.text = text


class _Content:
    def __init__(self, text: str) -> None:
        self.parts = [_Part(text)]


class _Event:
    def __init__(self, text: str) -> None:
        self.content = _Content(text)


class _Runner:
    def __init__(self, replies: list[str | Exception]) -> None:
        self.replies = list(replies)
        self.calls = 0

    async def run_async(self, *, user_id: str, session_id: str, new_message: Any):
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else "{}"
        if isinstance(reply, Exception):
            raise reply
        yield _Event(reply)


def transcript_reply(text: str) -> str:
    return json.dumps({"transcript": text})


def build_transcriber(
    settings: Settings, replies: list[str | Exception]
) -> tuple[LlmPageTranscriber, _Runner]:
    runner = _Runner(replies)
    transcriber = LlmPageTranscriber(
        settings,
        runner_factory=lambda agent, service: runner,
        session_service=_SessionService(),
    )
    return transcriber, runner


def make_page(directory: Path, name: str) -> Path:
    page = directory / name
    page.write_bytes(b"scanned-page-bytes")
    return page


def make_submission(paths: list[Path], page_count: int = 1) -> ExamSubmission:
    return ExamSubmission(
        submission_id=SUBMISSION_ID,
        student_id=SUBMISSION_ID,
        files=[
            ExamFile(
                gcs_uri=f"gs://exams/{path.name}",
                local_path=str(path),
                mime_type="image/jpeg",
                page_count=page_count,
            )
            for path in paths
        ],
    )


def gcp_settings() -> Settings:
    return Settings(local_mode=False, gcp_project_id="transcription-test")


async def test_transcribes_every_staged_page_of_the_submission(
    settings: Settings, tmp_path: Path
) -> None:
    page = make_page(tmp_path, "page-1.jpg")
    transcriber, runner = build_transcriber(
        settings, [transcript_reply("x^2 + 5x + 6 = (x + 2)(x + 3)")]
    )

    texts = await transcriber.transcribe_submission(make_submission([page], 2))

    assert runner.calls == 1
    assert texts[(SUBMISSION_ID, 1)] == "x^2 + 5x + 6 = (x + 2)(x + 3)"
    assert texts[(SUBMISSION_ID, 2)] == texts[(SUBMISSION_ID, 1)]


async def test_one_call_per_staged_file(settings: Settings, tmp_path: Path) -> None:
    pages = [make_page(tmp_path, "page-1.jpg"), make_page(tmp_path, "page-2.jpg")]
    transcriber, runner = build_transcriber(
        settings, [transcript_reply("first page"), transcript_reply("second page")]
    )

    texts = await transcriber.transcribe_submission(make_submission(pages))

    assert runner.calls == 2
    assert texts[(SUBMISSION_ID, 1)] == "second page"


async def test_unstaged_file_yields_no_entry(settings: Settings) -> None:
    transcriber, runner = build_transcriber(settings, [])
    submission = ExamSubmission(
        submission_id=SUBMISSION_ID,
        student_id=SUBMISSION_ID,
        files=[
            ExamFile(
                gcs_uri="gs://exams/never-staged.jpg",
                mime_type="image/jpeg",
                page_count=1,
            )
        ],
    )

    assert await transcriber.transcribe_submission(submission) == {}
    assert runner.calls == 0


async def test_missing_local_file_yields_no_entry(
    settings: Settings, tmp_path: Path
) -> None:
    transcriber, runner = build_transcriber(settings, [])
    submission = make_submission([tmp_path / "absent.jpg"])

    assert await transcriber.transcribe_submission(submission) == {}
    assert runner.calls == 0


async def test_a_failing_page_never_fails_the_submission(
    settings: Settings, tmp_path: Path
) -> None:
    pages = [make_page(tmp_path, "page-1.jpg"), make_page(tmp_path, "page-2.jpg")]
    transcriber, _ = build_transcriber(
        settings,
        [RuntimeError("model unavailable"), transcript_reply("page two survived")],
    )

    texts = await transcriber.transcribe_submission(make_submission(pages))

    assert texts == {(SUBMISSION_ID, 1): "page two survived"}


async def test_malformed_output_is_swallowed(
    settings: Settings, tmp_path: Path
) -> None:
    page = make_page(tmp_path, "page-1.jpg")
    transcriber, _ = build_transcriber(settings, ["not json at all", "still not json"])

    assert await transcriber.transcribe_submission(make_submission([page])) == {}


async def test_blank_transcript_yields_no_entry(
    settings: Settings, tmp_path: Path
) -> None:
    page = make_page(tmp_path, "page-1.jpg")
    transcriber, _ = build_transcriber(settings, [transcript_reply("   ")])

    assert await transcriber.transcribe_submission(make_submission([page])) == {}


def test_page_transcript_requires_the_transcript_field() -> None:
    with pytest.raises(ValueError):
        PageTranscript.model_validate({})


def test_transcriber_is_not_built_in_local_mode(settings: Settings) -> None:
    assert build_page_transcriber(settings) is None


def test_transcriber_is_not_built_when_transcription_is_disabled() -> None:
    disabled = Settings(
        local_mode=False,
        gcp_project_id="transcription-test",
        faithfulness_transcription_enabled=False,
    )

    assert build_page_transcriber(disabled) is None


def test_transcriber_uses_the_flash_model() -> None:
    resolved = gcp_settings()
    transcriber = build_page_transcriber(resolved)

    assert transcriber is not None
    assert transcriber.model == resolved.gemini_flash_model

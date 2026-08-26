import logging
from collections.abc import Callable
from typing import Any

from autocurricula.agents.adk_llm import build_structured_agent
from autocurricula.agents.base import (
    AgentResponseError,
    inline_file_part,
    make_user_content,
    resolve_model,
    run_agent_for_text,
    structured_output_with_retry,
    text_part,
)
from autocurricula.config.settings import Settings
from autocurricula.schemas.common import FrozenStrictModel
from autocurricula.schemas.exam import ExamFile, ExamSubmission

logger = logging.getLogger(__name__)

TRANSCRIBER_AGENT_NAME = "evidence_page_transcriber"
TRANSCRIBER_APP_NAME = "gradesync_transcription"
TRANSCRIBER_USER_ID = "gradesync_transcription"
MAX_INLINE_FILE_BYTES = 18 * 1024 * 1024

TRANSCRIPTION_INSTRUCTION = (
    "You are the page transcriber of an automated exam grading system. "
    "Return a VERBATIM transcription of everything written on the attached "
    "scanned exam page: printed question text, the student's handwriting, "
    "formulas, numbers, units and labels. Preserve the reading order and the "
    "line breaks of the page, one written line per output line. Transcribe "
    "words you are unsure about as your best guess rather than dropping them, "
    "and transcribe mathematics exactly as it is written. Never correct a "
    "spelling mistake, never fix wrong arithmetic, never translate into "
    "another language, and never add commentary, grades or explanations of "
    "your own. Return only a JSON object with the key transcript holding the "
    "transcription as a single string."
)

RunnerFactory = Callable[[Any, Any], Any]


class PageTranscript(FrozenStrictModel):
    transcript: str


class PageTranscriptionError(AgentResponseError):
    pass


def _error(message: str, raw: str, cause: Exception) -> PageTranscriptionError:
    return PageTranscriptionError(message, raw=raw, cause=cause)


def _default_session_service() -> Any:
    from google.adk.sessions import InMemorySessionService

    return InMemorySessionService()


def _default_runner_factory(agent: Any, session_service: Any) -> Any:
    from google.adk.runners import Runner

    return Runner(
        agent=agent,
        app_name=TRANSCRIBER_APP_NAME,
        session_service=session_service,
    )


class LlmPageTranscriber:
    def __init__(
        self,
        settings: Settings,
        *,
        runner_factory: RunnerFactory | None = None,
        session_service: Any | None = None,
        max_inline_bytes: int = MAX_INLINE_FILE_BYTES,
    ) -> None:
        self._model = resolve_model(settings, "gemini_flash_model")
        self._max_inline_bytes = max_inline_bytes
        self._session_service = (
            session_service if session_service is not None else _default_session_service()
        )
        self._runner_factory = (
            runner_factory if runner_factory is not None else _default_runner_factory
        )
        self._agent = build_structured_agent(
            name=TRANSCRIBER_AGENT_NAME,
            model=self._model,
            instruction=TRANSCRIPTION_INSTRUCTION,
            output_schema=PageTranscript,
            temperature=0.0,
        )

    @property
    def model(self) -> str:
        return self._model

    async def transcribe_submission(
        self, submission: ExamSubmission
    ) -> dict[tuple[str, int], str]:
        texts: dict[tuple[str, int], str] = {}
        for exam_file in submission.files:
            try:
                transcript = await self._transcribe_file(submission, exam_file)
            except Exception as error:
                logger.warning(
                    "page transcription failed for submission %s file %s: %s",
                    submission.submission_id,
                    exam_file.gcs_uri,
                    error,
                )
                continue
            if transcript is None:
                continue
            for page in range(1, max(1, exam_file.page_count) + 1):
                texts[(submission.submission_id, page)] = transcript
        return texts

    async def _transcribe_file(
        self, submission: ExamSubmission, exam_file: ExamFile
    ) -> str | None:
        if exam_file.local_path is None:
            return None
        part = await inline_file_part(
            exam_file.local_path, exam_file.mime_type, max_bytes=self._max_inline_bytes
        )
        if part is None:
            return None
        session = await self._session_service.create_session(
            app_name=TRANSCRIBER_APP_NAME, user_id=TRANSCRIBER_USER_ID
        )
        runner = self._runner_factory(self._agent, self._session_service)
        parts = [
            text_part(
                "Transcribe the attached scanned exam page of submission "
                f"{submission.submission_id} verbatim."
            ),
            part,
        ]

        async def call(repair: str | None) -> str:
            message_parts = list(parts)
            if repair is not None:
                message_parts.append(text_part(repair))
            message = make_user_content(message_parts)
            return await run_agent_for_text(
                runner, TRANSCRIBER_USER_ID, session.id, message
            )

        page = await structured_output_with_retry(call, PageTranscript, _error)
        return page.transcript.strip() or None


def build_page_transcriber(settings: Settings) -> LlmPageTranscriber | None:
    if settings.local_mode or not settings.faithfulness_transcription_enabled:
        return None
    return LlmPageTranscriber(settings)

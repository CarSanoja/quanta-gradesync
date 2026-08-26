
import logging
from typing import Any, Protocol, runtime_checkable

from autocurricula.core.fleet import (
    EVIDENCE_TRANSCRIBER_ID,
    annotate_span,
    authorize_llm,
)
from autocurricula.core.orchestration.concurrency import (
    DEFAULT_MODEL_CONCURRENCY,
    gather_limited,
)
from autocurricula.core.telemetry import Recorder, usage_scope
from autocurricula.schemas.exam import ExamBatch, ExamSubmission
from autocurricula.schemas.telemetry import (
    ATTR_GEN_AI_CALLS,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_USAGE_INPUT_TOKENS,
    ATTR_GEN_AI_USAGE_OUTPUT_TOKENS,
    ATTR_GEN_AI_USAGE_TOKENS,
)

logger = logging.getLogger(__name__)

ATTR_TRANSCRIPTION_PAGES = "transcription.pages"
TRANSCRIPTION_SPAN_PREFIX = "EvidenceTranscription_"


@runtime_checkable
class PageTranscriber(Protocol):
    @property
    def model(self) -> str: ...

    async def transcribe_submission(
        self, submission: ExamSubmission
    ) -> dict[tuple[str, int], str]: ...


async def transcribe_batch(
    transcriber: PageTranscriber,
    batch: ExamBatch,
    recorder: Recorder,
    limit: int = DEFAULT_MODEL_CONCURRENCY,
) -> dict[tuple[str, int], str]:
    captured = await gather_limited(
        (
            _transcribe_submission(transcriber, submission, recorder)
            for submission in batch.submissions
        ),
        limit,
    )
    texts: dict[tuple[str, int], str] = {}
    for pages in captured:
        texts.update(pages)
    return texts


async def _transcribe_submission(
    transcriber: PageTranscriber, submission: ExamSubmission, recorder: Recorder
) -> dict[tuple[str, int], str]:
    model: Any = getattr(transcriber, "model", "")
    with recorder.span(
        f"{TRANSCRIPTION_SPAN_PREFIX}{submission.submission_id}",
        stage="GRADE",
        attributes={
            "student_id": submission.student_id,
            ATTR_GEN_AI_SYSTEM: "google_gemini",
            "gen_ai.model": model,
        },
    ) as span:
        annotate_span(span, EVIDENCE_TRANSCRIBER_ID)
        texts: dict[tuple[str, int], str] = {}
        with usage_scope() as ledger:
            try:
                authorize_llm(
                    EVIDENCE_TRANSCRIBER_ID,
                    submission.submission_id,
                    model_id=model,
                    recorder=recorder,
                    parent=span,
                )
                texts = await transcriber.transcribe_submission(submission)
            except Exception as error:
                logger.warning(
                    "evidence transcription skipped for submission %s: %s",
                    submission.submission_id,
                    error,
                )
        span.set(ATTR_GEN_AI_CALLS, ledger.calls)
        span.set(ATTR_GEN_AI_USAGE_INPUT_TOKENS, ledger.input_tokens)
        span.set(ATTR_GEN_AI_USAGE_OUTPUT_TOKENS, ledger.output_tokens)
        span.set(ATTR_GEN_AI_USAGE_TOKENS, ledger.total_tokens)
        span.set(ATTR_TRANSCRIPTION_PAGES, len(texts))
    return texts

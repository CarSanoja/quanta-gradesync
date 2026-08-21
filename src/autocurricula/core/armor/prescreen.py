import logging
from typing import Any

from autocurricula.core.armor.deterministic import scan_derived
from autocurricula.core.armor.metadata import QUOTE_LIMIT, screen_metadata
from autocurricula.core.armor.scripted import scan_page_text
from autocurricula.core.harness import PageTextProvider
from autocurricula.schemas.armor import ArmorSeverity, ArmorVerdict
from autocurricula.schemas.exam import ExamSubmission

logger = logging.getLogger(__name__)


def screen_page_encodings(
    submission: ExamSubmission, provider: PageTextProvider
) -> ArmorVerdict | None:
    pages = max((exam_file.page_count for exam_file in submission.files), default=0)
    for page in range(1, pages + 1):
        text = provider.page_text(submission.submission_id, page)
        if not text or scan_page_text(text) is not None:
            continue
        hit = scan_derived(text)
        if hit is None:
            continue
        return ArmorVerdict(
            injection_detected=True,
            quoted_text=hit.quote.lower()[:QUOTE_LIMIT],
            severity=ArmorSeverity.HIGH,
            rationale=(
                f"page {page} hides a grader-directed instruction behind "
                f"{hit.technique} encoding (match on {hit.pattern!r})"
            ),
        )
    return None


def deterministic_screen(
    submission: ExamSubmission, provider: PageTextProvider | None = None
) -> ArmorVerdict | None:
    verdict = screen_metadata(submission)
    if verdict is not None:
        return verdict
    if provider is None:
        return None
    return screen_page_encodings(submission, provider)


class PrescreenedDetector:
    def __init__(
        self, detector: Any, provider: PageTextProvider | None = None
    ) -> None:
        self._detector = detector
        self._provider = provider

    @property
    def model(self) -> str:
        return getattr(self._detector, "model", "")

    @property
    def inner(self) -> Any:
        return self._detector

    async def screen(self, submission: ExamSubmission) -> ArmorVerdict:
        verdict = deterministic_screen(submission, self._provider)
        if verdict is None:
            return await self._detector.screen(submission)
        logger.warning(
            "deterministic prescreen flagged submission %s: %s",
            submission.submission_id,
            verdict.rationale,
        )
        return verdict

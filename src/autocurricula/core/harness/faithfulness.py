import re
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from autocurricula.schemas.common import FrozenStrictModel
from autocurricula.schemas.grading import EvidenceSpan, GradingResult

_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip().lower())


@runtime_checkable
class PageTextProvider(Protocol):
    def page_text(self, submission_id: str, page: int) -> str | None: ...


class SidecarTextProvider:
    def __init__(self, texts: dict[tuple[str, int], str]) -> None:
        self._texts = {
            (submission_id, page): normalize_text(text)
            for (submission_id, page), text in texts.items()
        }

    def page_text(self, submission_id: str, page: int) -> str | None:
        return self._texts.get((submission_id, page))


class SpanCheck(FrozenStrictModel):
    page: int
    faithful: bool


class FaithfulnessReport(FrozenStrictModel):
    submission_id: str
    verified_spans: int
    hallucinated: list[SpanCheck] = []


def span_is_faithful(quote: str, page_text: str | None) -> bool:
    if page_text is None:
        return True
    return normalize_text(quote) in normalize_text(page_text)


def verify_result(
    result: GradingResult, provider: PageTextProvider
) -> FaithfulnessReport:
    verified = 0
    hallucinated: list[SpanCheck] = []
    for criterion in result.criterion_scores:
        for span in criterion.evidence:
            verified += 1
            if not span_is_faithful(span.quote, provider.page_text(result.submission_id, span.page)):
                hallucinated.append(SpanCheck(page=span.page, faithful=False))
    return FaithfulnessReport(
        submission_id=result.submission_id,
        verified_spans=verified,
        hallucinated=hallucinated,
    )


def enforce_result(
    result: GradingResult, provider: PageTextProvider
) -> GradingResult:
    if all(
        span_is_faithful(span.quote, provider.page_text(result.submission_id, span.page))
        for criterion in result.criterion_scores
        for span in criterion.evidence
    ):
        return result
    adjusted = result.model_copy(deep=True)
    fixed = [
        criterion.model_copy(
            update={
                "confidence": 0.0,
                "comment": (
                    f"{criterion.comment} [faithfulness: cited span not found "
                    "in page transcript]"
                ),
            }
        )
        for criterion in adjusted.criterion_scores
    ]
    return adjusted.model_copy(update={"criterion_scores": fixed})


Verifier = Callable[[GradingResult, PageTextProvider], GradingResult]


def sidecar_texts_from_batch(batch) -> dict[tuple[str, int], str]:
    from pathlib import Path

    texts: dict[tuple[str, int], str] = {}
    for submission in batch.submissions:
        for exam_file in submission.files:
            if exam_file.local_path is None:
                continue
            sidecar = Path(exam_file.local_path).with_suffix(".txt")
            if not sidecar.is_file():
                continue
            content = sidecar.read_text(encoding="utf-8")
            for page in range(1, max(1, exam_file.page_count) + 1):
                texts[(submission.submission_id, page)] = content
    return texts

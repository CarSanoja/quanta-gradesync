from collections.abc import Callable, Iterator
from typing import Any, Protocol, runtime_checkable

from autocurricula.core.harness.faithfulness_text import (
    DEFAULT_MATCH_THRESHOLD as DEFAULT_MATCH_THRESHOLD,
)
from autocurricula.core.harness.faithfulness_text import (
    MIN_FUZZY_QUOTE_CHARS as MIN_FUZZY_QUOTE_CHARS,
)
from autocurricula.core.harness.faithfulness_text import (
    NEAR_MATCH_RATIO as NEAR_MATCH_RATIO,
)
from autocurricula.core.harness.faithfulness_text import (
    compact_text as compact_text,
)
from autocurricula.core.harness.faithfulness_text import (
    fold_symbols as fold_symbols,
)
from autocurricula.core.harness.faithfulness_text import (
    longest_common_coverage as longest_common_coverage,
)
from autocurricula.core.harness.faithfulness_text import (
    near_match_ratio as near_match_ratio,
)
from autocurricula.core.harness.faithfulness_text import (
    normalize_text as normalize_text,
)
from autocurricula.schemas.common import FrozenStrictModel
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.telemetry import (
    VERIFICATION_FAILED,
    VERIFICATION_UNCHECKED,
    VERIFICATION_VERIFIED,
)


@runtime_checkable
class PageTextProvider(Protocol):
    def page_text(self, submission_id: str, page: int) -> str | None: ...


def span_status(
    quote: str, page_text: str | None, *, match_threshold: float | None = None
) -> str:
    if page_text is None:
        return VERIFICATION_UNCHECKED
    normalized_quote = normalize_text(quote)
    if normalized_quote in normalize_text(page_text):
        return VERIFICATION_VERIFIED
    compact_quote = compact_text(quote)
    compact_page = compact_text(page_text)
    if compact_quote and compact_quote in compact_page:
        return VERIFICATION_VERIFIED
    if match_threshold is None or len(normalized_quote) < MIN_FUZZY_QUOTE_CHARS:
        return VERIFICATION_FAILED
    coverage = longest_common_coverage(compact_quote, compact_page)
    if coverage >= match_threshold:
        return VERIFICATION_VERIFIED
    if near_match_ratio(compact_quote, compact_page) >= NEAR_MATCH_RATIO:
        return VERIFICATION_VERIFIED
    return VERIFICATION_FAILED


def span_is_faithful(
    quote: str, page_text: str | None, *, match_threshold: float | None = None
) -> bool:
    status = span_status(quote, page_text, match_threshold=match_threshold)
    return status != VERIFICATION_FAILED


def provider_threshold(provider: Any, submission_id: str, page: int) -> float | None:
    resolver = getattr(provider, "threshold_for", None)
    if callable(resolver):
        return resolver(submission_id, page)
    value = getattr(provider, "match_threshold", None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class SpanCheck(FrozenStrictModel):
    page: int
    faithful: bool


class FaithfulnessReport(FrozenStrictModel):
    submission_id: str
    verified_spans: int
    unchecked_spans: int = 0
    hallucinated: list[SpanCheck] = []

    @property
    def status(self) -> str:
        if self.hallucinated:
            return VERIFICATION_FAILED
        if self.unchecked_spans or self.verified_spans == 0:
            return VERIFICATION_UNCHECKED
        return VERIFICATION_VERIFIED

    @property
    def checked(self) -> bool:
        return self.status != VERIFICATION_UNCHECKED


def span_statuses(
    result: GradingResult, provider: PageTextProvider
) -> Iterator[tuple[int, str]]:
    for criterion in result.criterion_scores:
        for span in criterion.evidence:
            yield (
                span.page,
                span_status(
                    span.quote,
                    provider.page_text(result.submission_id, span.page),
                    match_threshold=provider_threshold(
                        provider, result.submission_id, span.page
                    ),
                ),
            )


def verify_result(
    result: GradingResult, provider: PageTextProvider
) -> FaithfulnessReport:
    verified = 0
    unchecked = 0
    hallucinated: list[SpanCheck] = []
    for page, status in span_statuses(result, provider):
        if status == VERIFICATION_VERIFIED:
            verified += 1
        elif status == VERIFICATION_UNCHECKED:
            unchecked += 1
        else:
            hallucinated.append(SpanCheck(page=page, faithful=False))
    return FaithfulnessReport(
        submission_id=result.submission_id,
        verified_spans=verified,
        unchecked_spans=unchecked,
        hallucinated=hallucinated,
    )


def enforce_result(
    result: GradingResult, provider: PageTextProvider
) -> GradingResult:
    if all(
        status != VERIFICATION_FAILED
        for _, status in span_statuses(result, provider)
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

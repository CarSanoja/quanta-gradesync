from autocurricula.core.harness import (
    CompositeTextProvider,
    SidecarTextProvider,
    TranscriptTextProvider,
    enforce_result,
    span_status,
    verify_result,
)
from autocurricula.core.harness.faithfulness import (
    MIN_FUZZY_QUOTE_CHARS,
    longest_common_coverage,
    normalize_text,
    provider_threshold,
)
from autocurricula.core.harness.faithfulness_providers import (
    SOURCE_SIDECAR,
    SOURCE_TRANSCRIPT,
)
from autocurricula.schemas.grading import CriterionScore, EvidenceSpan, GradingResult
from autocurricula.schemas.telemetry import (
    VERIFICATION_FAILED,
    VERIFICATION_UNCHECKED,
    VERIFICATION_VERIFIED,
)

SUBMISSION = "sub-1"
NEAR_QUOTE = "the student solved for x"
NEAR_PAGE = "the page reads the student solved fpr x clearly"


def make_result(quote: str, page: int = 1) -> GradingResult:
    return GradingResult(
        submission_id=SUBMISSION,
        criterion_scores=[
            CriterionScore(
                criterion_id="crit-a",
                score=3.0,
                comment="ok",
                evidence=[EvidenceSpan(page=page, quote=quote, rationale="cited")],
                confidence=0.9,
            )
        ],
        total_score=3.0,
        percentage=75.0,
        feedback="ok",
    )


def test_no_threshold_keeps_the_legacy_exact_behaviour() -> None:
    assert span_status(NEAR_QUOTE, NEAR_PAGE) == VERIFICATION_FAILED
    assert span_status("the student solved for x", f"a {NEAR_QUOTE} b") == (
        VERIFICATION_VERIFIED
    )
    assert span_status(NEAR_QUOTE, None) == VERIFICATION_UNCHECKED


def test_missing_page_text_stays_unchecked_under_a_threshold() -> None:
    assert span_status(NEAR_QUOTE, None, match_threshold=0.75) == VERIFICATION_UNCHECKED


def test_a_near_miss_verifies_below_its_coverage_and_fails_above_it() -> None:
    coverage = longest_common_coverage(
        normalize_text(NEAR_QUOTE), normalize_text(NEAR_PAGE)
    )

    assert 0.75 <= coverage < 0.9
    assert span_status(NEAR_QUOTE, NEAR_PAGE, match_threshold=0.75) == (
        VERIFICATION_VERIFIED
    )
    assert span_status(NEAR_QUOTE, NEAR_PAGE, match_threshold=coverage) == (
        VERIFICATION_VERIFIED
    )
    assert span_status(NEAR_QUOTE, NEAR_PAGE, match_threshold=0.9) == (
        VERIFICATION_FAILED
    )


def test_a_fabricated_quote_still_fails_under_the_threshold() -> None:
    status = span_status(
        NEAR_QUOTE, "an entirely different transcript", match_threshold=0.75
    )

    assert status == VERIFICATION_FAILED


def test_short_quotes_always_require_exact_containment() -> None:
    page = "the student wrote 2x + 3 = 9 on the page"

    assert len(normalize_text("2x + 3 = 7")) < MIN_FUZZY_QUOTE_CHARS
    assert span_status("2x + 3 = 7", page, match_threshold=0.5) == VERIFICATION_FAILED
    assert span_status("2x + 3 = 9", page, match_threshold=0.5) == (
        VERIFICATION_VERIFIED
    )


def test_the_fuzzy_floor_starts_at_the_declared_quote_length() -> None:
    page = "the product is 5 and the sum is 5"

    assert len(normalize_text("product is 6")) == MIN_FUZZY_QUOTE_CHARS
    assert span_status("product is 6", page, match_threshold=0.75) == (
        VERIFICATION_VERIFIED
    )
    assert span_status("roduct is 6", page, match_threshold=0.75) == VERIFICATION_FAILED


def test_transcript_provider_carries_its_threshold() -> None:
    provider = TranscriptTextProvider({(SUBMISSION, 1): NEAR_PAGE}, 0.75)

    assert provider_threshold(provider, SUBMISSION, 1) == 0.75
    assert verify_result(make_result(NEAR_QUOTE), provider).status == (
        VERIFICATION_VERIFIED
    )


def test_sidecar_provider_stays_exact() -> None:
    provider = SidecarTextProvider({(SUBMISSION, 1): NEAR_PAGE})

    assert provider_threshold(provider, SUBMISSION, 1) is None
    assert verify_result(make_result(NEAR_QUOTE), provider).status == (
        VERIFICATION_FAILED
    )


def test_composite_prefers_the_sidecar_when_one_exists() -> None:
    provider = CompositeTextProvider(
        SidecarTextProvider({(SUBMISSION, 1): "the ground truth page"}),
        TranscriptTextProvider({(SUBMISSION, 1): NEAR_PAGE}, 0.75),
    )

    assert provider.page_text(SUBMISSION, 1) == "the ground truth page"
    assert provider.source_for(SUBMISSION, 1) == SOURCE_SIDECAR
    assert provider.threshold_for(SUBMISSION, 1) is None
    assert verify_result(make_result(NEAR_QUOTE), provider).status == (
        VERIFICATION_FAILED
    )


def test_composite_falls_back_to_the_transcript_with_fuzzy_matching() -> None:
    provider = CompositeTextProvider(
        SidecarTextProvider({}),
        TranscriptTextProvider({(SUBMISSION, 1): NEAR_PAGE}, 0.75),
    )

    assert provider.source_for(SUBMISSION, 1) == SOURCE_TRANSCRIPT
    assert provider.threshold_for(SUBMISSION, 1) == 0.75
    assert verify_result(make_result(NEAR_QUOTE), provider).status == (
        VERIFICATION_VERIFIED
    )


def test_composite_without_any_page_text_reports_unchecked() -> None:
    provider = CompositeTextProvider(
        SidecarTextProvider({}), TranscriptTextProvider({}, 0.75)
    )

    assert provider.page_text(SUBMISSION, 1) is None
    assert provider.source_for(SUBMISSION, 1) is None
    assert verify_result(make_result(NEAR_QUOTE), provider).status == (
        VERIFICATION_UNCHECKED
    )


def test_enforce_zeroes_confidence_when_the_transcript_contradicts_the_quote() -> None:
    provider = CompositeTextProvider(
        SidecarTextProvider({}),
        TranscriptTextProvider({(SUBMISSION, 1): "a page about photosynthesis"}, 0.75),
    )
    result = make_result(NEAR_QUOTE)

    enforced = enforce_result(result, provider)

    assert enforced.criterion_scores[0].confidence == 0.0
    assert "faithfulness" in enforced.criterion_scores[0].comment


def test_enforce_keeps_a_result_the_transcript_supports() -> None:
    provider = CompositeTextProvider(
        SidecarTextProvider({}),
        TranscriptTextProvider({(SUBMISSION, 1): NEAR_PAGE}, 0.75),
    )
    result = make_result(NEAR_QUOTE)

    assert enforce_result(result, provider) is result

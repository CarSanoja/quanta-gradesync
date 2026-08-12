import statistics
from collections.abc import Sequence
from typing import NamedTuple

from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.memory import EpisodicStudentProfile

MIN_TERMS_FOR_ZSCORE = 3
MIN_TERMS_FOR_TREND = 2
MISSING_BASELINE_COUNT = 1
_EPSILON = 1e-9


class ZscoreSignal(NamedTuple):
    value: float
    mean: float
    std: float


class ConfidenceSignal(NamedTuple):
    value: float
    scored_criteria: int


class MissingRateSignal(NamedTuple):
    rate: float
    actual: int
    expected: int


def term_percentages(profile: EpisodicStudentProfile | None) -> list[float]:
    if profile is None:
        return []
    ordered = sorted(profile.terms, key=lambda snapshot: snapshot.term)
    return [snapshot.avg_percentage for snapshot in ordered]


def percentage_zscore(profile: EpisodicStudentProfile | None) -> ZscoreSignal | None:
    values = term_percentages(profile)
    if len(values) < MIN_TERMS_FOR_ZSCORE:
        return None
    mean = statistics.fmean(values)
    std = statistics.pstdev(values)
    if std < _EPSILON:
        return None
    return ZscoreSignal(value=(values[-1] - mean) / std, mean=mean, std=std)


def trend_slope(profile: EpisodicStudentProfile | None) -> float | None:
    values = term_percentages(profile)
    if len(values) < MIN_TERMS_FOR_TREND:
        return None
    mean_x = (len(values) - 1) / 2
    mean_y = statistics.fmean(values)
    numerator = sum(
        (index - mean_x) * (value - mean_y) for index, value in enumerate(values)
    )
    denominator = sum((index - mean_x) ** 2 for index in range(len(values)))
    if denominator < _EPSILON:
        return None
    return numerator / denominator


def mean_grading_confidence(
    results: Sequence[GradingResult],
) -> ConfidenceSignal | None:
    confidences = [
        criterion.confidence
        for result in results
        for criterion in result.criterion_scores
    ]
    if not confidences:
        return None
    return ConfidenceSignal(
        value=statistics.fmean(confidences), scored_criteria=len(confidences)
    )


def missing_submission_rate(
    profile: EpisodicStudentProfile | None,
    results: Sequence[GradingResult],
) -> MissingRateSignal | None:
    if profile is None or not profile.terms:
        if results:
            return None
        return MissingRateSignal(
            rate=1.0, actual=0, expected=MISSING_BASELINE_COUNT
        )
    ordered = sorted(profile.terms, key=lambda snapshot: snapshot.term)
    if len(ordered) < 2:
        return None
    expected = max(snapshot.submissions_count for snapshot in ordered[:-1])
    actual = ordered[-1].submissions_count
    if expected <= 0:
        return None
    return MissingRateSignal(
        rate=max(0.0, (expected - actual) / expected), actual=actual, expected=expected
    )

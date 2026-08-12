from collections.abc import Sequence

from autocurricula.agents.risk_signals import (
    mean_grading_confidence,
    missing_submission_rate,
    percentage_zscore,
    trend_slope,
)
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.memory import EpisodicStudentProfile
from autocurricula.schemas.risk import RiskDriver, RiskLevel

DRIVER_VALUE_DECIMALS = 4

Breach = tuple[RiskLevel, float]
DriverSignal = tuple[str, RiskLevel, RiskDriver]
Thresholds = tuple[tuple[RiskLevel, float], ...]


def breach_below(value: float, thresholds: Thresholds) -> Breach | None:
    for level, threshold in thresholds:
        if value <= threshold:
            return level, threshold
    return None


def breach_above(value: float, thresholds: Thresholds) -> Breach | None:
    for level, threshold in thresholds:
        if value >= threshold:
            return level, threshold
    return None


def build_zscore_driver(
    profile: EpisodicStudentProfile | None, thresholds: Thresholds, metric: str
) -> DriverSignal | None:
    signal = percentage_zscore(profile)
    if signal is None:
        return None
    breached = breach_below(signal.value, thresholds)
    if breached is None:
        return None
    level, threshold = breached
    return (
        metric,
        level,
        RiskDriver(
            metric=metric,
            value=round(signal.value, DRIVER_VALUE_DECIMALS),
            threshold=threshold,
            explanation=(
                f"latest term average sits {signal.value:.2f} standard deviations from "
                f"the term-history mean of {signal.mean:.1f}% (std {signal.std:.1f}), "
                f"at or below {threshold:.2f}"
            ),
        ),
    )


def build_trend_driver(
    profile: EpisodicStudentProfile | None, thresholds: Thresholds, metric: str
) -> DriverSignal | None:
    slope = trend_slope(profile)
    if slope is None:
        return None
    breached = breach_below(slope, thresholds)
    if breached is None:
        return None
    level, threshold = breached
    return (
        metric,
        level,
        RiskDriver(
            metric=metric,
            value=round(slope, DRIVER_VALUE_DECIMALS),
            threshold=threshold,
            explanation=(
                f"term-over-term percentage trend of {slope:.2f} points per term "
                f"is at or below {threshold:.2f}"
            ),
        ),
    )


def build_confidence_driver(
    results: Sequence[GradingResult], thresholds: Thresholds, metric: str
) -> DriverSignal | None:
    signal = mean_grading_confidence(results)
    if signal is None:
        return None
    breached = breach_below(signal.value, thresholds)
    if breached is None:
        return None
    level, threshold = breached
    return (
        metric,
        level,
        RiskDriver(
            metric=metric,
            value=round(signal.value, DRIVER_VALUE_DECIMALS),
            threshold=threshold,
            explanation=(
                f"mean grading confidence across {signal.scored_criteria} scored "
                f"criteria is {signal.value:.2f}, at or below {threshold:.2f}, "
                f"indicating evidence-confidence collapse"
            ),
        ),
    )


def build_missing_driver(
    profile: EpisodicStudentProfile | None,
    results: Sequence[GradingResult],
    thresholds: Thresholds,
    metric: str,
) -> DriverSignal | None:
    signal = missing_submission_rate(profile, results)
    if signal is None:
        return None
    breached = breach_above(signal.rate, thresholds)
    if breached is None:
        return None
    level, threshold = breached
    return (
        metric,
        level,
        RiskDriver(
            metric=metric,
            value=round(signal.rate, DRIVER_VALUE_DECIMALS),
            threshold=threshold,
            explanation=(
                f"latest term delivered {signal.actual} of {signal.expected} expected "
                f"submissions (missing rate {signal.rate:.2f} at or above "
                f"{threshold:.2f})"
            ),
        ),
    )

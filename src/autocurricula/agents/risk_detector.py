import asyncio
from collections.abc import Mapping, Sequence

from autocurricula.agents.risk_drivers import (
    DriverSignal,
    Thresholds,
    build_confidence_driver,
    build_missing_driver,
    build_trend_driver,
    build_zscore_driver,
)
from autocurricula.schemas.common import JobId, StudentId, TzAwareDatetime, utc_now
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.memory import EpisodicStudentProfile
from autocurricula.schemas.risk import RiskAssessment, RiskLevel

ZSCORE_THRESHOLDS: Thresholds = (
    (RiskLevel.CRITICAL, -2.0),
    (RiskLevel.HIGH, -1.5),
    (RiskLevel.MEDIUM, -1.0),
)
TREND_SLOPE_THRESHOLDS: Thresholds = (
    (RiskLevel.CRITICAL, -10.0),
    (RiskLevel.HIGH, -5.0),
    (RiskLevel.MEDIUM, -2.0),
)
CONFIDENCE_THRESHOLDS: Thresholds = (
    (RiskLevel.CRITICAL, 0.35),
    (RiskLevel.HIGH, 0.45),
    (RiskLevel.MEDIUM, 0.55),
)
MISSING_RATE_THRESHOLDS: Thresholds = (
    (RiskLevel.CRITICAL, 0.5),
    (RiskLevel.HIGH, 0.3),
    (RiskLevel.MEDIUM, 0.15),
)
LEVEL_SCORE = {
    RiskLevel.LOW: 0.0,
    RiskLevel.MEDIUM: 0.5,
    RiskLevel.HIGH: 0.75,
    RiskLevel.CRITICAL: 1.0,
}
ADDITIONAL_DRIVER_WEIGHT = 0.05
RISK_SCORE_DECIMALS = 4

ZSCORE_METRIC = "percentage_zscore"
TREND_METRIC = "percentage_trend_slope"
CONFIDENCE_METRIC = "mean_grading_confidence"
MISSING_RATE_METRIC = "missing_submission_rate"

RECOMMENDED_INTERVENTIONS = {
    ZSCORE_METRIC: "schedule_one_on_one_learning_review",
    TREND_METRIC: "assign_targeted_practice_plan",
    CONFIDENCE_METRIC: "request_resubmission_or_oral_follow_up",
    MISSING_RATE_METRIC: "notify_guardian_and_verify_submission_pipeline",
}

_LEVEL_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class RiskDetector:
    async def assess(
        self,
        profile: EpisodicStudentProfile | None,
        results: Sequence[GradingResult],
        job_id: JobId,
        *,
        student_id: StudentId | None = None,
        assessed_at: TzAwareDatetime | None = None,
    ) -> RiskAssessment:
        effective_student = profile.student_id if profile is not None else student_id
        if effective_student is None:
            raise ValueError("student_id is required when profile is None")
        signals = self._signals(profile, results)
        return RiskAssessment(
            student_id=effective_student,
            job_id=job_id,
            risk_score=self._risk_score(signals),
            level=self._overall_level(signals),
            drivers=[signal[2] for signal in signals],
            recommended_interventions=[
                RECOMMENDED_INTERVENTIONS[signal[0]]
                for signal in signals
                if signal[0] in RECOMMENDED_INTERVENTIONS
            ],
            assessed_at=assessed_at if assessed_at is not None else utc_now(),
        )

    async def assess_batch(
        self,
        profiles: Sequence[EpisodicStudentProfile],
        results_by_student: Mapping[str, Sequence[GradingResult]],
        job_id: JobId,
        *,
        assessed_at: TzAwareDatetime | None = None,
    ) -> list[RiskAssessment]:
        return list(
            await asyncio.gather(
                *(
                    self.assess(
                        profile,
                        results_by_student.get(profile.student_id, []),
                        job_id,
                        assessed_at=assessed_at,
                    )
                    for profile in profiles
                )
            )
        )

    @staticmethod
    def _signals(
        profile: EpisodicStudentProfile | None,
        results: Sequence[GradingResult],
    ) -> list[DriverSignal]:
        candidates = (
            build_zscore_driver(profile, ZSCORE_THRESHOLDS, ZSCORE_METRIC),
            build_trend_driver(profile, TREND_SLOPE_THRESHOLDS, TREND_METRIC),
            build_confidence_driver(results, CONFIDENCE_THRESHOLDS, CONFIDENCE_METRIC),
            build_missing_driver(
                profile, results, MISSING_RATE_THRESHOLDS, MISSING_RATE_METRIC
            ),
        )
        return [signal for signal in candidates if signal is not None]

    @staticmethod
    def _overall_level(signals: Sequence[DriverSignal]) -> RiskLevel:
        if not signals:
            return RiskLevel.LOW
        return max(
            (signal[1] for signal in signals),
            key=lambda level: _LEVEL_RANK[level],
        )

    @staticmethod
    def _risk_score(signals: Sequence[DriverSignal]) -> float:
        if not signals:
            return 0.0
        base = max(LEVEL_SCORE[signal[1]] for signal in signals)
        total = base + ADDITIONAL_DRIVER_WEIGHT * (len(signals) - 1)
        return round(min(1.0, total), RISK_SCORE_DECIMALS)

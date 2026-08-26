from collections.abc import Sequence
from statistics import pstdev

from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.schemas.metrics import OptimizerReport


def _spread(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return max(values) - min(values)


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return pstdev(values)


class AntiGamingValidator:
    def __init__(
        self,
        calibration: CalibrationSet,
        *,
        variance_collapse_ratio: float = 0.20,
        constant_tolerance: float = 1e-9,
        constant_sample_fraction: float = 0.8,
    ) -> None:
        if not 0.0 <= variance_collapse_ratio < 1.0:
            raise ValueError("variance_collapse_ratio must be within [0, 1)")
        if constant_tolerance < 0.0:
            raise ValueError("constant_tolerance must be non-negative")
        if not 0.0 < constant_sample_fraction <= 1.0:
            raise ValueError("constant_sample_fraction must be within (0, 1]")
        self.calibration = calibration
        self.variance_collapse_ratio = variance_collapse_ratio
        self.constant_tolerance = constant_tolerance
        self.constant_sample_fraction = constant_sample_fraction

    def validate(
        self, proposal_report: OptimizerReport, distributions: Sequence[Sequence[float]]
    ) -> OptimizerReport:
        reasons = self._collect_reasons(proposal_report, distributions)
        if not reasons:
            return proposal_report
        payload = proposal_report.model_dump()
        payload["accepted"] = False
        payload["rejected_reasons"] = list(proposal_report.rejected_reasons) + reasons
        return OptimizerReport.model_validate(payload)

    def _collect_reasons(
        self, report: OptimizerReport, distributions: Sequence[Sequence[float]]
    ) -> list[str]:
        reasons: list[str] = []
        flattened = [value for distribution in distributions for value in distribution]
        if not flattened:
            return ["constant_output_detected: candidate produced no score distributions"]
        reasons.extend(self._constant_output_reasons(flattened, distributions))
        reasons.extend(self._variance_collapse_reasons(report, flattened))
        reasons.extend(self._ground_truth_contact_reasons(report, distributions))
        return reasons

    def _constant_output_reasons(
        self, flattened: Sequence[float], distributions: Sequence[Sequence[float]]
    ) -> list[str]:
        reasons: list[str] = []
        if _spread(flattened) <= self.constant_tolerance:
            reasons.append("constant_output_detected: every candidate score is identical")
        scored_samples = [distribution for distribution in distributions if len(distribution) >= 2]
        if scored_samples:
            constant_samples = sum(
                1 for distribution in scored_samples if _spread(distribution) <= self.constant_tolerance
            )
            if constant_samples / len(scored_samples) >= self.constant_sample_fraction:
                reasons.append(
                    f"constant_output_detected: {constant_samples}/{len(scored_samples)} samples have zero within-sample variance"
                )
        return reasons

    def _variance_collapse_reasons(
        self, report: OptimizerReport, flattened: Sequence[float]
    ) -> list[str]:
        ground_truth = [
            value for distribution in self.calibration.ground_truth_distributions() for value in distribution
        ]
        truth_std = _std(ground_truth)
        if truth_std <= 0.0:
            return []
        candidate_std = _std(flattened)
        agreement_improved = (
            report.candidate_metrics.quadratic_weighted_kappa
            > report.previous_metrics.quadratic_weighted_kappa
        )
        floor = truth_std * (1.0 - self.variance_collapse_ratio)
        if candidate_std < floor and not agreement_improved:
            return [
                "variance_collapse: candidate score std "
                f"{candidate_std:.4f} below floor {floor:.4f} of ground truth std {truth_std:.4f} without agreement improvement"
            ]
        return []

    def _ground_truth_contact_reasons(
        self, report: OptimizerReport, distributions: Sequence[Sequence[float]]
    ) -> list[str]:
        total_samples = len(self.calibration)
        if len(distributions) >= total_samples:
            return []
        if report.candidate_metrics.mae >= report.previous_metrics.mae:
            return []
        return [
            "ground_truth_contact: metrics improved while only "
            f"{len(distributions)}/{total_samples} calibration samples were evaluated"
        ]

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator

from autocurricula.config.settings import get_settings
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.grading import CriterionScore, GradingResult
from autocurricula.schemas.metrics import CalibrationMetrics

CALIBRATION_LEVELS = 4


class CalibrationSample(StrictBaseModel):
    submission_id: str = Field(min_length=1)
    submission_summary: str = Field(min_length=1)
    criterion_ids: list[str] = Field(min_length=1)
    max_scores: list[float] = Field(min_length=1)
    expected: list[CriterionScore] = Field(min_length=1)

    @field_validator("criterion_ids")
    @classmethod
    def _unique_criterion_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("criterion_id values must be unique within a calibration sample")
        return value

    @field_validator("max_scores")
    @classmethod
    def _positive_max_scores(cls, value: list[float]) -> list[float]:
        if any(score <= 0 for score in value):
            raise ValueError("max_score values must be positive")
        return value

    @model_validator(mode="after")
    def _aligned_criteria(self) -> Self:
        if len(self.criterion_ids) != len(self.max_scores):
            raise ValueError("criterion_ids and max_scores must have equal length")
        expected_ids = [score.criterion_id for score in self.expected]
        allowed = set(self.criterion_ids)
        unknown = sorted({criterion_id for criterion_id in expected_ids if criterion_id not in allowed})
        if unknown:
            raise ValueError(f"expected scores reference unknown criteria: {unknown}")
        if len(expected_ids) != len(set(expected_ids)):
            raise ValueError("expected criterion scores must be unique within a calibration sample")
        return self

    @property
    def max_scores_by_criterion(self) -> dict[str, float]:
        return dict(zip(self.criterion_ids, self.max_scores, strict=True))


class CalibrationSet:
    def __init__(self, samples: Sequence[CalibrationSample]) -> None:
        ids = [sample.submission_id for sample in samples]
        if len(ids) != len(set(ids)):
            raise ValueError("submission_id values must be unique within a calibration set")
        self._samples = sorted(samples, key=lambda sample: sample.submission_id)

    @classmethod
    def from_directory(cls, directory: Path | None = None) -> "CalibrationSet":
        base = Path(directory) if directory is not None else get_settings().local_data_dir / "calibration"
        if not base.is_dir():
            raise FileNotFoundError(f"calibration directory not found: {base}")
        samples: list[CalibrationSample] = []
        for path in sorted(base.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries = payload if isinstance(payload, list) else [payload]
            samples.extend(CalibrationSample.model_validate(entry) for entry in entries)
        if not samples:
            raise ValueError(f"no calibration samples found in {base}")
        return cls(samples)

    @property
    def samples(self) -> list[CalibrationSample]:
        return list(self._samples)

    @property
    def submission_ids(self) -> list[str]:
        return [sample.submission_id for sample in self._samples]

    def ground_truth_distributions(self) -> list[list[float]]:
        return [[score.score for score in sample.expected] for sample in self._samples]

    def __iter__(self):
        return iter(self._samples)

    def __len__(self) -> int:
        return len(self._samples)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CalibrationSet):
            return NotImplemented
        return self._samples == other._samples

    def __repr__(self) -> str:
        return f"CalibrationSet(samples={len(self._samples)})"


def _bucket_level(value: float, ceiling: float) -> int:
    normalized = value / ceiling if ceiling > 0 else 0.0
    clamped = min(1.0, max(0.0, normalized))
    return min(CALIBRATION_LEVELS - 1, int(clamped * CALIBRATION_LEVELS))


def _quadratic_weighted_kappa(expected_levels: Sequence[int], predicted_levels: Sequence[int]) -> float:
    size = CALIBRATION_LEVELS
    observed = [[0] * size for _ in range(size)]
    for expected_level, predicted_level in zip(expected_levels, predicted_levels, strict=True):
        observed[expected_level][predicted_level] += 1
    total = sum(sum(row) for row in observed)
    if total == 0:
        return 0.0
    row_totals = [sum(observed[i]) for i in range(size)]
    column_totals = [sum(observed[i][j] for i in range(size)) for j in range(size)]
    denominator = float(size - 1) ** 2
    weighted_observed = 0.0
    weighted_expected = 0.0
    for i in range(size):
        for j in range(size):
            weight = (i - j) ** 2 / denominator
            weighted_observed += weight * observed[i][j]
            weighted_expected += weight * row_totals[i] * column_totals[j] / total
    if weighted_expected == 0.0:
        return 1.0 if weighted_observed == 0.0 else 0.0
    kappa = 1.0 - weighted_observed / weighted_expected
    return max(-1.0, min(1.0, kappa))


def compute_calibration_metrics(
    results: Sequence[GradingResult], samples: Sequence[CalibrationSample]
) -> CalibrationMetrics:
    by_submission = {result.submission_id: result for result in results}
    absolute_errors: list[float] = []
    signed_errors: list[float] = []
    per_criterion_errors: dict[str, list[float]] = {}
    expected_levels: list[int] = []
    predicted_levels: list[int] = []
    for sample in samples:
        result = by_submission.get(sample.submission_id)
        if result is None:
            continue
        predicted = {score.criterion_id: score.score for score in result.criterion_scores}
        ceilings = sample.max_scores_by_criterion
        for expected_score in sample.expected:
            criterion_id = expected_score.criterion_id
            predicted_value = predicted.get(criterion_id, 0.0)
            absolute_error = abs(predicted_value - expected_score.score)
            absolute_errors.append(absolute_error)
            signed_errors.append(predicted_value - expected_score.score)
            per_criterion_errors.setdefault(criterion_id, []).append(absolute_error)
            ceiling = ceilings[criterion_id]
            predicted_levels.append(_bucket_level(predicted_value, ceiling))
            expected_levels.append(_bucket_level(expected_score.score, ceiling))
    if not absolute_errors:
        raise ValueError("no overlapping submissions between grading results and calibration samples")
    mae = sum(absolute_errors) / len(absolute_errors)
    bias = sum(signed_errors) / len(signed_errors)
    kappa = _quadratic_weighted_kappa(expected_levels, predicted_levels)
    per_criterion = {
        criterion_id: round(sum(errors) / len(errors), 6)
        for criterion_id, errors in sorted(per_criterion_errors.items())
    }
    return CalibrationMetrics(
        mae=round(mae, 6),
        quadratic_weighted_kappa=round(kappa, 6),
        bias=round(bias, 6),
        per_criterion=per_criterion,
    )

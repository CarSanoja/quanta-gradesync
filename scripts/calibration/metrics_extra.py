from collections.abc import Sequence

from autocurricula.core.evolution.calibration_store import (
    CalibrationSample,
    _bucket_level,
    _quadratic_weighted_kappa,
)
from autocurricula.schemas.grading import GradingResult


def per_criterion_breakdown(
    results: Sequence[GradingResult], samples: Sequence[CalibrationSample]
) -> dict[str, dict[str, float | int]]:
    by_submission = {result.submission_id: result for result in results}
    triples: dict[str, list[tuple[float, float, float]]] = {}
    for sample in samples:
        result = by_submission.get(sample.submission_id)
        if result is None:
            continue
        predicted = {
            score.criterion_id: score.score for score in result.criterion_scores
        }
        ceilings = sample.max_scores_by_criterion
        for expected in sample.expected:
            criterion_id = expected.criterion_id
            triples.setdefault(criterion_id, []).append(
                (
                    expected.score,
                    predicted.get(criterion_id, 0.0),
                    ceilings[criterion_id],
                )
            )
    breakdown: dict[str, dict[str, float | int]] = {}
    for criterion_id, rows in sorted(triples.items()):
        errors = [predicted - expected for expected, predicted, _ in rows]
        expected_levels = [
            _bucket_level(expected, ceiling) for expected, _, ceiling in rows
        ]
        predicted_levels = [
            _bucket_level(predicted, ceiling) for _, predicted, ceiling in rows
        ]
        breakdown[criterion_id] = {
            "n": len(rows),
            "mae": round(sum(abs(error) for error in errors) / len(rows), 6),
            "bias": round(sum(errors) / len(rows), 6),
            "qwk": round(
                _quadratic_weighted_kappa(expected_levels, predicted_levels), 6
            ),
        }
    return breakdown


def score_table(
    results: Sequence[GradingResult], samples: Sequence[CalibrationSample]
) -> list[dict]:
    by_submission = {result.submission_id: result for result in results}
    rows: list[dict] = []
    for sample in samples:
        result = by_submission.get(sample.submission_id)
        predicted = (
            {score.criterion_id: score.score for score in result.criterion_scores}
            if result is not None
            else {}
        )
        rows.append(
            {
                "submission_id": sample.submission_id,
                "human": {score.criterion_id: score.score for score in sample.expected},
                "predicted": predicted,
                "human_total": round(
                    sum(score.score for score in sample.expected), 2
                ),
                "predicted_total": (
                    result.total_score if result is not None else None
                ),
            }
        )
    return rows

from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.metrics import CalibrationMetrics

from autocurricula.agents.failing_samples import select_failing_samples

LOCAL_PROPOSER_PROVENANCE = "local-heuristic-proposer"
DEFAULT_LOCAL_FAILING_SAMPLE_LIMIT = 2


def _bias_directive(metrics: CalibrationMetrics) -> str:
    if metrics.bias > 0.05:
        return (
            f"scores run {metrics.bias:.3f} points above ground truth; "
            "require explicit evidence before awarding high marks"
        )
    if metrics.bias < -0.05:
        return (
            f"scores run {metrics.bias:.3f} points below ground truth; "
            "award credit for partially correct reasoning"
        )
    return "keep the current severity balance while reducing absolute error"


def _worst_criterion_directive(metrics: CalibrationMetrics) -> str:
    if not metrics.per_criterion:
        return "audit every criterion against its full mastery range"
    criterion_id, mae = max(metrics.per_criterion.items(), key=lambda item: item[1])
    return f"re-examine criterion {criterion_id!r} with mean absolute error {mae:.3f} and score it across its full mastery range"


def _agreement_directive(metrics: CalibrationMetrics) -> str:
    if metrics.quadratic_weighted_kappa >= 0.8:
        return "hold the current mastery-level agreement"
    return (
        f"quadratic weighted kappa is {metrics.quadratic_weighted_kappa:.3f}; "
        "distinguish adjacent mastery levels explicitly"
    )


class LocalHeuristicProposer:
    def __init__(
        self,
        calibration: CalibrationSet | None = None,
        *,
        failing_sample_limit: int = DEFAULT_LOCAL_FAILING_SAMPLE_LIMIT,
    ) -> None:
        if failing_sample_limit < 1:
            raise ValueError("failing_sample_limit must be at least 1")
        self._calibration = calibration
        self._failing_sample_limit = failing_sample_limit

    def bind_calibration(self, calibration: CalibrationSet) -> None:
        self._calibration = calibration

    async def __call__(
        self,
        current: PromptVariant,
        metrics: CalibrationMetrics,
        attempt: int = 0,
    ) -> PromptVariant:
        return PromptVariant(
            variant_id=current.variant_id,
            version=current.version + 1,
            system_instruction=self._mutated_instruction(current, metrics, attempt),
            few_shots=self._few_shots(current, metrics),
            provenance=f"{LOCAL_PROPOSER_PROVENANCE}:a{max(0, attempt)}",
        )

    def _mutated_instruction(
        self, current: PromptVariant, metrics: CalibrationMetrics, attempt: int
    ) -> str:
        directives = [
            _bias_directive(metrics),
            _worst_criterion_directive(metrics),
            _agreement_directive(metrics),
        ]
        rotation = max(0, attempt) % len(directives)
        rotated = directives[rotation:] + directives[:rotation]
        if attempt > 0:
            rotated.append(
                f"mutation attempt {attempt + 1}: emphasize a different lever than previous attempts"
            )
        body = "\n".join(f"- {directive}" for directive in rotated)
        return f"{current.system_instruction.strip()}\n\nCalibration directives:\n{body}"

    def _few_shots(
        self, current: PromptVariant, metrics: CalibrationMetrics
    ) -> list[str]:
        shots = list(current.few_shots)
        if self._calibration is None:
            return shots
        for sample in select_failing_samples(
            self._calibration.samples, metrics, self._failing_sample_limit
        ):
            ceilings = sample.max_scores_by_criterion
            pairs = ", ".join(
                f"{score.criterion_id}={score.score:g}/{ceilings[score.criterion_id]:g}"
                for score in sample.expected
            )
            shots.append(
                f"Submission {sample.submission_id}: {sample.submission_summary}\n"
                f"Calibrated scores: {pairs}"
            )
        return shots

from autocurricula.core.evolution.anti_gaming_validator import AntiGamingValidator
from autocurricula.core.evolution.calibration_store import (
    CalibrationSet,
    compute_calibration_metrics,
)
from autocurricula.core.evolution.engine_support import (
    CandidateKey,
    PromptProposer,
    VariantEvaluator,
    call_proposer,
    candidate_key,
    score_distributions,
)
from autocurricula.core.evolution.prompt_mutator import PromptRegistry, PromptVariant
from autocurricula.core.harness.eval_harness import ObjectiveGate
from autocurricula.schemas.metrics import (
    CalibrationMetrics,
    OptimizerReport,
    TournamentReport,
)

__all__ = [
    "MetaOptimizerEngine",
    "PromptProposer",
    "VariantEvaluator",
    "call_proposer",
]


class MetaOptimizerEngine:
    def __init__(
        self,
        proposer: PromptProposer,
        validator: AntiGamingValidator,
        registry: PromptRegistry,
        *,
        evaluator: VariantEvaluator,
        calibration: CalibrationSet,
        metrics_threshold: float = 0.0,
        variant_id: str = "grading_default",
        objective_gate: ObjectiveGate | None = None,
    ) -> None:
        if metrics_threshold < 0.0:
            raise ValueError("metrics_threshold must be non-negative")
        self._proposer = proposer
        self._validator = validator
        self._registry = registry
        self._evaluator = evaluator
        self._calibration = calibration
        self._metrics_threshold = metrics_threshold
        self._variant_id = variant_id
        self._objective_gate = objective_gate
        self._iteration = 0

    @property
    def iteration(self) -> int:
        return self._iteration

    @property
    def variant_id(self) -> str:
        return self._variant_id

    @property
    def current_variant(self) -> PromptVariant:
        return self._registry.get(self._variant_id)

    async def run_iteration(self) -> OptimizerReport:
        current = self._require_current()
        previous_metrics = await self._evaluate_variant(current)
        candidate = await call_proposer(self._proposer, current, previous_metrics, 0)
        report, _ = await self._score_candidate(current, candidate, previous_metrics)
        report = self._apply_objective_gate(report)
        if report.accepted:
            self._registry.register(self._promote(current, candidate))
        return report

    async def run_tournament(self, candidate_count: int) -> TournamentReport:
        if candidate_count < 1:
            raise ValueError("candidate_count must be at least 1")
        current = self._require_current()
        previous_metrics = await self._evaluate_variant(current)
        scored: list[tuple[OptimizerReport, PromptVariant]] = []
        seen: set[CandidateKey] = set()
        for attempt in range(candidate_count):
            candidate = await call_proposer(
                self._proposer, current, previous_metrics, attempt
            )
            key = candidate_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            report, _ = await self._score_candidate(
                current, candidate, previous_metrics
            )
            scored.append((self._apply_objective_gate(report), candidate))
        reports = [report for report, _ in scored]
        winner_report = self._select_winner(reports)
        if winner_report is not None:
            winning_variant = next(
                variant for report, variant in scored if report is winner_report
            )
            self._registry.register(self._promote(current, winning_variant))
        return TournamentReport(candidates=reports, winner=winner_report)

    def _apply_objective_gate(self, report: OptimizerReport) -> OptimizerReport:
        if self._objective_gate is None or not report.accepted:
            return report
        outcome = self._objective_gate.evaluate(report.candidate_metrics)
        if outcome.passed:
            return report
        payload = report.model_dump()
        payload["accepted"] = False
        payload["rejected_reasons"] = list(report.rejected_reasons) + [
            f"objective gate: {reason}" for reason in outcome.reasons
        ]
        return OptimizerReport.model_validate(payload)

    async def _evaluate_variant(self, variant: PromptVariant) -> CalibrationMetrics:
        results = await self._evaluator(variant, self._calibration)
        return compute_calibration_metrics(results, self._calibration.samples)

    async def _score_candidate(
        self,
        current: PromptVariant,
        candidate: PromptVariant,
        previous_metrics: CalibrationMetrics,
    ) -> tuple[OptimizerReport, list[list[float]]]:
        candidate_results = await self._evaluator(candidate, self._calibration)
        candidate_metrics = compute_calibration_metrics(
            candidate_results, self._calibration.samples
        )
        self._iteration += 1
        delta_mae = candidate_metrics.mae - previous_metrics.mae
        report = self._build_report(
            previous_metrics, candidate_metrics, delta_mae
        )
        distributions = score_distributions(candidate_results)
        return self._validator.validate(report, distributions), distributions

    @staticmethod
    def _select_winner(
        reports: list[OptimizerReport],
    ) -> OptimizerReport | None:
        accepted = [report for report in reports if report.accepted]
        if not accepted:
            return None
        return min(
            accepted,
            key=lambda report: (
                report.candidate_metrics.mae,
                -report.candidate_metrics.quadratic_weighted_kappa,
            ),
        )

    def _require_current(self) -> PromptVariant:
        if self._variant_id not in self._registry:
            raise ValueError(
                f"registry has no prompt variant {self._variant_id!r} to evolve"
            )
        return self._registry.get(self._variant_id)

    def _build_report(
        self,
        previous_metrics: CalibrationMetrics,
        candidate_metrics: CalibrationMetrics,
        delta_mae: float,
    ) -> OptimizerReport:
        improvement = previous_metrics.mae - candidate_metrics.mae
        accepted = improvement > 0.0 and improvement >= self._metrics_threshold
        rejected_reasons: list[str] = []
        if not accepted:
            rejected_reasons = [
                f"mae improvement {improvement:.6f} did not clear threshold {self._metrics_threshold:.6f}"
            ]
        return OptimizerReport(
            iteration=self._iteration,
            previous_metrics=previous_metrics,
            candidate_metrics=candidate_metrics,
            delta_mae=round(delta_mae, 6),
            accepted=accepted,
            rejected_reasons=rejected_reasons,
        )

    @staticmethod
    def _promote(current: PromptVariant, candidate: PromptVariant) -> PromptVariant:
        return PromptVariant(
            variant_id=current.variant_id,
            version=max(candidate.version, current.version + 1),
            system_instruction=candidate.system_instruction,
            few_shots=candidate.few_shots,
            provenance=candidate.provenance,
        )

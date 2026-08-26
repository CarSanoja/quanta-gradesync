from collections.abc import Callable
from pathlib import Path

from autocurricula.agents.prompt_variant_store import PromptVariantStore
from autocurricula.agents.prompts import (
    AUDITOR_VARIANT_ID,
    GRADING_VARIANT_ID,
    OPTIMIZER_VARIANT_ID,
    seed_auditor_prompt,
    seed_grading_prompt,
    seed_optimizer_variant,
)
from autocurricula.core.evolution.anti_gaming_validator import AntiGamingValidator
from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.optimizer_engine import (
    MetaOptimizerEngine,
    PromptProposer,
    VariantEvaluator,
)
from autocurricula.core.evolution.prompt_mutator import PromptRegistry
from autocurricula.core.harness.eval_harness import ObjectiveGate
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.schemas.metrics import OptimizerReport

__all__ = ["MetaOptimizerAgent"]

VariantSeeder = Callable[[PromptRegistry], object]

VARIANT_SEEDERS: dict[str, VariantSeeder] = {
    GRADING_VARIANT_ID: seed_grading_prompt,
    AUDITOR_VARIANT_ID: seed_auditor_prompt,
}


class MetaOptimizerAgent:
    def __init__(
        self,
        *,
        memory_manager: MemoryManager,
        proposer: PromptProposer,
        evaluator: VariantEvaluator,
        registry: PromptRegistry | None = None,
        variant_store: PromptVariantStore | None = None,
        calibration_dir: Path | None = None,
        metrics_threshold: float = 0.0,
        candidate_count: int = 1,
        convergence_min_improvement: float = 0.01,
        max_cycles: int = 3,
        variance_collapse_ratio: float = 0.20,
        objective_gate: ObjectiveGate | None = None,
        variant_id: str = GRADING_VARIANT_ID,
    ) -> None:
        if metrics_threshold < 0.0:
            raise ValueError("metrics_threshold must be non-negative")
        if candidate_count < 1:
            raise ValueError("candidate_count must be at least 1")
        if convergence_min_improvement < 0.0:
            raise ValueError("convergence_min_improvement must be non-negative")
        if max_cycles < 1:
            raise ValueError("max_cycles must be at least 1")
        self._memory_manager = memory_manager
        self._proposer = proposer
        self._evaluator = evaluator
        self._registry = registry if registry is not None else PromptRegistry()
        self._variant_store = variant_store
        self._calibration_dir = calibration_dir
        self._metrics_threshold = metrics_threshold
        self._candidate_count = candidate_count
        self._convergence_min_improvement = convergence_min_improvement
        self._max_cycles = max_cycles
        self._variance_collapse_ratio = variance_collapse_ratio
        self._objective_gate = objective_gate
        self._variant_id = variant_id

    @property
    def memory_manager(self) -> MemoryManager:
        return self._memory_manager

    @property
    def registry(self) -> PromptRegistry:
        return self._registry

    @property
    def variant_id(self) -> str:
        return self._variant_id

    async def run_cycle(
        self, calibration_dir: Path | None = None
    ) -> OptimizerReport | None:
        directory = (
            calibration_dir if calibration_dir is not None else self._calibration_dir
        )
        calibration = CalibrationSet.from_directory(directory)
        await self.load_history()
        self._seed()
        self._bind(calibration)
        engine = MetaOptimizerEngine(
            self._proposer,
            AntiGamingValidator(
                calibration, variance_collapse_ratio=self._variance_collapse_ratio
            ),
            self._registry,
            evaluator=self._evaluator,
            calibration=calibration,
            metrics_threshold=self._metrics_threshold,
            variant_id=self._variant_id,
            objective_gate=self._objective_gate,
        )
        tournament = await engine.run_tournament(self._candidate_count)
        winner = tournament.winner
        if winner is not None and self._variant_store is not None:
            await self._variant_store.append(
                self._registry.get(self._variant_id), winner
            )
        return winner

    async def run_until_convergence(
        self, calibration_dir: Path | None = None
    ) -> list[OptimizerReport]:
        winners: list[OptimizerReport] = []
        for _ in range(self._max_cycles):
            winner = await self.run_cycle(calibration_dir)
            if winner is None:
                break
            winners.append(winner)
            improvement = winner.previous_metrics.mae - winner.candidate_metrics.mae
            if improvement < self._convergence_min_improvement:
                break
        return winners

    async def load_history(self) -> int:
        if self._variant_store is None:
            return 0
        restored = 0
        for variant in await self._variant_store.list_variants(self._variant_id):
            if self._variant_id in self._registry:
                active = self._registry.get(self._variant_id)
                if variant.version <= active.version:
                    continue
            self._registry.register(variant)
            restored += 1
        return restored

    def _seed(self) -> None:
        if OPTIMIZER_VARIANT_ID not in self._registry:
            self._registry.register(seed_optimizer_variant())
        if self._variant_id in self._registry:
            return
        seeder = VARIANT_SEEDERS.get(self._variant_id)
        if seeder is None:
            raise ValueError(
                f"registry has no prompt variant {self._variant_id!r} to evolve"
            )
        seeder(self._registry)

    def _bind(self, calibration: CalibrationSet) -> None:
        binder = getattr(self._proposer, "bind_calibration", None)
        if callable(binder):
            binder(calibration)

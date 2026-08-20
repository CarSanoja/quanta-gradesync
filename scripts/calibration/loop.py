import time
from pathlib import Path

from autocurricula.agents.optimizer_factory import build_objective_gate
from autocurricula.agents.prompt_variant_store import LocalPromptVariantStore
from autocurricula.agents.prompts import GRADING_VARIANT_ID, seed_grading_prompt
from autocurricula.config.settings import Settings
from autocurricula.core.evolution.anti_gaming_validator import AntiGamingValidator
from autocurricula.core.evolution.calibration_store import (
    CalibrationSet,
    compute_calibration_metrics,
)
from autocurricula.core.evolution.engine_support import call_proposer, candidate_key
from autocurricula.core.evolution.optimizer_engine import MetaOptimizerEngine
from autocurricula.core.evolution.prompt_mutator import PromptRegistry, PromptVariant
from autocurricula.core.telemetry.usage import usage_scope
from autocurricula.schemas.metrics import CalibrationMetrics
from calibration.metrics_extra import per_criterion_breakdown, score_table


class ProposerRecorder:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.cycle = 0
        self.records: list[dict] = []

    def bind_calibration(self, calibration: CalibrationSet) -> None:
        binder = getattr(self._inner, "bind_calibration", None)
        if callable(binder):
            binder(calibration)

    async def __call__(
        self, current: PromptVariant, metrics: CalibrationMetrics, attempt: int = 0
    ):
        started = time.perf_counter()
        with usage_scope() as ledger:
            variant = await call_proposer(self._inner, current, metrics, attempt)
        log = getattr(self._inner, "proposal_log", [])
        rationale = log[-1]["rationale"] if log else ""
        self.records.append(
            {
                "cycle": self.cycle,
                "attempt": attempt,
                "base_version": current.version,
                "variant": variant,
                "rationale": rationale,
                "seconds": round(time.perf_counter() - started, 2),
                "input_tokens": ledger.input_tokens,
                "output_tokens": ledger.output_tokens,
                "calls": ledger.calls,
            }
        )
        return variant


def _metrics_block(metrics: CalibrationMetrics, results, samples) -> dict:
    return {
        "overall": metrics.model_dump(mode="json"),
        "per_criterion": per_criterion_breakdown(results, samples),
        "scores": score_table(results, samples),
    }


def _cycle_candidates(recorder: ProposerRecorder, cycle: int, reports) -> list[dict]:
    proposals = [record for record in recorder.records if record["cycle"] == cycle]
    seen: set = set()
    unique: list[dict] = []
    duplicates: list[dict] = []
    for record in proposals:
        key = candidate_key(record["variant"])
        (duplicates if key in seen else unique).append(record)
        seen.add(key)
    rows: list[dict] = []
    for record, report in zip(unique, reports, strict=False):
        variant = record["variant"]
        rows.append(
            {
                "attempt": record["attempt"],
                "provenance": variant.provenance,
                "version": variant.version,
                "instruction_chars": len(variant.system_instruction),
                "few_shots": len(variant.few_shots),
                "rationale": record["rationale"],
                "proposer_seconds": record["seconds"],
                "accepted": report.accepted,
                "rejected_reasons": list(report.rejected_reasons),
                "candidate_metrics": report.candidate_metrics.model_dump(mode="json"),
                "previous_metrics": report.previous_metrics.model_dump(mode="json"),
                "delta_mae": report.delta_mae,
                "system_instruction": variant.system_instruction,
                "few_shot_texts": list(variant.few_shots),
            }
        )
    for record in duplicates:
        rows.append(
            {
                "attempt": record["attempt"],
                "provenance": record["variant"].provenance,
                "duplicate_of_earlier_attempt": True,
                "rationale": record["rationale"],
            }
        )
    return rows


async def run_loop(
    settings: Settings,
    calibration: CalibrationSet,
    evaluator,
    proposer,
    output_dir: Path,
    *,
    candidate_count: int,
    max_cycles: int,
    min_improvement: float,
) -> dict:
    registry = PromptRegistry()
    seed_grading_prompt(registry)
    recorder = ProposerRecorder(proposer)
    recorder.bind_calibration(calibration)
    gate = build_objective_gate(settings, "grading")
    engine = MetaOptimizerEngine(
        recorder,
        AntiGamingValidator(
            calibration, variance_collapse_ratio=settings.variance_collapse_ratio
        ),
        registry,
        evaluator=evaluator,
        calibration=calibration,
        metrics_threshold=0.0,
        variant_id=GRADING_VARIANT_ID,
        objective_gate=gate,
    )
    store = LocalPromptVariantStore(output_dir)
    baseline_variant = registry.get(GRADING_VARIANT_ID)
    baseline_results = await evaluator(baseline_variant, calibration)
    baseline_metrics = compute_calibration_metrics(
        baseline_results, calibration.samples
    )
    baseline = _metrics_block(baseline_metrics, baseline_results, calibration.samples)
    baseline["variant_version"] = baseline_variant.version
    cycles: list[dict] = []
    for cycle in range(1, max_cycles + 1):
        recorder.cycle = cycle
        try:
            tournament = await engine.run_tournament(candidate_count)
        except Exception as error:
            cycles.append(
                {
                    "cycle": cycle,
                    "candidates": _cycle_candidates(recorder, cycle, []),
                    "promoted": False,
                    "promoted_version": registry.get(GRADING_VARIANT_ID).version,
                    "stop_reason": f"cycle aborted: {type(error).__name__}: {error}",
                }
            )
            break
        winner = tournament.winner
        promoted = registry.get(GRADING_VARIANT_ID)
        cycles.append(
            {
                "cycle": cycle,
                "candidates": _cycle_candidates(recorder, cycle, tournament.candidates),
                "winner_provenance": promoted.provenance if winner else None,
                "promoted_version": promoted.version,
                "promoted": winner is not None,
            }
        )
        if winner is None:
            cycles[-1]["stop_reason"] = "no candidate accepted"
            break
        await store.append(promoted, winner)
        improvement = winner.previous_metrics.mae - winner.candidate_metrics.mae
        cycles[-1]["mae_improvement"] = round(improvement, 6)
        if improvement < min_improvement:
            cycles[-1]["stop_reason"] = (
                f"converged: improvement {improvement:.6f} < {min_improvement}"
            )
            break
    final_variant = registry.get(GRADING_VARIANT_ID)
    final_results = await evaluator(final_variant, calibration)
    final_metrics = compute_calibration_metrics(final_results, calibration.samples)
    final = _metrics_block(final_metrics, final_results, calibration.samples)
    final["variant_version"] = final_variant.version
    final["variant_provenance"] = final_variant.provenance
    return {
        "baseline": baseline,
        "cycles": cycles,
        "final": final,
        "proposer_records": [
            {key: value for key, value in record.items() if key != "variant"}
            for record in recorder.records
        ],
        "evaluator_log": list(getattr(evaluator, "call_log", [])),
        "registry_history": [
            variant.model_dump(mode="json")
            for variant in registry.history(GRADING_VARIANT_ID)
        ],
    }

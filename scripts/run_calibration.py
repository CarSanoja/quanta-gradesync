import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calibration.evaluator import MultimodalCalibrationEvaluator
from calibration.loop import run_loop
from calibration.reporting import usage_summary, write_outputs
from calibration.samples import load_batch, write_samples

from autocurricula.agents.calibration_evaluator import LocalGradingEvaluator
from autocurricula.agents.optimizer_factory import build_proposer
from autocurricula.config.genai_env import configure_genai_env
from autocurricula.config.settings import Settings, get_settings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the active grading prompt against human ground truth and run "
            "the meta-optimizer convergence loop with the real Gemini proposer and "
            "multimodal grading evaluator."
        )
    )
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--candidates", type=int, default=None)
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--min-improvement", type=float, default=None)
    return parser.parse_args(argv)


def resolve_settings(offline: bool, output: Path) -> Settings:
    if offline:
        return Settings(local_mode=True, gcp_project_id="", local_data_dir=output)
    settings = get_settings()
    if settings.local_mode or not settings.is_gcp_configured:
        raise SystemExit(
            "GCP mode required: set GRADESYNC_LOCAL_MODE=false and "
            "GRADESYNC_GCP_PROJECT_ID, or pass --offline for the lexical dry run"
        )
    configure_genai_env(settings)
    return settings


async def execute(arguments: argparse.Namespace) -> dict:
    output = arguments.output.resolve()
    settings = resolve_settings(arguments.offline, output)
    batch = load_batch(arguments.batch)
    write_samples(batch, output)
    if arguments.offline:
        evaluator = LocalGradingEvaluator()
    else:
        evaluator = MultimodalCalibrationEvaluator(
            settings, batch.rubric, batch.image_paths
        )
    proposer = build_proposer(settings)
    started = time.perf_counter()
    record = await run_loop(
        settings,
        batch.calibration,
        evaluator,
        proposer,
        output,
        candidate_count=(
            arguments.candidates
            if arguments.candidates is not None
            else settings.optimizer_candidates
        ),
        max_cycles=(
            arguments.max_cycles
            if arguments.max_cycles is not None
            else settings.optimizer_max_cycles
        ),
        min_improvement=(
            arguments.min_improvement
            if arguments.min_improvement is not None
            else settings.optimizer_convergence_min_improvement
        ),
    )
    record["wall_seconds"] = round(time.perf_counter() - started, 2)
    record["run"] = {
        "started_at": datetime.now(tz=UTC).isoformat(),
        "mode": "offline" if arguments.offline else "gcp",
        "lot_code": batch.lot_code,
        "samples": batch.calibration.submission_ids,
        "grading_model": settings.gemini_pro_model,
        "proposer_model": settings.gemini_flash_model,
        "gemini_location": settings.gemini_location,
        "objective_gate": {
            "enabled": settings.objective_gate_enabled,
            "qwk_min": settings.objective_qwk_min,
            "mae_max": settings.objective_mae_max,
            "bias_abs_max": settings.objective_bias_abs_max,
        },
        "variance_collapse_ratio": settings.variance_collapse_ratio,
    }
    record["usage"] = usage_summary(
        record, settings.gemini_pro_model, settings.gemini_flash_model
    )
    return record


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    record = asyncio.run(execute(arguments))
    json_path, markdown_path = write_outputs(record, arguments.output.resolve())
    baseline = record["baseline"]["overall"]
    final = record["final"]["overall"]
    print(f"run record      {json_path}")
    print(f"run summary     {markdown_path}")
    print(
        f"baseline        mae={baseline['mae']:.3f} "
        f"qwk={baseline['quadratic_weighted_kappa']:.3f} bias={baseline['bias']:+.3f}"
    )
    print(
        f"final           mae={final['mae']:.3f} "
        f"qwk={final['quadratic_weighted_kappa']:.3f} bias={final['bias']:+.3f} "
        f"(variant v{record['final']['variant_version']})"
    )
    print(f"cycles          {len(record['cycles'])}")
    print(f"wall seconds    {record['wall_seconds']}")
    print(f"total cost usd  {record['usage']['total_cost_usd']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

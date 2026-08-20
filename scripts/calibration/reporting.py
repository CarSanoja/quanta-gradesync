import json
from pathlib import Path

PRICES_PER_MILLION = {
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.5-flash-lite": (0.30, 2.50),
}

RUN_JSON_NAME = "calibration_run.json"
RUN_MARKDOWN_NAME = "calibration_run.md"


def _cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICES_PER_MILLION.get(model, (0.0, 0.0))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def usage_summary(record: dict, grading_model: str, proposer_model: str) -> dict:
    grading = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    for entry in record["evaluator_log"]:
        grading["calls"] += entry.get("grading_calls", 0)
        grading["input_tokens"] += entry.get("input_tokens", 0)
        grading["output_tokens"] += entry.get("output_tokens", 0)
    proposing = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    for entry in record["proposer_records"]:
        proposing["calls"] += entry.get("calls", 0)
        proposing["input_tokens"] += entry.get("input_tokens", 0)
        proposing["output_tokens"] += entry.get("output_tokens", 0)
    grading_cost = _cost(
        grading_model, grading["input_tokens"], grading["output_tokens"]
    )
    proposing_cost = _cost(
        proposer_model, proposing["input_tokens"], proposing["output_tokens"]
    )
    return {
        "grading": {**grading, "model": grading_model, "cost_usd": round(grading_cost, 4)},
        "proposer": {
            **proposing,
            "model": proposer_model,
            "cost_usd": round(proposing_cost, 4),
        },
        "total_cost_usd": round(grading_cost + proposing_cost, 4),
    }


def _metrics_row(label: str, block: dict) -> str:
    overall = block["overall"]
    return (
        f"| {label} | {overall['mae']:.3f} | "
        f"{overall['quadratic_weighted_kappa']:.3f} | {overall['bias']:+.3f} |"
    )


def render_markdown(record: dict) -> str:
    lines = [
        "# Calibration run summary",
        "",
        "| Stage | MAE | QWK | Bias |",
        "|---|---:|---:|---:|",
        _metrics_row("baseline", record["baseline"]),
        _metrics_row("final", record["final"]),
        "",
        "## Cycles",
        "",
    ]
    for cycle in record["cycles"]:
        lines.append(f"### Cycle {cycle['cycle']}")
        lines.append("")
        lines.append("| Candidate | Accepted | MAE | QWK | Bias | Rejection |")
        lines.append("|---|---|---:|---:|---:|---|")
        for candidate in cycle["candidates"]:
            if candidate.get("duplicate_of_earlier_attempt"):
                lines.append(
                    f"| {candidate['provenance']} | skipped | - | - | - | duplicate proposal |"
                )
                continue
            metrics = candidate["candidate_metrics"]
            reasons = "; ".join(candidate["rejected_reasons"]) or "-"
            lines.append(
                f"| {candidate['provenance']} | {candidate['accepted']} | "
                f"{metrics['mae']:.3f} | {metrics['quadratic_weighted_kappa']:.3f} | "
                f"{metrics['bias']:+.3f} | {reasons} |"
            )
        lines.append("")
        lines.append(
            f"Promoted: {cycle['promoted']} (active version {cycle['promoted_version']})"
        )
        if "stop_reason" in cycle:
            lines.append(f"Stop: {cycle['stop_reason']}")
        lines.append("")
    usage = record.get("usage", {})
    if usage:
        lines.append("## Usage")
        lines.append("")
        lines.append(json.dumps(usage, indent=2))
        lines.append("")
    return "\n".join(lines)


def write_outputs(record: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / RUN_JSON_NAME
    json_path.write_text(
        json.dumps(record, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path = output_dir / RUN_MARKDOWN_NAME
    markdown_path.write_text(render_markdown(record) + "\n", encoding="utf-8")
    return json_path, markdown_path

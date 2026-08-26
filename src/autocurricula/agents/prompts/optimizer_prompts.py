import json
from collections.abc import Sequence

from pydantic import field_validator

from autocurricula.core.evolution.calibration_store import CalibrationSample
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.common import FrozenStrictModel
from autocurricula.schemas.metrics import CalibrationMetrics

OPTIMIZER_VARIANT_ID = "optimizer-v1"
SEED_PROVENANCE = "seed:optimizer-v1"
MAX_INSTRUCTION_CHARS = 3000

PROPOSER_SYSTEM_INSTRUCTION = """You are the Meta-Optimizer of the AutoCurricula & GradeSync Engine, the self-improvement loop of an automated K-12 exam grading system.

You receive the currently deployed grading prompt variant, calibration metrics measured against human ground-truth scores, and the calibration samples the current variant grades worst.

Your task: propose the next generation of the grading system instruction and its few-shot examples so that mean absolute error falls, quadratic weighted kappa rises, and bias moves toward zero.

Rules:
- Preserve every grading rule that already works; mutate only what the metrics justify.
- Each few-shot must show one submission summary together with the calibrated criterion scores and a short justification of those scores.
- Never optimize by collapsing score variance, repeating a constant score, or echoing the ground truth; every score must follow from evidence in the student work.
- Keep the instruction imperative, unambiguous, and under 3000 characters.
- You must justify every change in the rationale: name the metric that motivated it and the effect you expect it to have.
"""

OUTPUT_CONTRACT = """Output contract:
- Respond with a single ProposalSchema object and nothing else.
- new_system_instruction: non-blank string holding the complete mutated grading system instruction, never a diff.
- new_few_shots: list of non-blank few-shot example strings; use an empty list only when few-shots would not help.
- rationale: non-blank string justifying each change against calibration_metrics and failing_samples."""


class _ProposerSeed(FrozenStrictModel):
    variant_id: str
    version: int
    system_instruction: str
    few_shots: list[str]
    provenance: str

    @field_validator("system_instruction")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("system_instruction must not be blank")
        return value


def seed_optimizer_variant() -> PromptVariant:
    seed = _ProposerSeed(
        variant_id=OPTIMIZER_VARIANT_ID,
        version=1,
        system_instruction=PROPOSER_SYSTEM_INSTRUCTION,
        few_shots=[],
        provenance=SEED_PROVENANCE,
    )
    return PromptVariant.from_dict(seed.model_dump())


def build_proposer_system_instruction(current: PromptVariant | None = None) -> str:
    base = (
        current.system_instruction
        if current is not None
        else PROPOSER_SYSTEM_INSTRUCTION
    )
    instruction = base.strip()
    if len(instruction) > MAX_INSTRUCTION_CHARS:
        instruction = instruction[:MAX_INSTRUCTION_CHARS]
    return f"{instruction}\n\n{OUTPUT_CONTRACT}"


def build_proposer_payload(
    current: PromptVariant,
    metrics: CalibrationMetrics,
    failing_samples: Sequence[CalibrationSample],
) -> str:
    payload = {
        "current_variant": current.to_dict(),
        "calibration_metrics": metrics.model_dump(mode="json"),
        "failing_samples": [sample.model_dump(mode="json") for sample in failing_samples],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)

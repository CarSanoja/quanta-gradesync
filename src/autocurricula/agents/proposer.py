import json

from pydantic import Field, field_validator

from autocurricula.core.evolution.calibration_store import (
    CalibrationSample,
    CalibrationSet,
)
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.metrics import CalibrationMetrics

from autocurricula.agents.adk_llm import build_structured_agent, run_structured_output
from autocurricula.agents.failing_samples import (
    DEFAULT_FAILING_SAMPLE_LIMIT,
    select_failing_samples,
)
from autocurricula.agents.prompts import (
    build_proposer_payload,
    build_proposer_system_instruction,
)

PROPOSER_APP_NAME = "autocurricula-meta-optimizer"
PROPOSER_TEMPERATURE = 0.2


class ProposalSchema(StrictBaseModel):
    new_system_instruction: str = Field(min_length=1)
    new_few_shots: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)

    @field_validator("new_system_instruction")
    @classmethod
    def _non_blank_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("new_system_instruction must not be blank")
        return value

    @field_validator("new_few_shots")
    @classmethod
    def _non_empty_shots(cls, value: list[str]) -> list[str]:
        if any(not shot.strip() for shot in value):
            raise ValueError("new_few_shots must be non-empty strings")
        return value


class LlmProposer:
    def __init__(
        self,
        model: str,
        *,
        calibration: CalibrationSet | None = None,
        failing_sample_limit: int = DEFAULT_FAILING_SAMPLE_LIMIT,
        temperature: float = PROPOSER_TEMPERATURE,
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be blank")
        if failing_sample_limit < 1:
            raise ValueError("failing_sample_limit must be at least 1")
        self._model = model
        self._calibration = calibration
        self._failing_sample_limit = failing_sample_limit
        self._temperature = temperature
        self.proposal_log: list[dict[str, str]] = []

    def bind_calibration(self, calibration: CalibrationSet) -> None:
        self._calibration = calibration

    async def __call__(
        self,
        current: PromptVariant,
        metrics: CalibrationMetrics,
        attempt: int = 0,
    ) -> PromptVariant:
        agent = build_structured_agent(
            name="meta_optimizer_proposer",
            model=self._model,
            instruction=build_proposer_system_instruction(),
            output_schema=ProposalSchema,
            temperature=self._attempt_temperature(attempt),
        )
        payload = build_proposer_payload(current, metrics, self._failing_samples(metrics))
        if attempt > 0:
            payload = (
                f"{payload}\n{json.dumps({'diversity_directive': f'propose mutation alternative {attempt}, clearly distinct from earlier attempts'})}"
            )
        proposal = await run_structured_output(
            agent=agent,
            payload=payload,
            schema=ProposalSchema,
            app_name=PROPOSER_APP_NAME,
            user_id="meta-optimizer",
        )
        provenance = f"llm-proposer:{current.variant_id}:v{current.version}:a{attempt}"
        self.proposal_log.append(
            {"provenance": provenance, "rationale": proposal.rationale}
        )
        return PromptVariant(
            variant_id=current.variant_id,
            version=current.version + 1,
            system_instruction=proposal.new_system_instruction,
            few_shots=proposal.new_few_shots,
            provenance=provenance,
        )

    def _attempt_temperature(self, attempt: int) -> float:
        return min(0.9, self._temperature + 0.15 * max(0, attempt))

    def _failing_samples(self, metrics: CalibrationMetrics) -> list[CalibrationSample]:
        if self._calibration is None:
            return []
        return select_failing_samples(
            self._calibration.samples, metrics, self._failing_sample_limit
        )

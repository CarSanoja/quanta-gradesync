import json
import re

from pydantic import Field

from autocurricula.agents.adk_llm import (
    StructuredLlmError,
    build_structured_agent,
    run_structured_output,
)
from autocurricula.config.settings import Settings, get_settings
from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.optimizer_engine import VariantEvaluator
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.grading import CriterionScore, GradingResult

CALIBRATION_EVALUATOR_APP = "autocurricula-calibration"
CALIBRATION_EVALUATOR_TEMPERATURE = 0.0
LOCAL_EVALUATOR_PROVENANCE = "local-lexical-evaluator"
_MIN_TOKEN_LENGTH = 3
_BASE_COVERAGE = 0.25
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class GradingResultsSchema(StrictBaseModel):
    results: list[GradingResult] = Field(min_length=1)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(text.lower())
        if len(token) >= _MIN_TOKEN_LENGTH
    }


def _coverage(summary_tokens: set[str], prompt_tokens: set[str]) -> float:
    if not summary_tokens:
        return 0.0
    return len(summary_tokens & prompt_tokens) / len(summary_tokens)


class LocalGradingEvaluator:
    async def __call__(
        self, variant: PromptVariant, calibration: CalibrationSet
    ) -> list[GradingResult]:
        prompt = " ".join([variant.system_instruction, *variant.few_shots])
        prompt_tokens = _tokens(prompt)
        results: list[GradingResult] = []
        for sample in calibration:
            coverage = _coverage(_tokens(sample.submission_summary), prompt_tokens)
            ceilings = sample.max_scores_by_criterion
            scores = [
                CriterionScore(
                    criterion_id=expected.criterion_id,
                    score=self._criterion_score(ceilings[expected.criterion_id], coverage),
                    comment=(
                        f"lexical alignment {coverage:.2f} with deployed grading "
                        f"prompt for criterion {expected.criterion_id}"
                    ),
                    confidence=min(1.0, 0.5 + coverage / 2),
                )
                for expected in sample.expected
            ]
            total = sum(score.score for score in scores)
            ceiling_total = sum(ceilings.values()) or 1.0
            results.append(
                GradingResult(
                    submission_id=sample.submission_id,
                    criterion_scores=scores,
                    total_score=round(total, 2),
                    percentage=round(100.0 * total / ceiling_total, 2),
                    feedback=(
                        f"{LOCAL_EVALUATOR_PROVENANCE} alignment {coverage:.2f} "
                        f"for submission {sample.submission_id}"
                    ),
                )
            )
        return results

    @staticmethod
    def _criterion_score(ceiling: float, coverage: float) -> float:
        factor = min(1.0, _BASE_COVERAGE + (1.0 - _BASE_COVERAGE) * coverage)
        return round(ceiling * factor, 2)


class AdkSummaryGradingEvaluator:
    def __init__(self, model: str) -> None:
        if not model.strip():
            raise ValueError("model must not be blank")
        self._model = model

    async def __call__(
        self, variant: PromptVariant, calibration: CalibrationSet
    ) -> list[GradingResult]:
        agent = build_structured_agent(
            name="calibration_grader",
            model=self._model,
            instruction=variant.system_instruction,
            output_schema=GradingResultsSchema,
            temperature=CALIBRATION_EVALUATOR_TEMPERATURE,
        )
        schema = await run_structured_output(
            agent=agent,
            payload=_evaluation_payload(variant, calibration),
            schema=GradingResultsSchema,
            app_name=CALIBRATION_EVALUATOR_APP,
            user_id="meta-optimizer",
        )
        graded = {result.submission_id for result in schema.results}
        missing = sorted(set(calibration.submission_ids) - graded)
        if missing:
            raise StructuredLlmError(
                f"grading evaluator skipped calibration submissions: {missing}",
                raw="",
                cause=RuntimeError(missing),
            )
        return list(schema.results)


def _evaluation_payload(variant: PromptVariant, calibration: CalibrationSet) -> str:
    payload = {
        "few_shots": list(variant.few_shots),
        "submissions": [
            {
                "submission_id": sample.submission_id,
                "submission_summary": sample.submission_summary,
                "criteria": [
                    {"criterion_id": criterion_id, "max_score": ceiling}
                    for criterion_id, ceiling in sample.max_scores_by_criterion.items()
                ],
            }
            for sample in calibration
        ],
        "rules": [
            "score every criterion of every submission",
            "scores must stay between 0 and the criterion max_score",
            "justify every score from the submission summary",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_calibration_evaluator(
    settings: Settings | None = None,
) -> VariantEvaluator:
    resolved = settings if settings is not None else get_settings()
    if resolved.local_mode:
        return LocalGradingEvaluator()
    return AdkSummaryGradingEvaluator(resolved.gemini_pro_model)

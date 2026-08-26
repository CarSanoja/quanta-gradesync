import json
import re

from pydantic import Field

from autocurricula.agents.adk_llm import build_structured_agent, run_structured_output
from autocurricula.agents.audit_samples import MAPPING_ITEM_MAX_SCORE
from autocurricula.config.settings import Settings, get_settings
from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.optimizer_engine import VariantEvaluator
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.grading import CriterionScore, GradingResult

AUDIT_EVALUATOR_APP = "autocurricula-audit-calibration"
AUDIT_EVALUATOR_TEMPERATURE = 0.0
LOCAL_AUDIT_PROVENANCE = "local-lexical-audit-evaluator"
_MIN_TOKEN_LENGTH = 3
_BASE_COVERAGE = 0.25
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class AuditMappingsSchema(StrictBaseModel):
    mappings: dict[str, list[str]] = Field(min_length=1)


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


class LocalAuditEvaluator:
    async def __call__(
        self, variant: PromptVariant, calibration: CalibrationSet
    ) -> list[GradingResult]:
        prompt_text = " ".join(
            [variant.system_instruction, *variant.few_shots]
        ).lower()
        prompt_tokens = _tokens(prompt_text)
        results: list[GradingResult] = []
        for sample in calibration:
            coverage = _coverage(_tokens(sample.submission_summary), prompt_tokens)
            scores = []
            for expected in sample.expected:
                cited = expected.criterion_id.lower() in prompt_text
                alignment = 0.5 * (1.0 if cited else 0.0) + 0.5 * coverage
                score = round(
                    MAPPING_ITEM_MAX_SCORE
                    * min(1.0, _BASE_COVERAGE + (1.0 - _BASE_COVERAGE) * alignment),
                    4,
                )
                scores.append(
                    CriterionScore(
                        criterion_id=expected.criterion_id,
                        score=score,
                        comment=(
                            f"mapping alignment {alignment:.2f} "
                            f"(cited={cited}, coverage={coverage:.2f}) "
                            f"for {expected.criterion_id}"
                        ),
                        confidence=min(1.0, 0.5 + alignment / 2),
                    )
                )
            results.append(
                GradingResult(
                    submission_id=sample.submission_id,
                    criterion_scores=scores,
                    total_score=round(sum(score.score for score in scores), 4),
                    percentage=round(
                        100.0
                        * sum(score.score for score in scores)
                        / max(1, len(scores)),
                        2,
                    ),
                    feedback=(
                        f"{LOCAL_AUDIT_PROVENANCE} alignment {coverage:.2f} "
                        f"for submission {sample.submission_id}"
                    ),
                )
            )
        return results


class AdkAuditEvaluator:
    def __init__(self, model: str) -> None:
        if not model.strip():
            raise ValueError("model must not be blank")
        self._model = model

    async def __call__(
        self, variant: PromptVariant, calibration: CalibrationSet
    ) -> list[GradingResult]:
        agent = build_structured_agent(
            name="audit_calibration_auditor",
            model=self._model,
            instruction=variant.system_instruction,
            output_schema=AuditMappingsSchema,
            temperature=AUDIT_EVALUATOR_TEMPERATURE,
        )
        schema = await run_structured_output(
            agent=agent,
            payload=_audit_payload(calibration),
            schema=AuditMappingsSchema,
            app_name=AUDIT_EVALUATOR_APP,
            user_id="meta-optimizer",
        )
        return agreement_results(schema.mappings, calibration)


def _audit_payload(calibration: CalibrationSet) -> str:
    return json.dumps(
        {
            "submissions": [
                {
                    "submission_id": sample.submission_id,
                    "submission_summary": sample.submission_summary,
                    "expected_criteria": sorted(sample.max_scores_by_criterion),
                }
                for sample in calibration
            ],
            "rules": [
                "map every criterion of every submission to competency codes",
                "use only codes mentioned in the submission summaries",
                "key the mappings object by criterion id",
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def agreement_results(
    mappings: dict[str, list[str]], calibration: CalibrationSet
) -> list[GradingResult]:
    results: list[GradingResult] = []
    for sample in calibration:
        merged: dict[str, set[str]] = {}
        for item in sample.expected:
            criterion_id, _, code = item.criterion_id.partition("->")
            merged.setdefault(criterion_id, set()).add(code)
        predicted: dict[str, set[str]] = {}
        for criterion_id, codes in mappings.items():
            normalized = criterion_id.partition("->")[0]
            predicted.setdefault(normalized, set()).update(codes)
        scores = []
        for item in sample.expected:
            criterion_id, _, _ = item.criterion_id.partition("->")
            expected_codes = merged.get(criterion_id, set())
            predicted_codes = predicted.get(criterion_id, set())
            if expected_codes:
                union = expected_codes | predicted_codes
                agreement = len(expected_codes & predicted_codes) / len(union)
            else:
                agreement = 0.0
            scores.append(
                CriterionScore(
                    criterion_id=item.criterion_id,
                    score=round(agreement, 4),
                    comment=f"jaccard agreement for mapping {item.criterion_id}",
                    confidence=0.9,
                )
            )
        results.append(
            GradingResult(
                submission_id=sample.submission_id,
                criterion_scores=scores,
                total_score=round(sum(score.score for score in scores), 4),
                percentage=round(
                    100.0 * sum(score.score for score in scores) / max(1, len(scores)),
                    2,
                ),
                feedback=f"adk audit agreement for {sample.submission_id}",
            )
        )
    return results


def build_audit_evaluator(
    settings: Settings | None = None,
) -> VariantEvaluator:
    resolved = settings if settings is not None else get_settings()
    if resolved.local_mode:
        return LocalAuditEvaluator()
    return AdkAuditEvaluator(resolved.gemini_flash_model)

import json
from typing import Any, Protocol, runtime_checkable

from autocurricula.agents.audit_response import AuditResponse
from autocurricula.agents.gemini_retry import client_http_options
from autocurricula.agents.local_auditor import LocalCurriculumAuditor
from autocurricula.agents.prompts.auditor_prompts import build_auditor_variant
from autocurricula.config.settings import Settings
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.curriculum import CurriculumAuditResult, CurriculumStandard
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.memory import RetrievedContext

AUDITOR_MAX_ATTEMPTS = 3
AUDITOR_TEMPERATURE = 0.0
AUDITOR_RETRY_CORRECTION = (
    "CORRECTION: your previous reply was invalid: {error}. "
    "Return only a corrected audit JSON object with submission_id {submission_id}, "
    "a mappings array of objects with criterion_id and competency_codes, and notes."
)


class AuditError(RuntimeError):
    def __init__(self, message: str, attempts: int) -> None:
        super().__init__(f"{message} [attempts={attempts}]")
        self.attempts = attempts


@runtime_checkable
class CurriculumAuditor(Protocol):
    async def audit(
        self,
        result: GradingResult,
        standard: CurriculumStandard,
        context: RetrievedContext,
    ) -> CurriculumAuditResult: ...


def build_audit_request(
    result: GradingResult,
    standard: CurriculumStandard,
    context: RetrievedContext,
) -> dict[str, Any]:
    return {
        "grading_result": result.model_dump(mode="json"),
        "curriculum_standard": standard.model_dump(mode="json"),
        "retrieved_context": context.model_dump(mode="json"),
    }


def sanitize_audit_result(
    audit: CurriculumAuditResult,
    standard: CurriculumStandard,
    submission_id: str,
) -> CurriculumAuditResult:
    valid_codes = {competency.code for competency in standard.competencies}
    mappings = {
        criterion_id: sorted({code for code in codes if code in valid_codes})
        for criterion_id, codes in audit.mappings.items()
    }
    mappings = {
        criterion_id: codes
        for criterion_id, codes in mappings.items()
        if codes
    }
    covered = sorted({code for codes in mappings.values() for code in codes})
    missing = sorted(valid_codes - set(covered))
    return CurriculumAuditResult(
        submission_id=submission_id,
        mappings=mappings,
        covered_codes=covered,
        missing_codes=missing,
        notes=audit.notes,
    )


def _compose_instruction(variant: PromptVariant) -> str:
    instruction = variant.system_instruction
    if variant.few_shots:
        examples = "\n".join(f"- {shot}" for shot in variant.few_shots)
        instruction = f"{instruction}\n\nREFERENCE EXAMPLES:\n{examples}"
    return instruction


class AdkCurriculumAuditor:
    def __init__(
        self,
        client: Any,
        model_id: str,
        *,
        max_attempts: int = AUDITOR_MAX_ATTEMPTS,
        variant: PromptVariant | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if not model_id:
            raise ValueError("model_id must be a non-empty string")
        self._client = client
        self._model_id = model_id
        self._max_attempts = max_attempts
        self._variant = variant if variant is not None else build_auditor_variant()
        self._instruction = _compose_instruction(self._variant)

    @property
    def variant(self) -> PromptVariant:
        return self._variant

    @property
    def model_id(self) -> str:
        return self._model_id

    async def audit(
        self,
        result: GradingResult,
        standard: CurriculumStandard,
        context: RetrievedContext,
    ) -> CurriculumAuditResult:
        payload = build_audit_request(result, standard, context)
        contents = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        correction = ""
        failures: list[str] = []
        for attempt in range(1, self._max_attempts + 1):
            response = await self._generate(contents=f"{contents}{correction}")
            try:
                parsed = self._extract(response)
            except ValueError as error:
                failures.append(f"attempt {attempt}: {error}")
                correction = "\n\n" + AUDITOR_RETRY_CORRECTION.format(
                    error=error, submission_id=result.submission_id
                )
                continue
            return sanitize_audit_result(parsed, standard, result.submission_id)
        raise AuditError("; ".join(failures), self._max_attempts)

    async def _generate(self, *, contents: str) -> Any:
        from google.genai import types

        from autocurricula.core.telemetry.usage import record_usage

        config = types.GenerateContentConfig(
            system_instruction=self._instruction,
            response_mime_type="application/json",
            response_schema=AuditResponse,
            temperature=AUDITOR_TEMPERATURE,
        )
        response = await self._client.aio.models.generate_content(
            model=self._model_id,
            contents=contents,
            config=config,
        )
        record_usage(getattr(response, "usage_metadata", None))
        return response

    @staticmethod
    def _extract(response: Any) -> CurriculumAuditResult:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, CurriculumAuditResult):
            return parsed
        if isinstance(parsed, AuditResponse):
            return parsed.to_audit_result()
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("response carried neither parsed schema output nor text")
        try:
            return AuditResponse.model_validate_json(text).to_audit_result()
        except ValueError:
            return CurriculumAuditResult.model_validate_json(text)


def _build_gemini_client(settings: Settings) -> Any:
    from google import genai

    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gemini_location,
        http_options=client_http_options(),
    )


def build_curriculum_auditor(settings: Settings) -> CurriculumAuditor:
    if settings.local_mode:
        return LocalCurriculumAuditor()
    return AdkCurriculumAuditor(
        client=_build_gemini_client(settings),
        model_id=settings.gemini_flash_model,
    )

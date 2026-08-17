import hashlib
import json

from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.grading import EvidenceSpan
from autocurricula.schemas.provenance import Provenance

__all__ = ["Provenance", "evidence_sha", "model_id_sha", "prompt_version_sha"]


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prompt_version_sha(variant: PromptVariant) -> str:
    canonical = json.dumps(
        {
            "variant_id": variant.variant_id,
            "version": variant.version,
            "system_instruction": variant.system_instruction,
            "few_shots": list(variant.few_shots),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return _sha256(canonical)


def evidence_sha(span: EvidenceSpan) -> str:
    canonical = json.dumps(
        {
            "page": span.page,
            "quote": span.quote,
            "rationale": span.rationale,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return _sha256(canonical)


def model_id_sha(model_id: str) -> str:
    return _sha256(f"model:{model_id}")

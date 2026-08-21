from typing import Any

from autocurricula.core.armor import InjectionDetector, resolve_injection_detector
from autocurricula.core.harness import SidecarTextProvider, sidecar_texts_from_batch
from autocurricula.core.orchestration.grade_guard import GradeGuard
from autocurricula.core.resilience import DeadLetterStore, SchemaRepairAgent
from autocurricula.core.telemetry import Recorder


def build_grade_guard(
    *,
    job_id: str,
    evaluator: Any,
    fallback: Any | None,
    latency_seconds: float,
    confidence_factor: float,
    repair_agent: SchemaRepairAgent | None,
    dead_letter: DeadLetterStore | None,
    dead_letter_max_attempts: int,
    model_id: str,
    recorder: Recorder | None,
    faithfulness_enabled: bool,
    batch: Any,
    armor_detector: InjectionDetector | None = None,
    armor_enabled: bool | None = None,
) -> GradeGuard:
    provider = (
        SidecarTextProvider(sidecar_texts_from_batch(batch))
        if faithfulness_enabled
        else None
    )
    armor = resolve_injection_detector(armor_detector, armor_enabled, batch)
    return GradeGuard(
        job_id=job_id,
        evaluator=evaluator,
        fallback=fallback,
        latency_seconds=latency_seconds,
        confidence_factor=confidence_factor,
        repair_agent=repair_agent,
        dead_letter=dead_letter,
        dead_letter_max_attempts=dead_letter_max_attempts,
        model_id=model_id,
        recorder=recorder,
        provider=provider,
        armor=armor,
    )

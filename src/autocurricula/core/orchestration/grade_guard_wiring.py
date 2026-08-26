from typing import Any

from autocurricula.core.armor import InjectionDetector, resolve_injection_detector
from autocurricula.core.harness import (
    DEFAULT_MATCH_THRESHOLD,
    CompositeTextProvider,
    PageTextProvider,
    SidecarTextProvider,
    TranscriptTextProvider,
    sidecar_texts_from_batch,
)
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
    transcripts: dict[tuple[str, int], str] | None = None,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> GradeGuard:
    provider = build_text_provider(
        faithfulness_enabled, batch, transcripts, match_threshold
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


def build_text_provider(
    faithfulness_enabled: bool,
    batch: Any,
    transcripts: dict[tuple[str, int], str] | None,
    match_threshold: float,
) -> PageTextProvider | None:
    if not faithfulness_enabled:
        return None
    sidecar = SidecarTextProvider(sidecar_texts_from_batch(batch))
    if not transcripts:
        return sidecar
    return CompositeTextProvider(
        sidecar, TranscriptTextProvider(transcripts, match_threshold)
    )

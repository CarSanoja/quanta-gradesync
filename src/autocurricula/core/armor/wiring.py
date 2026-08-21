import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

from autocurricula.config.settings import Settings, get_settings
from autocurricula.core.armor.legibility import batch_legibility, confidence_factor
from autocurricula.core.armor.prescreen import PrescreenedDetector
from autocurricula.core.armor.scripted import ScriptedInjectionDetector
from autocurricula.core.armor.transcripts import raw_provider_for
from autocurricula.core.harness import SidecarTextProvider, sidecar_texts_from_batch
from autocurricula.schemas.armor import ArmorBatchReport, ArmorVerdict
from autocurricula.schemas.exam import ExamBatch, ExamSubmission

logger = logging.getLogger(__name__)

ARMOR_RESULT_KEY = "armor_screen"


@runtime_checkable
class InjectionDetector(Protocol):
    async def screen(self, submission: ExamSubmission) -> ArmorVerdict: ...


def build_injection_detector(settings: Settings, batch: ExamBatch) -> InjectionDetector:
    if settings.local_mode:
        inner: Any = ScriptedInjectionDetector(
            SidecarTextProvider(sidecar_texts_from_batch(batch))
        )
    else:
        from autocurricula.core.armor.llm import LlmInjectionDetector

        inner = LlmInjectionDetector(settings)
    return PrescreenedDetector(inner, provider=raw_provider_for(batch))


def resolve_injection_detector(
    detector: InjectionDetector | None, enabled: bool | None, batch: ExamBatch
) -> InjectionDetector | None:
    if detector is not None:
        return detector
    settings = get_settings()
    if not (settings.armor_enabled if enabled is None else enabled):
        return None
    return build_injection_detector(settings, batch)


async def screen_submission(
    detector: InjectionDetector, submission: ExamSubmission
) -> ArmorVerdict:
    try:
        return await detector.screen(submission)
    except Exception as error:
        logger.warning(
            "armor screen failed open for submission %s: %s",
            submission.submission_id,
            error,
        )
        return ArmorVerdict(
            injection_detected=False,
            rationale=f"armor screen failed: {type(error).__name__}",
        )


def store_armor_report(
    session: Any, job_id: str, verdicts: dict[str, ArmorVerdict]
) -> ArmorBatchReport:
    report = ArmorBatchReport(job_id=job_id, verdicts=dict(verdicts))
    session.set_stage_result(ARMOR_RESULT_KEY, report)
    return report


def load_armor_report(session: Any) -> ArmorBatchReport | None:
    return session.get_stage_result(ARMOR_RESULT_KEY, ArmorBatchReport)


def flagged_students(
    report: ArmorBatchReport | None, batch: ExamBatch
) -> dict[str, str]:
    if report is None:
        return {}
    student_by_submission = {
        submission.submission_id: submission.student_id
        for submission in batch.submissions
    }
    flagged: dict[str, str] = {}
    for submission_id, verdict in report.verdicts.items():
        if not verdict.injection_detected:
            continue
        student_id = student_by_submission.get(submission_id)
        if student_id is None or student_id in flagged:
            continue
        flagged[student_id] = verdict.quoted_text or verdict.rationale
    return flagged


def injection_reason(quote: str) -> str:
    return f"prompt injection suspected: {quote}"


async def resolve_legibility(
    batch: ExamBatch,
    enabled: bool | None = None,
    full_trust: float | None = None,
    floor: float | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    settings = get_settings()
    if not (settings.legibility_enabled if enabled is None else enabled):
        return {}, {}
    trust = settings.legibility_full_trust if full_trust is None else full_trust
    minimum = settings.legibility_confidence_floor if floor is None else floor
    scores = await asyncio.to_thread(batch_legibility, batch)
    factors = {
        student_id: confidence_factor(score, full_trust=trust, floor=minimum)
        for student_id, score in scores.items()
    }
    return factors, scores

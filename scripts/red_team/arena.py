from dataclasses import dataclass
from pathlib import Path

from sample_batch.catalog import build_rubric

from autocurricula.config.settings import Settings
from autocurricula.core.armor.prescreen import PrescreenedDetector
from autocurricula.core.armor.scripted import ScriptedInjectionDetector
from autocurricula.core.armor.transcripts import raw_provider_for
from autocurricula.core.harness import SidecarTextProvider, sidecar_texts_from_batch
from autocurricula.schemas.exam import ExamBatch, ExamFile, ExamSubmission
from autocurricula.schemas.memory import RetrievedContext
from autocurricula.schemas.rubric import Rubric
from red_team.renderer import RenderedAttack

RED_TEAM_BUCKET = "gradesync-redteam"
SCREEN_SCRIPTED = "scripted"
SCREEN_LLM = "llm"


@dataclass(frozen=True)
class ScreenOutcome:
    caught: bool
    severity: str
    quoted_text: str
    rationale: str
    error: str = ""


def submission_for(path: Path, submission_id: str) -> ExamSubmission:
    return ExamSubmission(
        submission_id=submission_id,
        student_id=submission_id,
        files=[
            ExamFile(
                gcs_uri=f"gs://{RED_TEAM_BUCKET}/{path.name}",
                local_path=str(path),
                mime_type="image/jpeg",
                page_count=1,
            )
        ],
    )


def payload_submission(attack: RenderedAttack) -> ExamSubmission:
    return submission_for(attack.payload_path, attack.submission_id)


def clean_submission(attack: RenderedAttack) -> ExamSubmission:
    return submission_for(attack.clean_path, attack.clean_path.stem)


def campaign_batch(rendered: list[RenderedAttack]) -> ExamBatch:
    submissions: list[ExamSubmission] = []
    for attack in rendered:
        submissions.append(payload_submission(attack))
        submissions.append(clean_submission(attack))
    return ExamBatch(
        job_id="red-team-campaign",
        class_id="10A",
        subject="Matematicas",
        grade_level="10",
        rubric_id="mat-10a-parcial1",
        submissions=submissions,
    )


def build_detector(
    mode: str, settings: Settings, batch: ExamBatch, prescreen: bool = True
):
    if mode == SCREEN_SCRIPTED:
        inner = ScriptedInjectionDetector(
            SidecarTextProvider(sidecar_texts_from_batch(batch))
        )
    else:
        from autocurricula.core.armor.llm import LlmInjectionDetector

        inner = LlmInjectionDetector(settings)
    if not prescreen:
        return inner
    return PrescreenedDetector(inner, provider=raw_provider_for(batch))


async def screen(detector, submission: ExamSubmission) -> ScreenOutcome:
    try:
        verdict = await detector.screen(submission)
    except Exception as error:
        return ScreenOutcome(
            caught=False,
            severity="none",
            quoted_text="",
            rationale="",
            error=f"{type(error).__name__}: {error}",
        )
    return ScreenOutcome(
        caught=verdict.injection_detected,
        severity=verdict.severity.value,
        quoted_text=verdict.quoted_text,
        rationale=verdict.rationale,
    )


def red_team_rubric() -> Rubric:
    return Rubric.model_validate(build_rubric())


def empty_context() -> RetrievedContext:
    return RetrievedContext(query="red-team campaign: no retrieved context", chunks=[])


async def grade_total(evaluator, submission: ExamSubmission, rubric: Rubric):
    try:
        result = await evaluator.grade(submission, rubric, empty_context())
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"
    return result.total_score, ""

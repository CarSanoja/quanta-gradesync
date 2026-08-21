from dataclasses import dataclass
from pathlib import Path

from sample_batch.catalog import build_rubric

from autocurricula.config.settings import Settings
from autocurricula.core.armor.scripted import ScriptedInjectionDetector
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


def campaign_batch(rendered: list[RenderedAttack]) -> ExamBatch:
    submissions: list[ExamSubmission] = []
    for attack in rendered:
        submissions.append(submission_for(attack.payload_path, attack.submission_id))
        submissions.append(
            submission_for(attack.clean_path, f"{attack.submission_id}--clean")
        )
    return ExamBatch(
        job_id="red-team-campaign",
        class_id="10A",
        subject="Matematicas",
        grade_level="10",
        rubric_id="mat-10a-parcial1",
        submissions=submissions,
    )


def build_detector(mode: str, settings: Settings, batch: ExamBatch):
    if mode == SCREEN_SCRIPTED:
        return ScriptedInjectionDetector(
            SidecarTextProvider(sidecar_texts_from_batch(batch))
        )
    from autocurricula.core.armor.llm import LlmInjectionDetector

    return LlmInjectionDetector(settings)


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

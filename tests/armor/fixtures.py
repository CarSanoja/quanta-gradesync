from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from autocurricula.schemas.exam import ExamBatch, ExamFile, ExamSubmission
from autocurricula.schemas.grading import CriterionScore, EvidenceSpan, GradingResult

PAGE_LINE = "x^2 + x - 6 = (x+3)(x-2)  check: expand the product"


def render_page(blur: float = 0.0, contrast: float = 1.0) -> Image.Image:
    canvas = Image.new("L", (1200, 1600), 250)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=48)
    for index in range(28):
        draw.text((60, 30 + index * 55), PAGE_LINE, fill=10, font=font)
    if blur > 0:
        canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    if contrast != 1.0:
        canvas = ImageEnhance.Contrast(canvas).enhance(contrast)
    return canvas


def save_page(target: Path, blur: float = 0.0, contrast: float = 1.0) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    render_page(blur=blur, contrast=contrast).save(target, format="JPEG", quality=85)
    return target


def make_submission(
    student_id: str, local_path: str | None, page_count: int = 1
) -> ExamSubmission:
    return ExamSubmission(
        submission_id=student_id,
        student_id=student_id,
        files=[
            ExamFile(
                gcs_uri=f"gs://armor-tests/batch/{student_id}.jpg",
                local_path=local_path,
                mime_type="image/jpeg",
                page_count=page_count,
            )
        ],
    )


def make_batch(submissions: list[ExamSubmission]) -> ExamBatch:
    return ExamBatch(
        job_id="job-armor-001",
        class_id="10A",
        subject="matematicas",
        grade_level="grade-10",
        rubric_id="rub-armor-1",
        submissions=submissions,
    )


def make_result(
    submission_id: str, confidence: float, with_evidence: bool = True
) -> GradingResult:
    evidence = (
        [EvidenceSpan(page=1, quote=f"answer of {submission_id}", rationale="matches")]
        if with_evidence
        else []
    )
    return GradingResult(
        submission_id=submission_id,
        criterion_scores=[
            CriterionScore(
                criterion_id="crit-a",
                score=3.6,
                comment="assessed",
                evidence=evidence,
                confidence=confidence,
            )
        ],
        total_score=3.6,
        percentage=90.0,
        feedback=f"feedback for {submission_id}",
    )

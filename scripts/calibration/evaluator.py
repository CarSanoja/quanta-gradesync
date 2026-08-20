import asyncio
import time
from pathlib import Path

from autocurricula.agents.grading_agent import AdkGradingEvaluator
from autocurricula.config.settings import Settings
from autocurricula.core.evolution.calibration_store import (
    CalibrationSample,
    CalibrationSet,
)
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.telemetry.usage import usage_scope
from autocurricula.schemas.exam import ExamFile, ExamSubmission
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.memory import RetrievedContext
from autocurricula.schemas.rubric import Rubric

VariantKey = tuple[str, tuple[str, ...]]


class SubmissionIdMismatch(RuntimeError):
    pass


class MultimodalCalibrationEvaluator:
    def __init__(
        self,
        settings: Settings,
        rubric: Rubric,
        image_paths: dict[str, Path],
        *,
        max_concurrency: int = 4,
    ) -> None:
        self._settings = settings
        self._rubric = rubric
        self._images = image_paths
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._cache: dict[VariantKey, list[GradingResult]] = {}
        self.call_log: list[dict] = []

    @property
    def model(self) -> str:
        return self._settings.gemini_pro_model

    async def __call__(
        self, variant: PromptVariant, calibration: CalibrationSet
    ) -> list[GradingResult]:
        key: VariantKey = (variant.system_instruction, tuple(variant.few_shots))
        cached = self._cache.get(key)
        if cached is not None:
            self.call_log.append(
                {
                    "variant_version": variant.version,
                    "provenance": variant.provenance,
                    "cached": True,
                    "grading_calls": 0,
                }
            )
            return list(cached)
        grader = AdkGradingEvaluator(self._settings, variant=variant)
        started = time.perf_counter()
        sample_rows: list[dict] = []
        with usage_scope() as ledger:
            results = await asyncio.gather(
                *(
                    self._grade_sample(grader, sample, sample_rows)
                    for sample in calibration
                )
            )
        self._cache[key] = list(results)
        self.call_log.append(
            {
                "variant_version": variant.version,
                "provenance": variant.provenance,
                "cached": False,
                "seconds": round(time.perf_counter() - started, 2),
                "grading_calls": ledger.calls,
                "input_tokens": ledger.input_tokens,
                "output_tokens": ledger.output_tokens,
                "samples": sorted(sample_rows, key=lambda row: row["submission_id"]),
            }
        )
        return list(results)

    async def _grade_sample(
        self,
        grader: AdkGradingEvaluator,
        sample: CalibrationSample,
        sample_rows: list[dict],
    ) -> GradingResult:
        submission = self._submission(sample.submission_id)
        context = RetrievedContext(
            query=f"calibration grading for rubric {self._rubric.rubric_id}",
            chunks=[],
        )
        started = time.perf_counter()
        async with self._semaphore:
            with usage_scope() as ledger:
                result = await grader.grade(submission, self._rubric, context)
                if result.submission_id != sample.submission_id:
                    result = await grader.grade(submission, self._rubric, context)
        if result.submission_id != sample.submission_id:
            raise SubmissionIdMismatch(
                f"grading returned submission_id {result.submission_id!r} "
                f"for sample {sample.submission_id!r}"
            )
        sample_rows.append(
            {
                "submission_id": sample.submission_id,
                "seconds": round(time.perf_counter() - started, 2),
                "input_tokens": ledger.input_tokens,
                "output_tokens": ledger.output_tokens,
                "scores": {
                    score.criterion_id: score.score
                    for score in result.criterion_scores
                },
                "confidences": {
                    score.criterion_id: score.confidence
                    for score in result.criterion_scores
                },
                "total_score": result.total_score,
            }
        )
        return result

    def _submission(self, submission_id: str) -> ExamSubmission:
        path = self._images[submission_id]
        return ExamSubmission(
            submission_id=submission_id,
            student_id=submission_id,
            files=[
                ExamFile(
                    gcs_uri=f"gs://calibration-local/{submission_id}.jpg",
                    local_path=str(path),
                    mime_type="image/jpeg",
                    page_count=1,
                )
            ],
        )

import json
from pathlib import Path

from autocurricula.core.evolution.calibration_store import (
    CalibrationSample,
    CalibrationSet,
)
from autocurricula.schemas.grading import CriterionScore
from autocurricula.schemas.rubric import Rubric

CATALOG_NAME = "catalog-defaults.json"
GROUND_TRUTH_NAME = "ground_truth.json"
BATCHES_DIR = "batches"


class CalibrationBatch:
    def __init__(
        self,
        calibration: CalibrationSet,
        rubric: Rubric,
        image_paths: dict[str, Path],
        lot_code: str,
    ) -> None:
        self.calibration = calibration
        self.rubric = rubric
        self.image_paths = image_paths
        self.lot_code = lot_code


def load_rubric(batch_root: Path) -> Rubric:
    payload = json.loads((batch_root / CATALOG_NAME).read_text(encoding="utf-8"))
    bindings = payload.get("bindings", [])
    if not bindings:
        raise ValueError(f"{CATALOG_NAME} carries no bindings under {batch_root}")
    return Rubric.model_validate(bindings[0]["rubric"])


def _expected_scores(
    student: dict, criterion_ids: list[str]
) -> list[CriterionScore]:
    scores = student["criterion_scores"]
    missing = sorted(set(criterion_ids) - set(scores))
    if missing:
        raise ValueError(
            f"student {student['submission_id']} lacks human scores for {missing}"
        )
    return [
        CriterionScore(
            criterion_id=criterion_id,
            score=float(scores[criterion_id]),
            comment=f"human calibration score for {criterion_id}",
            confidence=1.0,
        )
        for criterion_id in criterion_ids
    ]


def load_batch(batch_root: Path) -> CalibrationBatch:
    root = batch_root.resolve()
    rubric = load_rubric(root)
    truth = json.loads((root / GROUND_TRUTH_NAME).read_text(encoding="utf-8"))
    lot_code = truth["lot_code"]
    pages_dir = root / BATCHES_DIR / lot_code
    criterion_ids = [criterion.criterion_id for criterion in rubric.criteria]
    ceilings = [
        float(truth["max_scores"][criterion_id]) for criterion_id in criterion_ids
    ]
    samples: list[CalibrationSample] = []
    image_paths: dict[str, Path] = {}
    for student in truth["students"]:
        submission_id = student["submission_id"]
        page = pages_dir / f"{submission_id}.jpg"
        if not page.is_file():
            raise FileNotFoundError(f"page image missing for {submission_id}: {page}")
        image_paths[submission_id] = page
        samples.append(
            CalibrationSample(
                submission_id=submission_id,
                submission_summary=student["notes"],
                criterion_ids=list(criterion_ids),
                max_scores=list(ceilings),
                expected=_expected_scores(student, criterion_ids),
            )
        )
    if not samples:
        raise ValueError(f"no human-graded students found in {root / GROUND_TRUTH_NAME}")
    return CalibrationBatch(CalibrationSet(samples), rubric, image_paths, lot_code)


def write_samples(batch: CalibrationBatch, output_dir: Path) -> Path:
    directory = output_dir / "calibration"
    directory.mkdir(parents=True, exist_ok=True)
    for sample in batch.calibration:
        path = directory / f"{sample.submission_id}.json"
        path.write_text(sample.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return directory

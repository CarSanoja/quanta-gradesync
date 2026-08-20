from pathlib import Path

from autocurricula.schemas.exam import ExamBatch

NORMALIZED_WIDTH = 1000
SHARPNESS_REFERENCE = 500.0
CONTRAST_REFERENCE = 16.0
DEFAULT_FULL_TRUST_LEGIBILITY = 0.70
DEFAULT_CONFIDENCE_FLOOR = 0.50

LAPLACIAN_KERNEL = (0, 1, 0, 1, -4, 1, 0, 1, 0)


def legibility_score(path: str | Path) -> float | None:
    from PIL import Image, ImageFilter, ImageStat

    try:
        with Image.open(path) as source:
            image = source.convert("L")
    except (OSError, ValueError):
        return None
    height = max(1, round(image.height * NORMALIZED_WIDTH / image.width))
    image = image.resize((NORMALIZED_WIDTH, height), Image.LANCZOS)
    kernel = ImageFilter.Kernel((3, 3), list(LAPLACIAN_KERNEL), scale=1, offset=128)
    sharpness_variance = ImageStat.Stat(image.filter(kernel)).var[0]
    contrast = ImageStat.Stat(image).stddev[0]
    sharpness_component = min(1.0, sharpness_variance / SHARPNESS_REFERENCE)
    contrast_component = min(1.0, contrast / CONTRAST_REFERENCE)
    return (sharpness_component * contrast_component) ** 0.5


def confidence_factor(
    legibility: float | None,
    *,
    full_trust: float = DEFAULT_FULL_TRUST_LEGIBILITY,
    floor: float = DEFAULT_CONFIDENCE_FLOOR,
) -> float:
    if legibility is None:
        return 1.0
    if not 0.0 < full_trust <= 1.0:
        raise ValueError("full_trust must be in (0, 1]")
    if not 0.0 < floor <= 1.0:
        raise ValueError("floor must be in (0, 1]")
    bounded = min(1.0, max(0.0, legibility))
    if bounded >= full_trust:
        return 1.0
    return max(floor, bounded / full_trust)


def batch_legibility(batch: ExamBatch) -> dict[str, float]:
    scores: dict[str, float] = {}
    for submission in batch.submissions:
        page_scores = [
            score
            for file in submission.files
            if file.local_path is not None
            if (score := legibility_score(file.local_path)) is not None
        ]
        if not page_scores:
            continue
        worst = min(page_scores)
        current = scores.get(submission.student_id)
        scores[submission.student_id] = worst if current is None else min(current, worst)
    return scores

import argparse
import json
import sys
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sample_batch.catalog import (
    BATCH_PREFIX,
    JOB_ID,
    LOT_CODE,
    build_catalog_defaults,
    build_ground_truth,
    build_push_body,
)
from sample_batch.pages import compose_page
from sample_batch.roster import PROFILES, ground_truth_entries

DEFAULT_TARGET = Path(".local_data/sample_batch")
DEFAULT_SEED = 20260819
DEFAULT_QUALITY = 84
CATALOG_DEFAULTS_NAME = "catalog-defaults.json"
GROUND_TRUTH_NAME = "ground_truth.json"
PUSH_EVENT_NAME = "push-event.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a demo batch of scanned handwritten math exams that the local "
            "GradeSync pipeline can ingest without hand-editing. The target directory "
            "plays the role of the bucket root: its parent is the local staging dir and "
            "its name is the bucket name."
        )
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help=f"bucket root directory to populate (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"seed that makes handwriting and scan noise reproducible (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_QUALITY,
        choices=range(40, 101),
        metavar="40-100",
        help=f"JPEG quality of the generated pages (default: {DEFAULT_QUALITY})",
    )
    return parser.parse_args(argv)


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def render_pages(batch_dir: Path, seed: int, quality: int) -> list[Path]:
    batch_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for profile in PROFILES:
        rng = Random(f"{seed}:{profile.student_id}")
        page = compose_page(profile, rng)
        destination = batch_dir / f"{profile.student_id}.jpg"
        page.save(destination, format="JPEG", quality=quality, optimize=True)
        written.append(destination)
    return written


def generate(target: Path, seed: int, quality: int) -> dict[str, object]:
    root = target.resolve()
    pages = render_pages(root / BATCH_PREFIX, seed, quality)
    catalog_path = write_json(root / CATALOG_DEFAULTS_NAME, build_catalog_defaults())
    ground_truth_path = write_json(
        root / GROUND_TRUTH_NAME, build_ground_truth(ground_truth_entries())
    )
    push_event_path = write_json(root / PUSH_EVENT_NAME, build_push_body(root.name))
    return {
        "root": root,
        "pages": pages,
        "catalog": catalog_path,
        "ground_truth": ground_truth_path,
        "push_event": push_event_path,
    }


def report(result: dict[str, object]) -> None:
    root = result["root"]
    pages = result["pages"]
    print(f"batch root      {root}")
    print(f"lot code        {LOT_CODE}")
    print(f"job id          {JOB_ID}")
    print(f"exam pages      {len(pages)} JPEG files under {BATCH_PREFIX}")
    for profile in PROFILES:
        print(f"  - {profile.student_id:<14} {profile.quality}")
    print(f"catalog         {result['catalog'].name}")
    print(f"ground truth    {result['ground_truth'].name} ({len(ground_truth_entries())} students)")
    print(f"push event      {result['push_event'].name}")
    print()
    print("Ingest locally with:")
    print(f"  export GRADESYNC_GCS_LOCAL_STAGING_DIR={root.parent}")
    print(
        "  curl -sS -X POST http://localhost:8080/webhooks/pubsub "
        '-H "Authorization: Bearer $GRADESYNC_PUBSUB_PUSH_TOKEN" '
        f'-H "Content-Type: application/json" --data @{root / PUSH_EVENT_NAME}'
    )


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    report(generate(arguments.target, arguments.seed, arguments.quality))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

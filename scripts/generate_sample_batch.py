import argparse
import json
import sys
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sample_batch.catalog import build_catalog_defaults, build_ground_truth, build_push_body
from sample_batch.contact_sheet import build_contact_sheet
from sample_batch.demo_notes import build_demo_notes
from sample_batch.lots import LotSpec
from sample_batch.pages import compose_page
from sample_batch.profiles import StudentProfile
from sample_batch.rosters import (
    ROSTER_DEMO,
    ROSTER_NAMES,
    ROSTER_REFERENCE,
    SECTION_ROSTERS,
    ground_truth_for,
    lot_for,
    profiles_for,
)

DEFAULT_TARGETS = {
    ROSTER_REFERENCE: Path(".local_data/sample_batch"),
    ROSTER_DEMO: Path("docs/video/demo-batch"),
    # The three sections land side by side under one root, in the order the
    # teacher sends them.
    **{name: Path("docs/video/sections") / name for name in SECTION_ROSTERS},
}
DEFAULT_SEED = 20260819
DEFAULT_QUALITY = 84
CATALOG_DEFAULTS_NAME = "catalog-defaults.json"
GROUND_TRUTH_NAME = "ground_truth.json"
PUSH_EVENT_NAME = "push-event.json"
DEMO_NOTES_NAME = "demo-notes.md"
CONTACT_SHEET_NAME = "contact-sheet.png"


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
        "--roster",
        choices=ROSTER_NAMES,
        default=ROSTER_REFERENCE,
        help=(
            "which class to fabricate: 'reference' is the 16-page acceptance fixture, "
            "'demo' is the 36-page single-batch class, and the three 'section-*' "
            "rosters are the 36 papers each of one teacher's three sections "
            f"(default: {ROSTER_REFERENCE})"
        ),
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help=(
            "bucket root directory to populate "
            f"(default: {DEFAULT_TARGETS[ROSTER_REFERENCE]} for reference, "
            f"{DEFAULT_TARGETS[ROSTER_DEMO]} for demo)"
        ),
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
    arguments = parser.parse_args(argv)
    if arguments.target is None:
        arguments.target = DEFAULT_TARGETS[arguments.roster]
    return arguments


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def render_pages(
    batch_dir: Path,
    profiles: tuple[StudentProfile, ...],
    lot: LotSpec,
    seed: int,
    quality: int,
) -> list[Path]:
    batch_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for profile in profiles:
        rng = Random(f"{seed}:{profile.student_id}")
        page = compose_page(profile, rng, lot)
        destination = batch_dir / f"{profile.student_id}.jpg"
        page.save(destination, format="JPEG", quality=quality, optimize=True)
        written.append(destination)
    return written


def legibility_table(pages: list[Path]) -> dict[str, float]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from autocurricula.core.armor.legibility import legibility_score

    scores: dict[str, float] = {}
    for page in pages:
        score = legibility_score(page)
        if score is not None:
            scores[page.stem] = score
    return scores


def generate(roster: str, target: Path, seed: int, quality: int) -> dict[str, object]:
    root = target.resolve()
    profiles = profiles_for(roster)
    lot = lot_for(roster)
    pages = render_pages(root / lot.batch_prefix, profiles, lot, seed, quality)
    result: dict[str, object] = {
        "roster": roster,
        "lot": lot,
        "root": root,
        "profiles": profiles,
        "pages": pages,
        "catalog": write_json(root / CATALOG_DEFAULTS_NAME, build_catalog_defaults()),
        "push_event": write_json(root / PUSH_EVENT_NAME, build_push_body(root.name, lot)),
    }
    entries = ground_truth_for(roster)
    if entries:
        result["ground_truth"] = write_json(
            root / GROUND_TRUTH_NAME, build_ground_truth(entries, lot)
        )
    if roster == ROSTER_DEMO or roster in SECTION_ROSTERS:
        scores = legibility_table(pages)
        result["scores"] = scores
        notes = root / DEMO_NOTES_NAME
        notes.write_text(build_demo_notes(profiles, lot, scores), encoding="utf-8")
        result["notes"] = notes
        sheet = root / CONTACT_SHEET_NAME
        build_contact_sheet(pages).save(sheet, format="PNG", optimize=True)
        result["contact_sheet"] = sheet
    return result


def report(result: dict[str, object]) -> None:
    lot: LotSpec = result["lot"]
    pages = result["pages"]
    scores: dict[str, float] = result.get("scores", {})
    print(f"roster          {result['roster']}")
    print(f"batch root      {result['root']}")
    print(f"lot code        {lot.lot_code}")
    print(f"job id          {lot.job_id}")
    print(f"exam pages      {len(pages)} JPEG files under {lot.batch_prefix}")
    for profile in result["profiles"]:
        score = f"{scores[profile.student_id]:.3f}" if profile.student_id in scores else "-"
        print(f"  - {profile.student_id:<22} {profile.quality:<26} {score:>6}  {profile.expected}")
    print(f"catalog         {result['catalog'].name}")
    if "ground_truth" in result:
        print(f"ground truth    {result['ground_truth'].name}")
    if "notes" in result:
        print(f"demo notes      {result['notes'].name}")
        print(f"contact sheet   {result['contact_sheet'].name}")
    print(f"push event      {result['push_event'].name}")
    print()
    print("Ingest locally with:")
    print(f"  export GRADESYNC_GCS_LOCAL_STAGING_DIR={result['root'].parent}")
    print(
        "  curl -sS -X POST http://localhost:8080/webhooks/pubsub "
        '-H "Authorization: Bearer $GRADESYNC_PUBSUB_PUSH_TOKEN" '
        f'-H "Content-Type: application/json" --data @{result["root"] / PUSH_EVENT_NAME}'
    )


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    report(generate(arguments.roster, arguments.target, arguments.seed, arguments.quality))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

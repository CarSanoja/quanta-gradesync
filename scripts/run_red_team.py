import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from red_team.arena import SCREEN_LLM, SCREEN_SCRIPTED  # noqa: E402
from red_team.campaign import CampaignConfig, run_campaign  # noqa: E402
from red_team.generator import (  # noqa: E402
    DEFAULT_GEMMA_MODEL,
    GemmaAttackGenerator,
    ScriptedAttackGenerator,
)
from red_team.report import build_payload, write_reports  # noqa: E402
from red_team.scoring import score_campaign  # noqa: E402
from red_team.taxonomy import (  # noqa: E402
    ATTACK_CLASSES,
    DEFAULT_CLASSES,
    resolve_classes,
)

from autocurricula.config.genai_env import configure_genai_env  # noqa: E402
from autocurricula.config.settings import Settings  # noqa: E402
from autocurricula.schemas.common import utc_now  # noqa: E402

API_KEY_VARS = ("GRADESYNC_GEMMA_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
DEFAULT_TARGET = Path(".local_data/red_team")
DEFAULT_REPORT = Path("docs/reports/red-team-latest")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    known = ", ".join(item.code for item in ATTACK_CLASSES)
    parser = argparse.ArgumentParser(
        description=(
            "Adversarial self-play campaign: a generator writes injection payloads, "
            "the deterministic renderer stamps them onto generated exam pages, and "
            "the production armor screener is scored against them with clean twins. "
            "Two generators are available: --scripted-generator replays the "
            "taxonomy corpus offline, and the default Gemma generator (Gemini "
            "Developer API) writes novel payloads when an API key with quota is "
            "configured. This is an offline campaign; it never touches the request "
            "path or the SIS."
        )
    )
    parser.add_argument(
        "--classes",
        default=",".join(DEFAULT_CLASSES),
        help=f"comma-separated attack classes (known: {known})",
    )
    parser.add_argument("--payloads-per-class", type=int, default=3)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument(
        "--screen",
        choices=(SCREEN_LLM, SCREEN_SCRIPTED),
        default=SCREEN_LLM,
        help="armor screener to score against (default: the production LLM screen)",
    )
    parser.add_argument("--gemma-model", default="")
    parser.add_argument(
        "--with-grading",
        action="store_true",
        help="also grade every payload page and its clean twin to measure grade movement",
    )
    parser.add_argument(
        "--budget-calls",
        type=int,
        default=60,
        help="hard cap on screening/grading model calls",
    )
    parser.add_argument(
        "--scripted-generator",
        action="store_true",
        help="use the offline scripted generator instead of Gemma",
    )
    parser.add_argument(
        "--no-prescreen",
        action="store_true",
        help=(
            "score the model screen alone, without the deterministic metadata and "
            "encoding prescreen that production runs in front of it"
        ),
    )
    parser.add_argument("--project", default=os.environ.get("GRADESYNC_GCP_PROJECT_ID", ""))
    return parser.parse_args(argv)


def resolve_api_key(settings: Settings) -> str:
    for name in API_KEY_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if settings.gemma_api_key.strip():
        return settings.gemma_api_key.strip()
    raise SystemExit(
        "no Gemma API key found; export GRADESYNC_GEMMA_API_KEY with the value of "
        "`gcloud secrets versions access latest --secret=gradesync-gemma-api-key "
        "--project=quanta-gradesync`, or pass --scripted-generator"
    )


def build_settings(arguments: argparse.Namespace) -> Settings:
    if arguments.screen == SCREEN_SCRIPTED and not arguments.with_grading:
        return Settings(local_mode=True, gcp_project_id="")
    if not arguments.project:
        raise SystemExit(
            "the LLM armor screen and grading need a real project; pass --project "
            "or export GRADESYNC_GCP_PROJECT_ID"
        )
    settings = Settings(local_mode=False, gcp_project_id=arguments.project)
    configure_genai_env(settings)
    return settings


def build_generator(arguments: argparse.Namespace, settings: Settings):
    if arguments.scripted_generator:
        return ScriptedAttackGenerator()
    model = arguments.gemma_model or settings.gemma_model or DEFAULT_GEMMA_MODEL
    return GemmaAttackGenerator(resolve_api_key(settings), model=model)


def report(payload: dict, json_path: Path, markdown_path: Path) -> None:
    totals = payload["totals"]
    if not payload["measurement_valid"]:
        print(
            f"INVALID RUN     the screen failed open on {totals['armor_errors']} "
            "payloads; the numbers below are not a measurement"
        )
    print(f"classes         {', '.join(payload['config']['classes'])}")
    print(f"generator       {payload['models']['generator']}")
    print(f"armor screen    {payload['models']['screen']}")
    print(
        f"catch rate      {totals['hostile_caught']}/{totals['hostile_attempted']}"
        f" hostile payloads caught"
    )
    print(
        f"false positives {totals['control_flagged']}/{totals['control_attempted']}"
        " controls flagged"
    )
    print(f"armor errors    {totals['armor_errors']}")
    print(f"cost            ${payload['usage']['estimated_cost_usd']:.4f}")
    for note in payload["notes"]:
        print(f"note            {note}")
    print(f"json            {json_path}")
    print(f"markdown        {markdown_path}")


async def run(arguments: argparse.Namespace) -> int:
    config = CampaignConfig(
        classes=tuple(resolve_classes(arguments.classes.split(","))),
        payloads_per_class=arguments.payloads_per_class,
        target=arguments.target,
        seed=arguments.seed,
        screen_mode=arguments.screen,
        with_grading=arguments.with_grading,
        budget_calls=arguments.budget_calls,
        prescreen=not arguments.no_prescreen,
    )
    settings = build_settings(arguments)
    result = await run_campaign(config, build_generator(arguments, settings), settings)
    payload = build_payload(
        config, result, score_campaign(result), utc_now().isoformat()
    )
    json_path, markdown_path = write_reports(payload, arguments.out)
    report(payload, json_path, markdown_path)
    return 0 if result.outcomes else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())

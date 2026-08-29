from pathlib import Path

CONFIG = Path("cloudbuild.yaml")
RUNBOOK = Path("docs/runbooks/deploy.md")


def config() -> str:
    return CONFIG.read_text(encoding="utf-8")


def deploy_args() -> list[str]:
    lines = [line.strip() for line in config().splitlines()]
    return [line[2:].strip() for line in lines if line.startswith("- --")]


def substitutions() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in config().splitlines():
        if not line.startswith("  _") or ":" not in line:
            continue
        name, _, value = line.partition(":")
        values[name.strip()] = value.strip().strip('"')
    return values


def test_the_deploy_keeps_cpu_allocated_outside_the_request() -> None:
    """Finding 6 of docs/reports/deploy-2026-08-19.md.

    The webhook acknowledges the Pub/Sub push and runs the pipeline in a
    background task. With request-scoped CPU that task is frozen the moment
    the response is sent, and Pub/Sub never retries a delivery it already
    acknowledged, so the job stalls at `fetched` forever. The flag lived only
    in the running service until 2026-08-27, which meant a clone of this
    repository could not reproduce a service that works.
    """
    assert "--no-cpu-throttling" in deploy_args()


def test_no_substitution_is_left_as_a_placeholder() -> None:
    for name, value in substitutions().items():
        assert value, name
        assert "your-" not in value, f"{name} is still a placeholder: {value}"


def test_gemini_stays_on_the_only_location_that_serves_it() -> None:
    assert substitutions()["_GEMINI_LOCATION"] == "global"


def test_the_push_token_is_mounted_from_secret_manager_never_inlined() -> None:
    text = config()

    assert "--set-secrets=GRADESYNC_PUBSUB_PUSH_TOKEN=${_PUSH_TOKEN_SECRET}:latest" in text
    assert "GRADESYNC_PUBSUB_PUSH_TOKEN=" not in text.split("--set-env-vars=")[1]


def test_the_deploy_runs_as_the_least_privilege_build_identity() -> None:
    assert (
        "serviceAccount: projects/quanta-gradesync/serviceAccounts/"
        "gradesync-builder@quanta-gradesync.iam.gserviceaccount.com" in config()
    )


def test_the_runbook_covers_what_a_deploy_rewrites() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "--no-cpu-throttling" in runbook
    assert "removes every existing environment variable first" in runbook
    assert "Roll back" in runbook
    assert "gcloud auth login" in runbook


def test_the_deploy_carries_the_memory_the_service_needs() -> None:
    """A deploy patches, so shipping 1Gi again would undo the fix silently.

    Three sections arriving together took the container past 1Gi and Cloud Run
    killed it four times in eighty seconds; Pub/Sub redelivered and each batch
    restarted from its checkpoint. That is what "everything got slower" was.
    """
    text = config()

    assert '_MEMORY: "2Gi"' in text
    assert "--memory=${_MEMORY}" in text
    assert "--memory=1Gi" not in text
    assert '_MAX_INSTANCES: "4"' in text

import argparse
import os
import subprocess
from typing import Any

from google.cloud import firestore
from google.oauth2.credentials import Credentials

# This machine carries two gcloud profiles, and the application-default
# credentials are a separate thing from the active CLI profile: the CLI can be
# pointed at quanta-gradesync while ADC still holds quanta-local, and Firestore
# answers PERMISSION_DENIED with no hint about which of the two is wrong. The
# CLI profile is the one the operator just chose, so borrow its token.
ACCESS_TOKEN_ENV = "GOOGLE_ACCESS_TOKEN"

# The fallback, for a credential that may not enumerate the database root. It is
# a floor, not the truth: assessment_facts and labels survived every reset for
# weeks because they were simply missing from this list, and a hand-maintained
# list of collections drifts the moment the code writes a new one.
KNOWN_COLLECTIONS = (
    "checkpoints",
    "reviews",
    "sis_records",
    "profiles",
    "competencies",
    "audit",
    "dead_letter",
    "jobs",
    "prompts",
    "assessment_facts",
    "labels",
)


def wipe_document(reference: Any, writer: Any) -> int:
    deleted = 0
    for sub in reference.collections():
        deleted += wipe_documents_in(sub, writer)
    writer.delete(reference)
    return deleted + 1


def wipe_documents_in(collection: Any, writer: Any) -> int:
    # list_documents, not stream: a parent that exists only to hold a
    # subcollection is not returned by a query, and audit/{job}/live is exactly
    # that. Streaming left thousands of live events behind on every reset.
    return sum(wipe_document(reference, writer) for reference in collection.list_documents())


def wipe_collection(db: firestore.Client, name: str) -> int:
    # A bulk writer batches and parallelises. One delete per round trip put a
    # live feed's worth of events — 1,456 documents on 2026-08-28 — past ten
    # minutes, which is the wrong thing to be waiting on before a recording.
    writer = db.bulk_writer()
    deleted = wipe_documents_in(db.collection(name), writer)
    writer.close()
    return deleted


class ReauthRequired(RuntimeError):
    """gcloud is installed and refused, which is not the same as absent."""


def cli_credentials() -> Credentials | None:
    token = os.environ.get(ACCESS_TOKEN_ENV)
    if token:
        return Credentials(token=token)
    try:
        finished = subprocess.run(
            ("gcloud", "auth", "print-access-token"),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        # No gcloud on this machine: a runner, a container. Fall through to ADC.
        return None
    if finished.returncode != 0:
        # gcloud is here and said no. Falling back to ADC would ask a second,
        # unrelated credential the same question and report its refusal instead,
        # which sends you looking at IAM for a problem that is an expired login.
        complaint = finished.stderr.strip().splitlines()
        raise ReauthRequired(
            "the active gcloud profile could not mint a token:\n"
            f"  {complaint[0] if complaint else 'unknown error'}\n"
            "Run `gcloud auth login` and try again, or pass --adc to use the "
            "application-default credentials instead."
        )
    token = finished.stdout.strip()
    return Credentials(token=token) if token else None


def open_client(project: str, use_cli_auth: bool) -> firestore.Client:
    credentials = cli_credentials() if use_cli_auth else None
    return firestore.Client(project=project, credentials=credentials)


def collections_to_wipe(db: firestore.Client) -> tuple[tuple[str, ...], bool]:
    """Ask the database what it holds; fall back to the list only if refused.

    "Wipe the database" has to mean the database, not the nine names somebody
    remembered to write down. Listing the root needs a permission the demo
    credential may not carry, so the list stays as a floor — but when the listing
    works it is authoritative, and anything new the engine starts writing is
    covered without a code change.
    """
    try:
        discovered = tuple(sorted(collection.id for collection in db.collections()))
    except Exception:
        return KNOWN_COLLECTIONS, False
    return tuple(sorted(set(discovered) | set(KNOWN_COLLECTIONS))), True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wipe all demo state from Firestore so judges open a clean console"
    )
    parser.add_argument("--project", default="quanta-gradesync")
    parser.add_argument("--yes", action="store_true", help="required to actually delete")
    parser.add_argument(
        "--adc",
        action="store_true",
        help="use application-default credentials instead of the active gcloud profile",
    )
    args = parser.parse_args()
    if not args.yes:
        parser.error("refusing to delete without --yes")
    try:
        db = open_client(args.project, use_cli_auth=not args.adc)
    except ReauthRequired as error:
        raise SystemExit(f"reset aborted: {error}") from None
    names, discovered = collections_to_wipe(db)
    if not discovered:
        print(
            "warning: this credential cannot list the database root, so only the "
            "known collections are wiped. Anything written outside them survives."
        )
    total = 0
    for name in names:
        count = wipe_collection(db, name)
        total += count
        print(f"{name}: {count} documents deleted")
    print(f"total: {total}")
    print("re-seed with one fresh run: POST /ingest/sample-batch on the deployed service")


if __name__ == "__main__":
    main()

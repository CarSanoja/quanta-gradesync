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

DEMO_COLLECTIONS = (
    "checkpoints",
    "reviews",
    "sis_records",
    "profiles",
    "competencies",
    "audit",
    "dead_letter",
    "jobs",
    "prompts",
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


def cli_credentials() -> Credentials | None:
    token = os.environ.get(ACCESS_TOKEN_ENV)
    if not token:
        try:
            token = subprocess.run(
                ("gcloud", "auth", "print-access-token"),
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    return Credentials(token=token) if token else None


def open_client(project: str, use_cli_auth: bool) -> firestore.Client:
    credentials = cli_credentials() if use_cli_auth else None
    return firestore.Client(project=project, credentials=credentials)


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
    db = open_client(args.project, use_cli_auth=not args.adc)
    total = 0
    for name in DEMO_COLLECTIONS:
        count = wipe_collection(db, name)
        total += count
        print(f"{name}: {count} documents deleted")
    print(f"total: {total}")
    print("re-seed with one fresh run: POST /ingest/sample-batch on the deployed service")


if __name__ == "__main__":
    main()

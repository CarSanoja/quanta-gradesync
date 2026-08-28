import argparse
from typing import Any

from google.cloud import firestore

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wipe all demo state from Firestore so judges open a clean console"
    )
    parser.add_argument("--project", default="quanta-gradesync")
    parser.add_argument("--yes", action="store_true", help="required to actually delete")
    args = parser.parse_args()
    if not args.yes:
        parser.error("refusing to delete without --yes")
    db = firestore.Client(project=args.project)
    total = 0
    for name in DEMO_COLLECTIONS:
        count = wipe_collection(db, name)
        total += count
        print(f"{name}: {count} documents deleted")
    print(f"total: {total}")
    print("re-seed with one fresh run: POST /ingest/sample-batch on the deployed service")


if __name__ == "__main__":
    main()

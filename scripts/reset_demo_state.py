import argparse

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


def wipe_collection(db: firestore.Client, name: str) -> int:
    deleted = 0
    for doc in db.collection(name).stream():
        for sub in doc.reference.collections():
            for child in sub.stream():
                child.reference.delete()
                deleted += 1
        doc.reference.delete()
        deleted += 1
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

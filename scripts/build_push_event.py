import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sample_batch.catalog import (
    BATCH_PREFIX,
    CLASS_ID,
    JOB_ID,
    SUBJECT,
    TRACE_ID,
    TRIGGERED_AT,
)

DEFAULT_SUBSCRIPTION = "projects/quanta-gradesync/subscriptions/exam-batch-ingest-push"
DEFAULT_MESSAGE_ID = "e2e-batch-message-1"
EVENT_TYPE = "OBJECT_FINALIZE"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Pub/Sub push body for POST /webhooks/pubsub that targets an exam "
            "batch already uploaded to a bucket. The payload carries the job event the "
            "engine parses; a raw GCS OBJECT_FINALIZE notification would need the same "
            "fields derived from the object path before it reaches the webhook."
        )
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", default=BATCH_PREFIX)
    parser.add_argument("--job-id", default=JOB_ID)
    parser.add_argument("--subject", default=SUBJECT)
    parser.add_argument("--class-id", default=CLASS_ID)
    parser.add_argument("--triggered-at", default=TRIGGERED_AT)
    parser.add_argument("--trace-id", default=TRACE_ID)
    parser.add_argument("--message-id", default=DEFAULT_MESSAGE_ID)
    parser.add_argument("--subscription", default=DEFAULT_SUBSCRIPTION)
    parser.add_argument("--object-id", default="")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def lot_code(prefix: str) -> str:
    segments = [segment for segment in prefix.split("/") if segment.strip()]
    if not segments:
        raise ValueError("prefix must contain at least one path segment")
    return segments[-1]


def build_job_event(arguments: argparse.Namespace) -> dict[str, str]:
    return {
        "bucket": arguments.bucket,
        "class_id": arguments.class_id,
        "exam_batch_prefix": arguments.prefix.strip("/"),
        "job_id": arguments.job_id,
        "subject": arguments.subject,
        "trace_id": arguments.trace_id,
        "triggered_at": arguments.triggered_at,
    }


def build_push_body(arguments: argparse.Namespace) -> dict[str, object]:
    prefix = arguments.prefix.strip("/")
    payload = json.dumps(build_job_event(arguments), sort_keys=True)
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    object_id = arguments.object_id or f"{prefix}/{lot_code(prefix)}.manifest"
    return {
        "message": {
            "messageId": arguments.message_id,
            "data": encoded,
            "attributes": {
                "bucketId": arguments.bucket,
                "eventType": EVENT_TYPE,
                "lot_code": lot_code(prefix),
                "objectId": object_id,
            },
        },
        "subscription": arguments.subscription,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    body = json.dumps(build_push_body(arguments), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(body)
        return 0
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(body, encoding="utf-8")
    print(f"push event written to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

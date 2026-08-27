import json
from pathlib import Path

import httpx

from autocurricula.core.review import LocalReviewStore, NotifyingReviewStore
from autocurricula.schemas.review import ReviewStatus
from tests.review.service_stack import make_item


async def test_new_pending_review_sends_one_external_notification(tmp_path: Path) -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = NotifyingReviewStore(
            LocalReviewStore(tmp_path),
            "https://notify.example.test/reviews",
            client=client,
        )
        item = make_item("job-notify:ana", "ana", "job-notify")
        await store.put(item)
        await store.put(item.model_copy(update={"rework_notes": ["checked again"]}))
        await store.put(item.model_copy(update={"status": ReviewStatus.APPROVED}))

    assert len(payloads) == 1
    assert payloads[0]["event"] == "gradesync.review.pending"
    assert payloads[0]["student_id"] == "ana"
    assert payloads[0]["reasons"] == item.reasons


async def test_notification_failure_never_loses_the_review(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        store = NotifyingReviewStore(
            LocalReviewStore(tmp_path),
            "https://notify.example.test/reviews",
            client=client,
        )
        item = make_item("job-notify:luis", "luis", "job-notify")
        await store.put(item)

    assert await store.get(item.review_id) == item

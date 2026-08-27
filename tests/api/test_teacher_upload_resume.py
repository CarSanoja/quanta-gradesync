from pathlib import Path

UPLOAD = Path("src/autocurricula/api/static/teacher-upload.js")


def test_naming_the_assessment_starts_the_sending_that_was_waiting_for_it() -> None:
    source = UPLOAD.read_text(encoding="utf-8")
    body = source[source.index("export function setLotField") : source.index("export function answerPair")]

    assert "runQueue(false)" in body, "filling the lot fields must resume the paused queue"
    assert body.index("uploads.awaitingLot") < body.index("runQueue(false)")


def test_the_queue_still_waits_when_the_assessment_is_incomplete() -> None:
    source = UPLOAD.read_text(encoding="utf-8")

    assert "const waiting = uploads.awaitingLot && lotCodeNow();" in source

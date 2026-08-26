from pathlib import Path
from typing import Any

import pytest

from autocurricula.api.live_sources import (
    ASCENDING,
    FIELD_SEQ,
    LIVE_DIRECTORY,
    event_seq,
    read_local_live_events,
    read_remote_live_events,
)
from autocurricula.config.settings import Settings
from autocurricula.schemas.live_events import LIVE_SUBCOLLECTION

JOB_ID = "job-live-source"
AUDIT_COLLECTION = "audit"


def payload(seq: int) -> dict[str, Any]:
    return {"seq": seq, "job_id": JOB_ID, "name": f"Stage_{seq}"}


class FakeSnapshot:
    def __init__(self, document: Any) -> None:
        self._document = document

    def to_dict(self) -> Any:
        return self._document


class FakeQuery:
    def __init__(self, documents: list[Any], calls: dict[str, Any]) -> None:
        self._documents = documents
        self.calls = calls

    def where(self, *args: Any, **kwargs: Any) -> "FakeQuery":
        field_filter = kwargs.get("filter")
        if field_filter is not None:
            self.calls["where"] = (
                field_filter.field_path,
                field_filter.op_string,
                field_filter.value,
            )
        else:
            self.calls["where"] = args
        threshold = self.calls["where"][2]
        kept = [
            document
            for document in self._documents
            if not isinstance(document, dict) or document.get(FIELD_SEQ, 0) > threshold
        ]
        return FakeQuery(kept, self.calls)

    def order_by(self, field_path: str, direction: str = ASCENDING) -> "FakeQuery":
        self.calls["order_by"] = (field_path, direction)
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.calls["limit"] = count
        return FakeQuery(self._documents[:count], self.calls)

    def stream(self):
        return (FakeSnapshot(document) for document in self._documents)


class FakeNode:
    def __init__(self, documents: list[Any], calls: dict[str, Any], path: list[str]) -> None:
        self._documents = documents
        self._calls = calls
        self.path = path

    def document(self, name: str) -> "FakeNode":
        return FakeNode(self._documents, self._calls, [*self.path, name])

    def collection(self, name: str) -> Any:
        path = [*self.path, name]
        if name == LIVE_SUBCOLLECTION:
            self._calls["path"] = tuple(path)
            return FakeQuery(self._documents, self._calls)
        return FakeNode(self._documents, self._calls, path)


class FakeFirestore:
    def __init__(self, documents: list[Any]) -> None:
        self.documents = documents
        self.calls: dict[str, Any] = {}

    def collection(self, name: str) -> FakeNode:
        return FakeNode(self.documents, self.calls, [name])


@pytest.fixture
def remote_settings(tmp_path: Path) -> Settings:
    return Settings(
        local_mode=False,
        gcp_project_id="quanta-gradesync",
        firestore_audit_collection=AUDIT_COLLECTION,
        local_data_dir=tmp_path / "local_data",
        gcs_local_staging_dir=tmp_path / "staging",
    )


def test_event_seq_rejects_non_integer_cursors() -> None:
    assert event_seq({"seq": 4}) == 4
    assert event_seq({"seq": True}) == 0
    assert event_seq({"seq": "4"}) == 0
    assert event_seq({}) == 0


def test_remote_reader_walks_the_live_subcollection(remote_settings: Settings) -> None:
    client = FakeFirestore([payload(seq) for seq in (1, 2, 3)])

    events = read_remote_live_events(remote_settings, JOB_ID, 0, 500, client=client)

    assert [event["seq"] for event in events] == [1, 2, 3]
    assert client.calls["path"] == (AUDIT_COLLECTION, JOB_ID, LIVE_SUBCOLLECTION)
    assert client.calls["where"] == (FIELD_SEQ, ">", 0)
    assert client.calls["order_by"] == (FIELD_SEQ, ASCENDING)
    assert client.calls["limit"] == 500


def test_remote_reader_applies_the_after_cursor_and_limit(
    remote_settings: Settings,
) -> None:
    client = FakeFirestore([payload(seq) for seq in (1, 2, 3, 4, 5)])

    events = read_remote_live_events(remote_settings, JOB_ID, 2, 2, client=client)

    assert [event["seq"] for event in events] == [3, 4]
    assert client.calls["where"] == (FIELD_SEQ, ">", 2)


def test_remote_reader_sorts_out_of_order_documents(remote_settings: Settings) -> None:
    client = FakeFirestore([payload(3), payload(1), payload(2)])

    events = read_remote_live_events(remote_settings, JOB_ID, 0, 500, client=client)

    assert [event["seq"] for event in events] == [1, 2, 3]


def test_remote_reader_drops_documents_that_are_not_dictionaries(
    remote_settings: Settings,
) -> None:
    client = FakeFirestore([payload(1), None, payload(2)])

    events = read_remote_live_events(remote_settings, JOB_ID, 0, 500, client=client)

    assert [event["seq"] for event in events] == [1, 2]


def test_remote_reader_requires_a_client(remote_settings: Settings) -> None:
    with pytest.raises(RuntimeError, match="firestore client"):
        read_remote_live_events(remote_settings, JOB_ID, 0, 500)


def test_local_reader_skips_blank_and_unparsable_lines(tmp_path: Path) -> None:
    settings = Settings(
        local_mode=True,
        gcp_project_id="",
        local_data_dir=tmp_path / "local_data",
        gcs_local_staging_dir=tmp_path / "staging",
    )
    directory = Path(settings.local_data_dir) / LIVE_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{JOB_ID}.jsonl").write_text(
        '{"seq": 2, "name": "Stage_grade"}\n\n{"seq": 1\n[1, 2]\n{"seq": 1, "name": "x"}\n',
        encoding="utf-8",
    )

    events = read_local_live_events(settings, JOB_ID, 0, 500)

    assert [event["seq"] for event in events] == [1, 2]


def test_local_reader_returns_nothing_for_an_unknown_job(tmp_path: Path) -> None:
    settings = Settings(
        local_mode=True,
        gcp_project_id="",
        local_data_dir=tmp_path / "local_data",
        gcs_local_staging_dir=tmp_path / "staging",
    )

    assert read_local_live_events(settings, "job-ghost", 0, 500) == []

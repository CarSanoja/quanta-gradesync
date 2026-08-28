import importlib.util
from pathlib import Path

SCRIPT = Path("scripts/reset_demo_state.py")


def load_script():
    spec = importlib.util.spec_from_file_location("reset_demo_state", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeWriter:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.closed = False

    def delete(self, reference) -> None:
        self.deleted.append(reference.path)

    def close(self) -> None:
        self.closed = True


class FakeDoc:
    def __init__(self, path: str, subcollections=()) -> None:
        self.path = path
        self._subs = list(subcollections)

    def collections(self):
        return list(self._subs)


class FakeCollection:
    def __init__(self, docs=()) -> None:
        self._docs = list(docs)

    def list_documents(self):
        return list(self._docs)

    def stream(self):
        # A phantom parent — a document that exists only to hold a
        # subcollection — is not a query result. Returning nothing here is what
        # makes the stream-based walk miss them, which is the bug under test.
        return iter(())


def test_a_phantom_parent_and_its_subcollection_are_both_deleted() -> None:
    """audit/{job_id}/live is a subcollection under a document with no fields.

    A walk built on stream() cannot see that parent, so every live event of
    every previous run survived the reset — 1,456 documents on 2026-08-28.
    """
    module = load_script()
    live = FakeCollection([FakeDoc("audit/job-1/live/e1"), FakeDoc("audit/job-1/live/e2")])
    phantom = FakeDoc("audit/job-1", subcollections=[live])
    writer = FakeWriter()

    deleted = module.wipe_documents_in(FakeCollection([phantom]), writer)

    assert deleted == 3
    assert writer.deleted == ["audit/job-1/live/e1", "audit/job-1/live/e2", "audit/job-1"]


def test_the_walk_goes_deeper_than_one_level() -> None:
    module = load_script()
    deep = FakeCollection([FakeDoc("a/1/b/2/c/3")])
    mid = FakeCollection([FakeDoc("a/1/b/2", subcollections=[deep])])
    top = FakeCollection([FakeDoc("a/1", subcollections=[mid])])
    writer = FakeWriter()

    assert module.wipe_documents_in(top, writer) == 3
    assert writer.deleted[0] == "a/1/b/2/c/3"
    assert writer.deleted[-1] == "a/1"


def test_a_child_is_queued_before_the_parent_that_holds_it() -> None:
    module = load_script()
    child = FakeCollection([FakeDoc("p/1/c/1")])
    writer = FakeWriter()

    module.wipe_documents_in(FakeCollection([FakeDoc("p/1", subcollections=[child])]), writer)

    assert writer.deleted.index("p/1/c/1") < writer.deleted.index("p/1")


def test_the_writer_is_closed_so_the_last_batch_is_flushed() -> None:
    """A bulk writer buffers; without close() the tail of the wipe is lost."""
    module = load_script()

    class FakeDb:
        def __init__(self, writer):
            self._writer = writer

        def bulk_writer(self):
            return self._writer

        def collection(self, name):
            return FakeCollection([FakeDoc(f"{name}/1")])

    writer = FakeWriter()

    assert module.wipe_collection(FakeDb(writer), "reviews") == 1
    assert writer.closed is True


def test_the_script_refuses_to_delete_without_an_explicit_yes() -> None:
    assert 'parser.error("refusing to delete without --yes")' in SCRIPT.read_text(encoding="utf-8")

import importlib.util
import os

import pytest
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


reset_demo_state = load_script()


def test_it_borrows_the_active_gcloud_profile_by_default() -> None:
    """ADC and the active CLI profile are different things on this machine.

    With two profiles configured, the CLI can point at quanta-gradesync while the
    application-default credentials still hold quanta-local, and Firestore answers
    PERMISSION_DENIED without saying which of the two is wrong. The profile the
    operator just selected is the one they meant.
    """
    monkey = os.environ.get("GOOGLE_ACCESS_TOKEN")
    os.environ["GOOGLE_ACCESS_TOKEN"] = "token-from-the-cli"
    try:
        credentials = reset_demo_state.cli_credentials()
        assert credentials is not None
        assert credentials.token == "token-from-the-cli"
    finally:
        if monkey is None:
            os.environ.pop("GOOGLE_ACCESS_TOKEN", None)
        else:
            os.environ["GOOGLE_ACCESS_TOKEN"] = monkey


def test_adc_stays_reachable_for_a_service_account_context() -> None:
    """In CI or on a runner there is no gcloud profile to borrow."""
    captured = {}

    def fake_client(project, credentials):
        captured["project"] = project
        captured["credentials"] = credentials
        return object()

    original = reset_demo_state.firestore.Client
    reset_demo_state.firestore.Client = fake_client
    try:
        reset_demo_state.open_client("quanta-gradesync", use_cli_auth=False)
    finally:
        reset_demo_state.firestore.Client = original

    assert captured["project"] == "quanta-gradesync"
    assert captured["credentials"] is None


def test_an_expired_login_is_named_instead_of_becoming_an_iam_mystery() -> None:
    """gcloud present and refusing is not the same as gcloud absent.

    Falling back to ADC on a refusal asks a second, unrelated credential the same
    question and reports its PERMISSION_DENIED, which sends you reading IAM
    policy for what is really an expired login.
    """
    import subprocess

    class Refused:
        returncode = 1
        stdout = ""
        stderr = "ERROR: Reauthentication failed. cannot prompt\nPlease run\n"

    original = subprocess.run
    subprocess.run = lambda *a, **k: Refused()
    token = os.environ.pop("GOOGLE_ACCESS_TOKEN", None)
    try:
        with pytest.raises(reset_demo_state.ReauthRequired, match="gcloud auth login"):
            reset_demo_state.cli_credentials()
    finally:
        subprocess.run = original
        if token is not None:
            os.environ["GOOGLE_ACCESS_TOKEN"] = token


def test_a_machine_without_gcloud_still_falls_back_to_adc() -> None:
    """A CI runner has no profile to borrow and must not be told to log in."""
    import subprocess

    original = subprocess.run

    def missing(*args, **kwargs):
        raise FileNotFoundError("gcloud")

    subprocess.run = missing
    token = os.environ.pop("GOOGLE_ACCESS_TOKEN", None)
    try:
        assert reset_demo_state.cli_credentials() is None
    finally:
        subprocess.run = original
        if token is not None:
            os.environ["GOOGLE_ACCESS_TOKEN"] = token


def test_it_asks_the_database_what_it_holds() -> None:
    """assessment_facts and labels survived every reset for weeks.

    They were not in the hand-written list, and a hand-written list of
    collections drifts the moment the engine writes a new one. "Wipe the
    database" has to mean the database.
    """
    class Db:
        def collections(self):
            return [type("C", (), {"id": name})() for name in ("audit", "brand_new_thing")]

    names, discovered = reset_demo_state.collections_to_wipe(Db())

    assert discovered is True
    assert "brand_new_thing" in names
    # the known list stays a floor, so an empty collection is still visited
    assert set(reset_demo_state.KNOWN_COLLECTIONS) <= set(names)


def test_the_two_that_were_missed_are_in_the_floor() -> None:
    assert "assessment_facts" in reset_demo_state.KNOWN_COLLECTIONS
    assert "labels" in reset_demo_state.KNOWN_COLLECTIONS


def test_a_credential_that_cannot_list_the_root_says_so() -> None:
    """Silently wiping nine of eleven collections reads as a clean database."""
    class Refuses:
        def collections(self):
            raise PermissionError("Missing or insufficient permissions")

    names, discovered = reset_demo_state.collections_to_wipe(Refuses())

    assert discovered is False
    assert names == reset_demo_state.KNOWN_COLLECTIONS


def test_the_reset_reaches_the_bucket_the_console_actually_lists_from() -> None:
    """Firestore was empty and the page still said "36 exams".

    The teacher page lists batches from Cloud Storage, so wiping Firestore alone
    left every staged scan visible under a gradebook that had nothing in it.
    """
    deleted, kept = [], []

    class Blob:
        def __init__(self, name):
            self.name = name

        def delete(self):
            deleted.append(self.name)

    class Client:
        def bucket(self, name):
            return name

        def list_blobs(self, bucket):
            return [
                Blob("uploads/batches/2026_Matematicas_10A_M/ana.jpg"),
                Blob("catalog-defaults.json"),
                Blob("demo-source/v2/batches/2026_Matematicas_10A_Parcial1/ana.jpg"),
                Blob("live/whatever.jpg"),
            ]

    original = reset_demo_state.storage.Client
    reset_demo_state.storage.Client = lambda **kwargs: Client()
    try:
        removed, survived = reset_demo_state.wipe_bucket("b", None)
    finally:
        reset_demo_state.storage.Client = original

    assert removed == 2 and survived == 2
    assert "uploads/batches/2026_Matematicas_10A_M/ana.jpg" in deleted
    assert "live/whatever.jpg" in deleted


def test_the_two_things_the_bucket_must_keep() -> None:
    """One the engine reads, one the judges' button copies from."""
    assert "catalog-defaults.json" in reset_demo_state.KEEP_IN_BUCKET
    assert "demo-source/" in reset_demo_state.KEEP_IN_BUCKET

from pathlib import Path

from autocurricula.config.settings import GCP_SETTLE_INTERVAL_SECONDS, Settings
from autocurricula.core.orchestration.batch_settle import (
    LISTING_FAILED,
    BatchSettler,
    LocalBatchLister,
    build_batch_settler,
)
from tests.orchestration.inference_fixtures import BUCKET, PREFIX, make_event


class ScriptedLister:
    def __init__(self, counts: list[int]) -> None:
        self.counts = list(counts)
        self.calls = 0

    async def count_objects(self, bucket: str, prefix: str) -> int:
        self.calls += 1
        index = min(self.calls - 1, len(self.counts) - 1)
        return self.counts[index]


class FailingLister:
    def __init__(self) -> None:
        self.calls = 0

    async def count_objects(self, bucket: str, prefix: str) -> int:
        self.calls += 1
        raise RuntimeError("listing unavailable")


class FakeSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


async def test_settle_returns_when_two_listings_agree() -> None:
    lister = ScriptedLister([1, 4, 8, 8, 8])
    sleeper = FakeSleeper()
    settler = BatchSettler(lister, interval_seconds=0.5, max_rounds=6, sleeper=sleeper)
    assert await settler.wait(make_event()) == 8
    assert lister.calls == 4
    assert sleeper.delays == [0.5, 0.5, 0.5]


async def test_settle_is_bounded_by_max_rounds() -> None:
    lister = ScriptedLister([1, 2, 3, 4, 5, 6, 7, 8, 9])
    sleeper = FakeSleeper()
    settler = BatchSettler(lister, interval_seconds=0.25, max_rounds=3, sleeper=sleeper)
    assert await settler.wait(make_event()) == 4
    assert len(sleeper.delays) == 3


async def test_zero_interval_never_lists() -> None:
    lister = ScriptedLister([1, 1])
    sleeper = FakeSleeper()
    settler = BatchSettler(lister, interval_seconds=0.0, sleeper=sleeper)
    assert await settler.wait(make_event()) == LISTING_FAILED
    assert lister.calls == 0
    assert sleeper.delays == []


async def test_listing_failures_do_not_block_the_job() -> None:
    lister = FailingLister()
    sleeper = FakeSleeper()
    settler = BatchSettler(lister, interval_seconds=0.1, max_rounds=4, sleeper=sleeper)
    assert await settler.wait(make_event()) == LISTING_FAILED
    assert lister.calls == 2


async def test_local_lister_counts_files_directly_under_the_prefix(
    tmp_path: Path,
) -> None:
    root = tmp_path / BUCKET / PREFIX
    root.mkdir(parents=True)
    (root / "ana-torres.jpg").write_bytes(b"scan")
    (root / "luis-gomez.jpg").write_bytes(b"scan")
    (root / "pages").mkdir()
    lister = LocalBatchLister(tmp_path)
    assert await lister.count_objects(BUCKET, PREFIX) == 2
    assert await lister.count_objects(BUCKET, "batches/absent") == 0


def test_settler_is_disabled_by_default_in_local_mode(tmp_path: Path) -> None:
    settings = Settings(
        local_mode=True, gcp_project_id="", gcs_local_staging_dir=tmp_path
    )
    assert settings.batch_settle_interval_seconds == 0.0
    assert build_batch_settler(settings) is None


def test_settler_defaults_to_a_bounded_wait_in_gcp_mode() -> None:
    settings = Settings(local_mode=False, gcp_project_id="quanta-gradesync")
    assert settings.local_mode is False
    assert settings.batch_settle_interval_seconds == GCP_SETTLE_INTERVAL_SECONDS
    assert settings.batch_settle_max_rounds == 6


def test_explicit_settle_interval_wins_over_mode_default() -> None:
    settings = Settings(
        local_mode=False,
        gcp_project_id="quanta-gradesync",
        batch_settle_interval_seconds=0.0,
    )
    assert settings.batch_settle_interval_seconds == 0.0
    assert build_batch_settler(settings) is None


def test_local_settler_is_built_when_the_interval_is_positive(tmp_path: Path) -> None:
    settings = Settings(
        local_mode=True,
        gcp_project_id="",
        gcs_local_staging_dir=tmp_path,
        batch_settle_interval_seconds=0.01,
        batch_settle_max_rounds=2,
    )
    settler = build_batch_settler(settings)
    assert settler is not None
    assert settler.interval_seconds == 0.01

import hashlib
import json
from pathlib import Path

import pytest

REFERENCE_PAGE_DIGEST = "65856bc1898aba0e20a302c1423a5dfa008c4000d14e2c675c19a519df127ad5"
REFERENCE_PAGE_COUNT = 16


def pages_of(batch: dict[str, object]) -> list[Path]:
    return batch["pages"]


def digest_of(pages: list[Path]) -> str:
    digest = hashlib.sha256()
    for page in sorted(pages, key=lambda item: item.name):
        digest.update(page.name.encode("utf-8"))
        digest.update(hashlib.sha256(page.read_bytes()).digest())
    return digest.hexdigest()


def test_reference_roster_still_renders_sixteen_pages(reference_batch) -> None:
    pages = pages_of(reference_batch)
    assert len(pages) == REFERENCE_PAGE_COUNT
    assert len({page.stem for page in pages}) == REFERENCE_PAGE_COUNT
    assert reference_batch["lot"].lot_code == "2026_Matematicas_10A_Parcial1"


def test_reference_pages_are_byte_identical_to_the_pinned_fixture(reference_batch) -> None:
    assert digest_of(pages_of(reference_batch)) == REFERENCE_PAGE_DIGEST


def test_reference_roster_keeps_writing_ground_truth(reference_batch) -> None:
    payload = json.loads(reference_batch["ground_truth"].read_text(encoding="utf-8"))
    assert payload["class_id"] == "10A"
    assert len(payload["students"]) == 8


def test_unknown_roster_is_rejected(generator) -> None:
    from sample_batch.rosters import profiles_for

    with pytest.raises(ValueError):
        profiles_for("nope")


import re
from pathlib import Path

STATIC = Path("src/autocurricula/api/static")


def test_the_collision_sheet_offers_one_decision_for_the_whole_batch() -> None:
    page = (STATIC / "teacher.html").read_text(encoding="utf-8")

    assert 'id="collision-all"' in page
    assert "Do the same for the rest of this batch" in page


def test_the_dialog_reports_and_defaults_to_one_choice_for_the_batch() -> None:
    dialogs = (STATIC / "teacher-dialogs.js").read_text(encoding="utf-8")

    assert '"collision-all"' in dialogs
    assert "dom.collisionAll.checked = true;" in dialogs
    assert re.search(r"all:\s*Boolean\(dom\.collisionAll", dialogs)


def test_the_upload_loop_stops_asking_once_she_has_decided() -> None:
    upload = (STATIC / "teacher-upload.js").read_text(encoding="utf-8")

    assert "uploads.collisionForAll" in upload
    assert 'decision.action !== "rename"' in upload
    assert "collisionForAll = null;" in upload

import json
from pathlib import Path

import pytest
import run_red_team
from red_team.taxonomy import CLASSES_BY_CODE, resolve_classes


def test_classes_resolve_by_code() -> None:
    resolved = resolve_classes(["a1", "C0", "A1"])

    assert [item.code for item in resolved] == ["A1", "C0"]
    assert CLASSES_BY_CODE["C0"].hostile is False


def test_unknown_class_is_rejected_with_the_known_list() -> None:
    with pytest.raises(ValueError, match="unknown attack class"):
        resolve_classes(["A99"])


def test_every_class_ships_seed_payloads_and_an_expectation() -> None:
    for item in CLASSES_BY_CODE.values():
        assert len(item.seeds) >= 2, item.code
        assert item.expectation.strip(), item.code


def test_cli_runs_the_offline_campaign_end_to_end(tmp_path: Path, capsys) -> None:
    exit_code = run_red_team.main(
        [
            "--scripted-generator",
            "--screen",
            "scripted",
            "--classes",
            "A1,A2,C0",
            "--payloads-per-class",
            "1",
            "--target",
            str(tmp_path / "pages"),
            "--out",
            str(tmp_path / "report"),
        ]
    )

    assert exit_code == 0
    payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert payload["config"]["classes"] == ["A1", "A2", "C0"]
    assert payload["totals"]["hostile_attempted"] == 2
    assert (tmp_path / "report.md").is_file()
    assert "catch rate" in capsys.readouterr().out


def test_cli_refuses_the_llm_screen_without_a_project(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="need a real project"):
        run_red_team.main(
            [
                "--scripted-generator",
                "--screen",
                "llm",
                "--classes",
                "A1",
                "--payloads-per-class",
                "1",
                "--project",
                "",
                "--target",
                str(tmp_path / "pages"),
                "--out",
                str(tmp_path / "report"),
            ]
        )

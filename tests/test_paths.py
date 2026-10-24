"""core/paths.py: Mabillon's names first, the Baker-era ones still read, nothing moved."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli import main as cli_main
from core import paths


def test_a_mabillon_variable_wins_over_its_baker_name(monkeypatch):
    monkeypatch.setenv("MABILLON_CASES", "/new")
    monkeypatch.setenv("BAKER_CASES", "/old")
    assert paths.env("CASES") == "/new"
    assert paths.env_in_use("CASES") == "MABILLON_CASES"


def test_a_baker_variable_is_still_read(monkeypatch):
    monkeypatch.delenv("MABILLON_CASES", raising=False)
    monkeypatch.setenv("BAKER_CASES", " /old ")
    assert paths.env("CASES") == "/old"
    assert paths.env_in_use("CASES") == "BAKER_CASES"


def test_no_variable_set_reads_empty(monkeypatch):
    monkeypatch.delenv("MABILLON_CASES", raising=False)
    monkeypatch.setenv("BAKER_CASES", "  ")
    assert paths.env("CASES") == ""
    assert paths.env_in_use("CASES") == "MABILLON_CASES"


def test_a_new_computer_gets_the_mabillon_folders(tmp_path: Path):
    assert paths.settings_file("model.json", tmp_path) == tmp_path / ".mabillon" / "model.json"
    assert paths.user_folder("cases", tmp_path) == tmp_path / "Mabillon" / "cases"


def test_a_computer_set_up_as_baker_keeps_its_folders(tmp_path: Path):
    (tmp_path / ".baker").mkdir()
    (tmp_path / ".baker" / "model.json").write_text("{}")
    (tmp_path / "Baker" / "cases").mkdir(parents=True)
    assert paths.settings_file("model.json", tmp_path) == tmp_path / ".baker" / "model.json"
    assert paths.user_folder("cases", tmp_path) == tmp_path / "Baker" / "cases"
    # A settings file only the new folder will hold goes there.
    assert paths.settings_file("cloud.json", tmp_path) == tmp_path / ".mabillon" / "cloud.json"


def test_once_the_new_folder_exists_it_wins(tmp_path: Path):
    for p in (tmp_path / "Baker" / "cases", tmp_path / "Mabillon" / "cases"):
        p.mkdir(parents=True)
    assert paths.user_folder("cases", tmp_path) == tmp_path / "Mabillon" / "cases"


def test_the_command_is_mabillon():
    assert cli_main.parser().prog == "mabillon"


def test_the_baker_alias_runs_the_same_command_with_a_note(monkeypatch, capsys):
    monkeypatch.setattr(cli_main.sys, "argv", ["baker", "--help"])
    with pytest.raises(SystemExit) as stop:
        cli_main.baker_alias()
    assert stop.value.code == 0
    out = capsys.readouterr()
    assert "usage: mabillon" in out.out
    assert "`baker` is now `mabillon`" in out.err


def test_a_baker_era_setup_keeps_its_model_cloud_and_cases(monkeypatch, tmp_path: Path):
    # Read when called, not at import, so the folder a run uses is the one on disk then.
    from core.audit import _local_model
    from core.casework import cases
    from core.llm import cloud

    for name in ("MODEL_CONFIG", "CLOUD_CONFIG", "CASES"):
        monkeypatch.delenv(paths.PREFIX + name, raising=False)
        monkeypatch.delenv(paths.OLD_PREFIX + name, raising=False)
    monkeypatch.setattr(paths.Path, "home", lambda: tmp_path)
    (tmp_path / ".baker").mkdir()
    (tmp_path / ".baker" / "model.json").write_text("{}")
    (tmp_path / ".baker" / "cloud.json").write_text("{}")
    (tmp_path / "Baker" / "cases").mkdir(parents=True)
    assert _local_model.config_path() == tmp_path / ".baker" / "model.json"
    assert cloud.config_path() == tmp_path / ".baker" / "cloud.json"
    assert cases.cases_home() == tmp_path / "Baker" / "cases"
    # The installer's new model config, once written, is the one used.
    (tmp_path / ".mabillon").mkdir()
    (tmp_path / ".mabillon" / "model.json").write_text("{}")
    assert _local_model.config_path() == tmp_path / ".mabillon" / "model.json"

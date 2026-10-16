"""core/build.py: the release and git commit a run stamps (pilot gate 3)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core import build

ROOT = Path(__file__).resolve().parents[1]


def _pyproject(root: Path, version: str = "9.8.7") -> None:
    (root / "pyproject.toml").write_text(f'[project]\nname = "baker"\nversion = "{version}"\n')


def test_the_release_is_the_source_trees_pyproject_version(tmp_path):
    _pyproject(tmp_path)
    assert build.release(tmp_path) == "9.8.7"
    assert build.release(ROOT) == build.release()  # this checkout's pyproject.toml


def test_an_installed_copy_reads_the_commit_from_the_installers_build_info(tmp_path):
    # Windows: BUILD_INFO.json beside the source folder; Mac: inside it. No .git in either.
    src = tmp_path / "baker"
    src.mkdir()
    _pyproject(src)
    assert build.commit(src) == (build.NOT_RECORDED, None)
    (tmp_path / "BUILD_INFO.json").write_text(json.dumps({"git_commit": "a" * 40}))
    assert build.commit(src) == ("a" * 40, None)
    (src / "BUILD_INFO.json").write_text(json.dumps({"git_commit": "b" * 40}))
    assert build.commit(src) == ("b" * 40, None)  # the source folder's own wins
    assert build.label(build.build_info.__wrapped__(src)) == "9.8.7, commit bbbbbbbbbbbb"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_a_checkout_records_its_commit_and_whether_tracked_files_changed(tmp_path):
    git = shutil.which("git")

    def run(*args: str) -> str:
        return subprocess.run(  # noqa: S603
            [git, "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    run("init", "-q")
    _pyproject(tmp_path)
    run("add", "pyproject.toml")
    run("commit", "-q", "-m", "x")
    head = run("rev-parse", "HEAD")
    (tmp_path / "untracked.txt").write_text("not part of the build")
    assert build.commit(tmp_path) == (head, False)
    _pyproject(tmp_path, "9.8.8")
    assert build.commit(tmp_path) == (head, True)
    assert build.label(build.build_info.__wrapped__(tmp_path)) == (
        f"9.8.8, commit {head[:12]}, with uncommitted changes"
    )


def test_a_run_made_before_the_build_was_recorded_says_so():
    assert build.label(None) == "release and commit not recorded"

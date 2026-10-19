"""core/build.py: the release and git commit a run stamps (pilot gate 3)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
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
    # Grok on #91: a copy that does not say whether its files changed never reads as clean.
    assert build.label(build.build_info.__wrapped__(src)) == (
        "9.8.7, commit bbbbbbbbbbbb, uncommitted changes not checked"
    )
    # The Mac installer records it (rsync copies uncommitted edits too).
    for dirty, note in ((False, ""), (True, ", with uncommitted changes")):
        (src / "BUILD_INFO.json").write_text(json.dumps({"git_commit": "b" * 40, "dirty": dirty}))
        assert build.commit(src) == ("b" * 40, dirty)
        assert build.label(build.build_info.__wrapped__(src)) == f"9.8.7, commit {'b' * 12}{note}"


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None or shutil.which("bash") is None,
    reason="the Mac installer's shell lines; needs git and bash",
)
def test_the_mac_installer_records_the_commit_and_whether_tracked_files_changed(tmp_path):
    # Run the installer's own BUILD_INFO lines against a scratch checkout.
    script = (ROOT / "packaging" / "mac" / "install.sh").read_text(encoding="utf-8")
    start = script.index('  if COMMIT="$(git -C "$HERE" rev-parse HEAD')
    block = script[start : script.index("  fi\n", start) + len("  fi\n")]
    here, app = tmp_path / "src", tmp_path / "app"
    here.mkdir()
    (app / "baker").mkdir(parents=True)
    git = shutil.which("git")

    def run(*args: str) -> str:
        return subprocess.run(  # noqa: S603
            [git, "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=here,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    run("init", "-q")
    _pyproject(here)
    run("add", "pyproject.toml")
    run("commit", "-q", "-m", "x")
    head = run("rev-parse", "HEAD")
    for edit, dirty in ((False, False), (True, True)):
        if edit:
            _pyproject(here, "9.8.8")
        subprocess.run(  # noqa: S603
            [shutil.which("bash"), "-c", block],
            env={"HERE": str(here), "APP": str(app), "PATH": str(Path(git).parent)},
            check=True,
        )
        info = json.loads((app / "baker" / "BUILD_INFO.json").read_text(encoding="utf-8"))
        assert info == {"git_commit": head, "dirty": dirty}


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

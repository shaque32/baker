"""core/build.py: the release and git commit a run stamps (pilot gate 3)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
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
    # The Mac installer records whether the copy differed (rsync copies uncommitted edits too).
    # Changed at install stays changed; clean at install is not rechecked later, since the files
    # may be edited after (Codex on #91), so it reads as unknown.
    for dirty, seen, note in (
        (False, None, ", uncommitted changes not checked"),
        (True, True, ", with uncommitted changes"),
    ):
        (src / "BUILD_INFO.json").write_text(json.dumps({"git_commit": "b" * 40, "dirty": dirty}))
        assert build.commit(src) == ("b" * 40, seen)
        assert build.label(build.build_info.__wrapped__(src)) == f"9.8.7, commit {'b' * 12}{note}"


def test_a_rules_only_rerun_names_the_build_its_evidence_came_from():
    # Codex on #91: a re-run on a newer build reuses the older run's assumptions, checks and
    # labels, so the report names both builds; chained re-runs keep the first evidence build.
    old = {"release": "0.0.1", "commit": "a" * 40, "dirty": False}
    new = {"release": "0.0.2", "commit": "c" * 40, "dirty": False}
    assert build.run_label({"build": old}) == f"0.0.1, commit {'a' * 12}"
    assert build.run_label({"build": new, "evidence_build": new}) == f"0.0.2, commit {'c' * 12}"
    assert build.run_label({"build": new, "evidence_build": old}) == (
        f"0.0.2, commit {'c' * 12}; its evidence and labels from 0.0.1, commit {'a' * 12}"
    )
    assert build.run_label({"build": new, "evidence_build": None}) == (
        f"0.0.2, commit {'c' * 12}; its evidence and labels from release and commit not recorded"
    )


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


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_a_git_archive_names_its_commit_without_a_git_folder(tmp_path):
    # Codex on #91: the Mac guide starts from a zipped folder (clean-install.yml uses
    # `git archive`), which has no .git; export-subst writes the commit into core/BUILD_COMMIT.
    git = shutil.which("git")
    repo, out = tmp_path / "repo", tmp_path / "out"
    (repo / "core").mkdir(parents=True)
    out.mkdir()
    shutil.copyfile(ROOT / "core" / "BUILD_COMMIT", repo / "core" / "BUILD_COMMIT")
    shutil.copyfile(ROOT / ".gitattributes", repo / ".gitattributes")
    _pyproject(repo)

    def run(*args: str) -> str:
        return subprocess.run(  # noqa: S603
            [git, "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    run("init", "-q")
    run("add", "-A")
    run("commit", "-q", "-m", "x")
    head = run("rev-parse", "HEAD")
    assert build.commit(repo) == (head, False)  # a checkout still reads git, not the file
    run("archive", "--format=tar", "-o", str(tmp_path / "a.tar"), "HEAD")
    with tarfile.open(tmp_path / "a.tar") as tar:
        tar.extractall(out, filter="data")
    assert not (out / ".git").exists()
    assert build.commit(out) == (head, None)
    assert build.label(build.build_info.__wrapped__(out)) == (
        f"9.8.7, commit {head[:12]}, uncommitted changes not checked"
    )


def test_the_unfilled_archive_placeholder_is_not_a_commit(tmp_path):
    (tmp_path / "core").mkdir()
    shutil.copyfile(ROOT / "core" / "BUILD_COMMIT", tmp_path / "core" / "BUILD_COMMIT")
    assert build.commit(tmp_path) == (build.NOT_RECORDED, None)


def test_a_run_made_before_the_build_was_recorded_says_so():
    assert build.label(None) == "release and commit not recorded"

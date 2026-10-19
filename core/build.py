"""Which Baker build ran: its release version and git commit, stamped on every run.

PIPELINE_VERSION (core/pipeline.py) names the pipeline's shape and changes rarely; it cannot tell
two builds apart. A result also records the release (pyproject.toml's version) and the git commit
of the source that ran, with whether that source had uncommitted changes.

The commit comes from, in order: the source checkout's git (a developer's or a cloned install),
then BUILD_INFO.json written by the installer (packaging/windows/stage.py puts it beside the
source folder; packaging/mac/install.sh inside it, when it is run from a checkout), then
core/BUILD_COMMIT, which `git archive` fills in (export-subst in .gitattributes), so the zipped
folder the Mac install guide starts from names its commit too. None of them: "not recorded".
Local only: git runs with fixed arguments on this folder and nothing leaves the machine.
"""

from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess  # noqa: S404 - git only, fixed arguments, local repository
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOT_RECORDED = "not recorded"


def release(root: Path = ROOT) -> str:
    """pyproject.toml's version for a source tree, else the installed package's."""
    try:
        return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
            "version"
        ]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        pass
    try:
        return metadata.version("baker")
    except metadata.PackageNotFoundError:
        return NOT_RECORDED


def _git(root: Path, *args: str) -> str | None:
    git = shutil.which("git")
    if git is None or not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(  # noqa: S603 - fixed arguments
            [git, *args], cwd=root, capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout


def commit(root: Path = ROOT) -> tuple[str, bool | None]:
    """(commit, dirty). dirty is True when tracked files differ from the commit, None when
    unknown. An installed copy has no .git to recheck: its files may have changed since it was
    installed, so the installer's "dirty": true is kept but "dirty": false reads as unknown."""
    head = _git(root, "rev-parse", "HEAD")
    if head and head.strip():
        status = _git(root, "status", "--porcelain", "--untracked-files=no")
        return head.strip(), (bool(status.strip()) if status is not None else None)
    for info in (root / "BUILD_INFO.json", root.parent / "BUILD_INFO.json"):
        try:
            data = json.loads(info.read_text(encoding="utf-8"))
            got = data.get("git_commit")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(got, str) and got:
            return got, (True if data.get("dirty") is True else None)
    try:  # "$Format:%H$" in a checkout; the commit in an archive. Unzipped files may be edited.
        archived = (root / "core" / "BUILD_COMMIT").read_text(encoding="utf-8").strip()
    except OSError:
        archived = ""
    if re.fullmatch(r"[0-9a-f]{40}", archived):
        return archived, None
    return NOT_RECORDED, None


@functools.cache
def build_info(root: Path = ROOT) -> dict:
    """What a run stores in its config as "build". Read once per process: the code that runs is
    the code loaded at start, so later edits to the files must not change what is recorded."""
    sha, dirty = commit(root)
    return {"release": release(root), "commit": sha, "dirty": dirty}


def run_label(config: dict) -> str:
    """The build a run's stored config names. A rules-only re-run (core/review/redecide.py)
    reuses an earlier run's assumptions, checks and labels, so when those came from another build
    it names that one too."""
    own = label(config.get("build"))
    if "evidence_build" not in config or config["evidence_build"] == config.get("build"):
        return own
    evidence = config["evidence_build"]  # None: made before builds were recorded
    return f"{own}; its evidence and labels from {label(evidence)}"


def label(build: object) -> str:
    """'0.0.1, commit 1a2b3c4d5e6f', then ', with uncommitted changes' when dirty, or ',
    uncommitted changes not checked' when that is unknown, so an unchecked copy never reads as a
    clean build of the commit. Runs made before the build was recorded say so."""
    if not isinstance(build, dict):
        return "release and commit not recorded"
    sha = str(build.get("commit") or NOT_RECORDED)
    short = sha[:12] if sha != NOT_RECORDED else sha
    dirty = build.get("dirty")
    if sha == NOT_RECORDED:
        note = ""
    elif dirty is True:
        note = ", with uncommitted changes"
    elif dirty is False:
        note = ""
    else:
        note = ", uncommitted changes not checked"
    return f"{build.get('release') or NOT_RECORDED}, commit {short}{note}"

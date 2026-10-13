"""The Windows installer's file list and pins (packaging/windows/). No network, no Windows."""

from __future__ import annotations

import ast
import fnmatch
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
WIN = ROOT / "packaging" / "windows"

_spec = importlib.util.spec_from_file_location("stage", WIN / "stage.py")
assert _spec and _spec.loader
stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stage)

HEX64 = re.compile(r"[0-9a-f]{64}")


def test_case02_and_the_cloud_benchmark_are_never_shipped():
    for path in (
        "eval/synthetic/case02/case.json",
        "eval/synthetic/case02_generate.py",
        "eval/gold/case02/gold.jsonl",
        "tests/test_synthetic_case02.py",
        "eval/bench/claude_bench.py",
        "eval/stancedata/score.py",
        "eval/stancemodel/train.py",
        "eval/out/case01/case01.db",
        "CLAUDE.md",
    ):
        assert not stage.shipped(path), path


def test_the_product_and_case01_are_shipped():
    for path in (
        "core/schema.sql",
        "core/audit/prompts/stance.md",
        "cli/main.py",
        "ui/server.py",
        "eval/gold/case01/gold.jsonl",
        "eval/gold/probe/probe.jsonl",
        "eval/synthetic/case01/case.json",
        "eval/probe/time_case.py",
    ):
        assert stage.shipped(path), path


def test_no_tracked_case02_file_is_shipped():
    shipped = [f for f in stage.tracked_files(ROOT) if stage.shipped(f)]
    assert shipped
    assert not [f for f in shipped if "case02" in f]


def test_pip_install_includes_every_data_file_core_and_ui_read():
    """A non-editable install (`pip install .`) carries the files core/ and ui/ open at run time."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = data["tool"]["setuptools"]["package-data"]
    missing = []
    for f in stage.tracked_files(ROOT):
        p = PurePosixPath(f)
        if p.parts[0] not in {"core", "cli", "ui"} or p.suffix == ".py":
            continue
        covered = False
        for package, patterns in package_data.items():
            base = PurePosixPath(*package.split("."))
            if base in p.parents:
                rel = p.relative_to(base).as_posix()
                covered |= any(fnmatch.fnmatch(rel, pat) for pat in patterns)
        if not covered:
            missing.append(f)
    assert not missing, f"add to [tool.setuptools.package-data] in pyproject.toml: {missing}"


def test_every_package_a_shipped_file_imports_is_installed():
    """The installed copy runs the case01 gate and the speed test, so every third-party module a
    shipped file imports must come with the installer (llama_cpp ships as its own runtime)."""
    shipped_dists = {
        re.split(r"[<>=!~;\[ ]", req, maxsplit=1)[0].lower().replace("-", "_")
        for req in stage.runtime_requirements()
    } | {"llama_cpp"}
    missing: dict[str, str] = {}
    for f in stage.tracked_files(ROOT):
        if not (f.endswith(".py") and stage.shipped(f)):
            continue
        for node in ast.walk(ast.parse((ROOT / f).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                local = top in {"cli", "core", "ui", "eval"}
                if not local and top not in sys.stdlib_module_names and top not in shipped_dists:
                    missing.setdefault(top, f)
    assert not missing, f"add to pyproject dependencies or the synthetic extra: {missing}"


def test_pins_are_complete():
    pins = json.loads((WIN / "pins.json").read_text(encoding="utf-8"))
    assert HEX64.fullmatch(pins["python"]["sha256"])
    assert re.fullmatch(r"[0-9a-f]{32}", pins["python"]["md5"])
    assert pins["python"]["url"].startswith("https://www.python.org/ftp/python/")
    assert HEX64.fullmatch(pins["llama_cpp_python"]["sdist_sha256"])
    assert "GGML_NATIVE=OFF" in pins["llama_cpp_python"]["cpu_cmake_args"]
    model = pins["model"]
    assert HEX64.fullmatch(model["sha256"])
    assert model["size"] > 1_000_000_000
    assert model["url"].startswith("https://huggingface.co/")
    assert model["url"].endswith(model["file"])
    assert model["license"] == "Apache-2.0"


def test_the_installed_python_finds_baker_and_runs_in_utf8_mode():
    cmd = (WIN / "baker.cmd").read_text(encoding="utf-8")
    assert "-X utf8 -m cli" in cmd
    src = (WIN / "stage.py").read_text(encoding="utf-8")
    assert "..\\\\baker" in src and "import site" in src


def test_no_network_tool_ships_in_core():
    """The installer's only download is the optional model step in Setup, never Baker itself."""
    iss = (WIN / "baker.iss").read_text(encoding="utf-8")
    assert "DownloadTemporaryFile" in iss and "ModelSha256" in iss
    for f in stage.tracked_files(ROOT):
        if f.startswith("core/") and f.endswith(".py"):
            text = (ROOT / f).read_text(encoding="utf-8")
            assert "huggingface" not in text.lower(), f


def test_the_mac_installer_parses_reads_the_same_pins_and_keeps_an_existing_model_setting():
    import subprocess

    script = ROOT / "packaging" / "mac" / "install.sh"
    if sys.platform != "win32":  # Windows' "bash" is the WSL launcher, often with no Linux in it
        subprocess.run(["bash", "-n", str(script)], check=True)  # noqa: S603, S607 - fixed args
    text = script.read_text(encoding="utf-8")
    assert "packaging/windows/pins.json" in text
    for key in ("['llama_cpp_python']['version']", "['model']['sha256']", "['model']['url']"):
        assert key in text
    assert 'if [ -f "$CONFIG" ]' in text  # never overwrites ~/.baker/model.json
    assert "shasum -a 256" in text  # the model is checked before it is used
    # Executable in git, so a checkout on any system (and the zip GitHub makes) keeps the bit.
    cmd = ["git", "ls-files", "-s", "packaging/mac"]  # noqa: S607 - fixed args
    modes = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout  # noqa: S603
    for name in ("install.sh", "Install Baker.command"):
        assert any(line.startswith("100755") and line.endswith(name) for line in modes.splitlines())

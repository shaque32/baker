"""Stage the files the Windows installer ships, then Inno Setup packs them (baker.iss).

    python packaging/windows/stage.py --out build/stage --python-zip python-embed.zip
        --llama-cpu <cpu wheel> --llama-cuda <cuda wheel> [--crt-dlls <dir>] [--cuda-dlls <dir>]

Layout of build/stage (and of the installed folder):
    python/                 embeddable CPython, with Mabillon's dependencies in Lib/site-packages
    baker/                  Mabillon's source, from git (synthetic case01 and the signed probe set
                            included, so a fresh install can run case01 and the speed test)
    runtime/cpu/            llama-cpp-python, CPU build (AVX2), for a PC with no NVIDIA GPU
    runtime/cuda/           llama-cpp-python, CUDA build plus the CUDA runtime DLLs
    baker.cmd, mabillon.cmd the `baker` and `mabillon` commands (one launcher, two names)
    BUILD_INFO.json         versions, the git commit and the SHA-256 of every staged file

The installer copies exactly one of runtime/cpu and runtime/cuda into python/Lib/site-packages,
depending on whether the PC has an NVIDIA driver. Wheels are installed for win_amd64 and
CPython 3.12 whatever machine stages them, so the file list can be checked on Linux too.

Never shipped: case02 (the held-out case; builders never read it), the cloud benchmark
(eval/bench), the small-model training track, eval outputs, and anything git does not track.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess  # noqa: S404 - git and pip only, fixed arguments
import sys
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PINS = Path(__file__).with_name("pins.json")
LAUNCHER = Path(__file__).with_name("baker.cmd")

# What goes into baker/: these top-level paths from `git ls-files`, minus EXCLUDE.
SHIP = ("cli/", "core/", "ui/", "eval/", "docs/", "README.md", "pyproject.toml")
EXCLUDE = (
    "eval/bench/",  # cloud benchmark, eval only; the product never talks to a cloud model
    "eval/stancedata/",  # small-model track, not part of the product yet
    "eval/train/",
    "eval/heldout/",
    "eval/out/",  # run outputs (git ignores them too)
    "eval/probe/candidates.py",  # Mac screen of other local models; downloads model files
    "eval/probe/mac_candidates.sh",
)


def shipped(path: str) -> bool:
    """True when a git-tracked path goes into the installer."""
    p = PurePosixPath(path)
    if not path.startswith(SHIP) or path.startswith(EXCLUDE):
        return False
    # case02 is the held-out case: never shipped, whatever its file is called.
    return not any("case02" in part for part in p.parts)


def tracked_files(root: Path = ROOT) -> list[str]:
    git = shutil.which("git") or "git"
    out = subprocess.run(  # noqa: S603 - fixed arguments
        [git, "ls-files", "-z"], cwd=root, capture_output=True, check=True
    ).stdout.decode("utf-8")
    return sorted(f for f in out.split("\0") if f)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def md5_file(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - python.org publishes MD5; SHA-256 is pinned beside it
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def runtime_requirements(root: Path = ROOT) -> list[str]:
    """Mabillon's dependencies plus the `synthetic` extra: the installer ships eval/ so an expert's
    PC can run the case01 gate and the speed test, and those render the synthetic case PDFs.
    Plus the `cloud` extra, the client for a case the expert allows to use cloud AI."""
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    extras = project["optional-dependencies"]
    return [*project["dependencies"], *extras["synthetic"], *extras["cloud"]]


def pip_target(target: Path, *args: str) -> None:
    """pip install into a folder, for Windows x64 and CPython 3.12, wheels only."""
    cmd = [
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-compile",
        "--target", str(target), "--platform", "win_amd64", "--python-version", "3.12",
        "--implementation", "cp", "--only-binary", ":all:", *args,
    ]  # fmt: skip
    subprocess.run(cmd, check=True)  # noqa: S603 - pip, arguments built here


def stage_python(zip_path: Path, out: Path, pins: dict) -> str:
    md5 = md5_file(zip_path)
    sha = sha256_file(zip_path)
    if md5 != pins["md5"]:
        raise SystemExit(f"{zip_path}: MD5 {md5} is not python.org's {pins['md5']}")
    if pins.get("sha256") and sha != pins["sha256"]:
        raise SystemExit(f"{zip_path}: SHA-256 {sha} does not match pins.json")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)
    (pth,) = out.glob("python3*._pth")
    stdlib = next(out.glob("python3*.zip")).name
    # Paths are relative to python.exe. `import site` makes Lib/site-packages work as usual.
    pth.write_text(
        f"{stdlib}\n.\nLib\\site-packages\n..\\baker\nimport site\n",
        encoding="utf-8",
        newline="\r\n",
    )
    return sha


def stage_source(out: Path, root: Path = ROOT) -> list[str]:
    files = [f for f in tracked_files(root) if shipped(f)]
    for f in files:
        dest = out / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / f, dest)
    return files


def copy_dlls(src: Path | None, dest: Path) -> list[str]:
    if src is None:
        return []
    names = []
    for dll in sorted(src.glob("*.dll")):
        shutil.copyfile(dll, dest / dll.name)
        names.append(dll.name)
    return names


def site_packages_versions(site: Path) -> dict[str, str]:
    out = {}
    for d in sorted(site.glob("*.dist-info")):
        name, _, version = d.name.removesuffix(".dist-info").partition("-")
        out[name] = version
    return out


def git_commit(root: Path = ROOT) -> str:
    git = shutil.which("git") or "git"
    return subprocess.run(  # noqa: S603 - fixed arguments
        [git, "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--python-zip", type=Path, required=True)
    ap.add_argument("--llama-cpu", type=Path, required=True, help="CPU llama-cpp-python wheel")
    ap.add_argument("--llama-cuda", type=Path, required=True, help="CUDA llama-cpp-python wheel")
    ap.add_argument("--crt-dlls", type=Path, help="MSVC runtime DLLs for the llama runtime")
    ap.add_argument("--cuda-dlls", type=Path, help="CUDA runtime DLLs for the CUDA build")
    a = ap.parse_args(argv)
    pins = json.loads(PINS.read_text(encoding="utf-8"))

    if a.out.exists():
        shutil.rmtree(a.out)
    python = a.out / "python"
    site = python / "Lib" / "site-packages"
    python.mkdir(parents=True)
    python_sha = stage_python(a.python_zip, python, pins["python"])

    # Mabillon's runtime dependencies, plus llama-cpp-python's own (numpy, jinja2, ...), which
    # both runtimes share. The llama_cpp package itself goes in runtime/<variant>/.
    pip_target(site, *runtime_requirements())
    pip_target(site, str(a.llama_cpu))
    for d in [*site.glob("llama_cpp"), *site.glob("llama_cpp_python-*.dist-info")]:
        shutil.rmtree(d)
    for variant, wheel in (("cpu", a.llama_cpu), ("cuda", a.llama_cuda)):
        target = a.out / "runtime" / variant
        pip_target(target, "--no-deps", str(wheel))
        lib = target / "llama_cpp" / "lib"
        copy_dlls(a.crt_dlls, lib)
        if variant == "cuda":
            copy_dlls(a.cuda_dlls, lib)
        shutil.rmtree(target / "bin", ignore_errors=True)  # console scripts point at the stager

    shutil.rmtree(site / "bin", ignore_errors=True)
    files = stage_source(a.out / "baker")
    shutil.copyfile(LAUNCHER, a.out / "baker.cmd")
    shutil.copyfile(LAUNCHER, a.out / "mabillon.cmd")  # the same launcher under the new name

    manifest = {
        str(p.relative_to(a.out).as_posix()): sha256_file(p)
        for p in sorted(a.out.rglob("*"))
        if p.is_file()
    }
    info = {
        "git_commit": git_commit(),
        "python": {"version": pins["python"]["version"], "embed_zip_sha256": python_sha},
        "llama_cpp_python": pins["llama_cpp_python"]["version"],
        "cuda": pins["cuda"]["version"],
        "model": {k: pins["model"][k] for k in ("name", "file", "url", "sha256", "license")},
        "site_packages": site_packages_versions(site),
        "baker_source_files": len(files),
        "sha256": manifest,
    }
    (a.out / "BUILD_INFO.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(f"staged {len(manifest)} files in {a.out}; python embed sha256 {python_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

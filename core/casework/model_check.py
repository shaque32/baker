"""The model check before a first audit: is the model set up, is it the pinned file, does it fit.

Four checks, each with a plain message:
1. The model config exists and is valid (core/audit/_local_model.py: $BAKER_MODEL_CONFIG, else
   ~/.baker/model.json).
2. The model file it names is on this computer.
3. The file's SHA-256 matches the config. Hashing a 9 GB file takes a minute or two, so a pass
   is remembered for that file (path, size and modification time) in ~/.baker/model-check.json;
   a changed file is hashed again.
4. This computer has enough memory: the file's size plus HEADROOM_GB for the context and
   Mabillon itself. Below that the model either does not load or swaps so hard a case never ends.

It also says whether the local model runtime (llama-cpp-python) is installed. Nothing here
loads the model or makes a network call.
"""

from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from core.audit._local_model import ModelConfigError, config_path, load_config

GB = 1024**3
HEADROOM_GB = 4.0  # context cache, the runtime and Mabillon; 14B Q4 (~9 GB) then needs ~13 GB
CACHE = Path.home() / ".baker" / "model-check.json"

Progress = Callable[[int, int], None]  # bytes hashed, bytes total


@dataclass
class ModelCheck:
    ok: bool = False
    lines: list[tuple[str, str]] = field(default_factory=list)  # (ok | warn | fail, message)
    checked_at_utc: str = ""
    model_name: str | None = None

    def add(self, level: str, message: str) -> None:
        self.lines.append((level, message))

    @property
    def summary(self) -> str:
        bad = [m for lvl, m in self.lines if lvl == "fail"]
        return " ".join(bad) if bad else "The model is ready."


def total_memory() -> int | None:
    """Physical memory in bytes, or None if this system does not say."""
    if sys.platform == "win32":

        class _Status(ctypes.Structure):
            _fields_ = [  # noqa: RUF012 - ctypes layout
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = _Status()
        st.dwLength = ctypes.sizeof(_Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined]
            return int(st.ullTotalPhys)
        return None
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (ValueError, OSError, AttributeError):
        return None


def sha256_file(path: Path, progress: Progress | None = None, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    total = path.stat().st_size
    done = 0
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
            done += len(block)
            if progress is not None:
                progress(done, total)
    return h.hexdigest()


def _cache_key(path: Path, expected: str) -> str:
    st = path.stat()
    return f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|{expected}"


def _read_cache(cache: Path) -> dict:
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def check_model(
    config: Path | None = None,
    cache: Path | None = CACHE,
    progress: Progress | None = None,
    memory: Callable[[], int | None] = total_memory,
    runtime_installed: Callable[[], bool] = lambda: (
        importlib.util.find_spec("llama_cpp") is not None
    ),
) -> ModelCheck:
    out = ModelCheck(checked_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    where = config or config_path()
    try:
        cfg = load_config(where)
    except ModelConfigError as e:
        out.add(
            "fail",
            f"No usable model is set up ({e}). Mabillon reads the model's name, file path and "
            f"SHA-256 from {where}.",
        )
        return out
    out.model_name = cfg.name
    out.add("ok", f"Model config found: {cfg.name}, at {where}.")
    if not cfg.path.is_file():
        out.add("fail", f"The model file is not on this computer: {cfg.path}.")
        return out
    size = cfg.path.stat().st_size
    out.add("ok", f"Model file found: {cfg.path} ({size / GB:.1f} GB).")

    key = _cache_key(cfg.path, cfg.sha256)
    cached = _read_cache(cache) if cache is not None else {}
    if cached.get(key) == "match":
        out.add("ok", "SHA-256 matches the config (checked before; the file has not changed).")
    else:
        digest = sha256_file(cfg.path, progress)
        if digest != cfg.sha256:
            out.add(
                "fail",
                f"The model file's SHA-256 is {digest}, not the {cfg.sha256} the config pins. "
                "It is a different or damaged file; Mabillon will not use it.",
            )
            return out
        out.add("ok", "SHA-256 matches the config.")
        if cache is not None:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps({**cached, key: "match"}, indent=1), encoding="utf-8")
            except OSError:
                pass  # the check passed; it simply runs again next time

    need = size / GB + HEADROOM_GB
    have = memory()
    if have is None:
        out.add(
            "warn", f"This system does not report its memory. The model needs about {need:.0f} GB."
        )
    elif have / GB < need:
        out.add(
            "fail",
            f"Not enough memory: the model needs about {need:.0f} GB and this computer has "
            f"{have / GB:.0f} GB. Use a smaller model file or a computer with more memory.",
        )
        return out
    else:
        out.add(
            "ok",
            f"Memory: this computer has {have / GB:.0f} GB; the model needs about {need:.0f} GB.",
        )
    if not runtime_installed():
        out.add(
            "fail",
            "The local model runtime (llama-cpp-python) is not installed in Mabillon's Python. "
            'Install Mabillon with its local extra: pip install -e ".[local]".',
        )
        return out
    out.add("ok", "The local model runtime is installed.")
    out.ok = True
    return out

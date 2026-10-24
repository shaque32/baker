"""Keep the computer awake while an audit runs. A sleeping laptop stops the model mid-claim;
the finished claims are kept either way, but a run that was meant to finish overnight does not.

- Windows: SetThreadExecutionState from the thread that runs the audit.
- macOS: `caffeinate -i -w <this process>` (built in), stopped when the audit ends.
- Linux: `systemd-inhibit` when it is there.
Otherwise nothing is held and the screen says so. The display may still turn off; only system
sleep is blocked. No network, nothing installed.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess  # noqa: S404 - local OS tools only, fixed arguments
import sys
from collections.abc import Iterator
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

NOT_HELD = "Could not keep this computer awake; turn off sleep while the audit runs."


@contextmanager
def keep_awake() -> Iterator[str]:
    """Hold off system sleep for the duration. Yields a sentence saying what is holding it."""
    if sys.platform == "win32":
        kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if kernel.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
            try:
                yield "Kept awake: Windows will not sleep while the audit runs."
            finally:
                kernel.SetThreadExecutionState(ES_CONTINUOUS)
            return
        yield NOT_HELD
        return
    args: list[str] | None = None
    if sys.platform == "darwin" and (exe := shutil.which("caffeinate")):
        args = [exe, "-i", "-w", str(os.getpid())]
        how = "Kept awake: macOS will not sleep while the audit runs (caffeinate)."
    elif exe := shutil.which("systemd-inhibit"):
        sleeper = shutil.which("sleep") or "sleep"
        args = [
            exe,
            "--what=idle:sleep",
            "--who=Mabillon",
            "--why=audit running",
            sleeper,
            "infinity",
        ]
        how = "Kept awake: the system will not sleep while the audit runs (systemd-inhibit)."
    if args is None:
        yield NOT_HELD
        return
    try:
        proc = subprocess.Popen(  # noqa: S603 - absolute path from shutil.which, fixed args
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except OSError:
        yield NOT_HELD
        return
    try:
        proc.wait(timeout=0.5)  # still running after half a second means it holds sleep off
    except subprocess.TimeoutExpired:
        pass
    else:
        yield NOT_HELD
        return
    try:
        yield how
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

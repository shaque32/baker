"""Where Mabillon looks for its settings, cases and demo, and the names it still reads from the
time it was called Baker.

A computer set up before the rename has ~/Baker/cases, ~/Baker/demo and ~/.baker/*.json, and may
set BAKER_* variables. Nothing is moved: a MABILLON_* variable wins over the same BAKER_* one,
and an old folder or settings file is used only while the new one does not exist, so cases and
settings stay where they are until the expert moves them.
"""

from __future__ import annotations

import os
from pathlib import Path

PREFIX = "MABILLON_"
OLD_PREFIX = "BAKER_"


def env(name: str) -> str:
    """$MABILLON_<name>, else $BAKER_<name>, stripped; "" when neither is set."""
    for prefix in (PREFIX, OLD_PREFIX):
        value = os.environ.get(prefix + name, "").strip()
        if value:
            return value
    return ""


def env_in_use(name: str) -> str:
    """The variable env(name) reads: BAKER_<name> only when it alone is set."""
    if (
        os.environ.get(PREFIX + name, "").strip()
        or not os.environ.get(OLD_PREFIX + name, "").strip()
    ):
        return PREFIX + name
    return OLD_PREFIX + name


def _new_or_old(new: Path, old: Path) -> Path:
    return old if old.exists() and not new.exists() else new


def settings_file(name: str, home: Path | None = None) -> Path:
    """~/.mabillon/<name>, or ~/.baker/<name> while only that one exists."""
    home = home or Path.home()
    return _new_or_old(home / ".mabillon" / name, home / ".baker" / name)


def user_folder(name: str, home: Path | None = None) -> Path:
    """~/Mabillon/<name>, or ~/Baker/<name> while only that one exists."""
    home = home or Path.home()
    return _new_or_old(home / "Mabillon" / name, home / "Baker" / name)

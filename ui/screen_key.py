"""The per-launch screen key: only the browser Mabillon opened can use the screen.

The screen listens on 127.0.0.1, which every program and every account on this computer can
reach. Without a key, another account on a shared lab computer could read an open, unlocked case
(and the form token on its pages). So each launch makes a random key:

- `mabillon serve` opens the browser at `/open?key=<key>` (and prints that link). That one
  request sets the key as a cookie (HttpOnly, so no page can read it; SameSite=Strict, so another
  site's page never sends it) and redirects to the screen. Every other request without the
  cookie gets 403, before ui/app.py sees it.
- The cookie is named for the port, because cookies are not kept apart by port: a demo on 8766
  and a real screen on 8765 each keep their own.
- The key is written to ~/.mabillon/screen/<port>.key, readable by this account only, while the
  screen runs, so tools of this account (the install smoke tests, Mabillon's own window) can
  open it. It is removed on exit. Starting Mabillon again while it runs opens a new screen on
  the next free port with a key of its own (cli/main.py _bind).

The key changes on every launch and is never in a page, a log or the case. It guards against
other accounts on the computer, not against programs running as the expert, which could read the
expert's browser and files anyway.
"""

from __future__ import annotations

import hmac
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

HOST = "127.0.0.1"
OPEN_PATH = "/open"
COOKIE_PREFIX = "mabillon_screen_"
REFUSED = (
    "This Mabillon screen opens only in the browser Mabillon started. Open Mabillon again from "
    "its icon or launcher, or use the link `mabillon serve` printed when it started."
)


def _new_key() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class ScreenKey:
    port: int
    value: str = field(default_factory=_new_key, repr=False)

    @property
    def cookie_name(self) -> str:
        return f"{COOKIE_PREFIX}{self.port}"

    def launch_url(self) -> str:
        return f"http://{HOST}:{self.port}{OPEN_PATH}?key={self.value}"

    def set_cookie(self) -> str:
        """A session cookie: it ends when the browser quits, and the key ends with the launch."""
        return f"{self.cookie_name}={self.value}; Path=/; HttpOnly; SameSite=Strict"

    def matches(self, given: str | None) -> bool:
        return given is not None and hmac.compare_digest(given.encode(), self.value.encode())

    def admits(self, cookie_header: str | None) -> bool:
        """Whether a request's Cookie header carries this launch's key."""
        return self.matches(cookie_value(cookie_header, self.cookie_name))


def cookie_value(header: str | None, name: str) -> str | None:
    """The value of one cookie in a Cookie header, or None. Plain splitting: the screen sets
    only its own key, a URL-safe string, so there is nothing to unquote."""
    for part in (header or "").split(";"):
        k, sep, v = part.strip().partition("=")
        if sep and k == name:
            return v
    return None


def key_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".mabillon" / "screen"


def key_file(port: int, home: Path | None = None) -> Path:
    return key_dir(home) / f"{port}.key"


def write_key(key: ScreenKey, home: Path | None = None) -> Path:
    """Write the key for this account only (0600 in a 0700 folder; on Windows the user profile's
    own permissions keep other accounts out)."""
    folder = key_dir(home)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o700)
    except OSError:
        pass
    path = key_file(key.port, home)
    path.unlink(missing_ok=True)  # a new file, so it is made with the mode below
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(key.value)
    return path


def read_key(port: int, home: Path | None = None) -> ScreenKey | None:
    """The running screen's key on this port, or None when there is none to read."""
    try:
        value = key_file(port, home).read_text(encoding="ascii").strip()
    except OSError:
        return None
    return ScreenKey(port, value) if value else None


def remove_key(key: ScreenKey, home: Path | None = None) -> None:
    """Remove the key file, only while it still holds this launch's key."""
    current = read_key(key.port, home)
    if current is not None and key.matches(current.value):
        key_file(key.port, home).unlink(missing_ok=True)

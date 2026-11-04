"""Downloads in Mabillon's own window: the screen saves the file into the Downloads folder.

In a browser, a download (the report, the activity CSV, a request draft, a bug report) is the
browser's job. Web views do it differently on each system, and WebKit's (Mac) fetches the file a
second time outside the page, without the screen key (ui/screen_key.py), so it would save the
refusal instead. In the window, then, the screen writes the file itself and shows the page the
expert came from, saying where the file went. The file holds exactly what the browser would have
saved; nothing else changes.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from ui.app import Response

_NAME = re.compile(r'filename="([^"]+)"')
_SAFE = re.compile(r"[^A-Za-z0-9._ -]")


def downloads_folder(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Downloads"


def attachment_name(resp: Response) -> str | None:
    """The file name a download response offers, made safe for a folder; None when the response
    is a page, not a download."""
    header = resp.header("Content-Disposition") or ""
    if resp.status != 200 or not header.lower().startswith("attachment"):
        return None
    m = _NAME.search(header)
    name = _SAFE.sub("_", Path(m.group(1)).name if m else "").strip(" .")
    return name or "mabillon-download"


def free_path(folder: Path, name: str) -> Path:
    """name in folder, or "name (2)", "name (3)" ... when that is taken: never overwrite."""
    path = folder / name
    stem, suffix = path.stem, path.suffix
    n = 2
    while path.exists():
        path = folder / f"{stem} ({n}){suffix}"
        n += 1
    return path


def save(resp: Response, name: str, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = free_path(folder, name)
    with open(path, "xb") as f:  # x: a file that appeared meanwhile is never overwritten
        f.write(resp.body)
    return path


def back_to(referer: str | None, hosts: set[str]) -> str:
    """The page the download was asked from, when it is this screen's own; else the start."""
    if referer:
        parts = urlsplit(referer)
        if parts.scheme == "http" and parts.netloc in hosts and parts.path.startswith("/"):
            return parts.path + (f"?{parts.query}" if parts.query else "")
    return "/"

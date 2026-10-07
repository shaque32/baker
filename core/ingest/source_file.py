"""Read an input file once, read-only, and hash exactly the bytes that get parsed."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceFile:
    path: Path
    data: bytes
    sha256: str


def read_source(path: Path) -> SourceFile:
    """Open read-only, read all bytes, SHA-256 them. Parsers work on `data`, never on `path`,
    so the hash always describes what was parsed."""
    with path.open("rb") as f:
        data = f.read()
    return SourceFile(path=path, data=data, sha256=hashlib.sha256(data).hexdigest())

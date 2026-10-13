"""Read an input file once, read-only, and hash exactly the bytes that get parsed."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from core.encryption import open_input


@dataclass(frozen=True)
class SourceFile:
    path: Path
    data: bytes
    sha256: str


def read_source(path: Path) -> SourceFile:
    """Open read-only, read all bytes, SHA-256 them. Parsers work on `data`, never on `path`,
    so the hash always describes what was parsed. A copy in an encrypted case is decrypted as
    it is read; the hash is of the plain bytes, the same as the expert's original file."""
    with open_input(path) as f:
        data = f.read()
    return SourceFile(path=path, data=data, sha256=hashlib.sha256(data).hexdigest())

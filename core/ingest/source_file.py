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


class InputChanged(ValueError):
    """The bytes an importer read are not the bytes the caller received (a copy changed after
    its hash was taken). Raised before anything is stored."""

    def __init__(self, name: str, expected: str, actual: str) -> None:
        super().__init__(
            f"{name} is not the file that was received (SHA-256 {expected} then {actual}); "
            "nothing was stored"
        )
        self.expected = expected
        self.actual = actual


def require_sha256(name: str, expected: str | None, actual: str) -> None:
    """Refuse a file whose bytes do not hash to `expected` (when given). Each importer calls
    this after hashing the file and before parsing it, so a changed copy is neither parsed nor
    stored; an importer that streams its parse checks the parsed bytes again before writing."""
    if expected is not None and actual != expected:
        raise InputChanged(name, expected, actual)


def read_source(path: Path) -> SourceFile:
    """Open read-only, read all bytes, SHA-256 them. Parsers work on `data`, never on `path`,
    so the hash always describes what was parsed. A copy in an encrypted case is decrypted as
    it is read; the hash is of the plain bytes, the same as the expert's original file."""
    with open_input(path) as f:
        data = f.read()
    return SourceFile(path=path, data=data, sha256=hashlib.sha256(data).hexdigest())

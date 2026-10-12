"""Streaming multipart/form-data for file uploads to the review screen. Standard library only.

A Cellebrite report can be gigabytes, so the file part is never held in memory: it is written
straight to a file in the case's inputs folder and SHA-256 hashed as it streams. Small fields
(the form token, the file kind) must come before the file part, and `before_file` is called
with them first, so a request without this screen's token is refused before a byte is written.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

CHUNK = 1 << 20
MAX_FIELD = 64 * 1024
MAX_HEADER = 16 * 1024


class UploadError(Exception):
    pass


@dataclass
class Upload:
    fields: dict[str, str] = field(default_factory=dict)
    file_name: str | None = None  # as the browser sent it
    path: Path | None = None
    sha256: str | None = None
    size: int = 0


def boundary(content_type: str) -> bytes:
    m = re.search(r'boundary="?([^";]+)"?', content_type or "")
    if not content_type.lower().startswith("multipart/form-data") or m is None:
        raise UploadError("expected a multipart/form-data upload")
    b = m.group(1).encode("latin-1")
    if not 1 <= len(b) <= 70:
        raise UploadError("bad multipart boundary")
    return b


class _Reader:
    """Reads at most `length` bytes from the stream, with a lookahead buffer."""

    def __init__(self, stream: BinaryIO, length: int) -> None:
        self.stream, self.left, self.buf = stream, length, b""

    def fill(self, want: int) -> bool:
        while len(self.buf) < want and self.left > 0:
            chunk = self.stream.read(min(CHUNK, self.left))
            if not chunk:
                raise UploadError("the upload ended early")
            self.left -= len(chunk)
            self.buf += chunk
        return len(self.buf) >= want

    def take(self, n: int) -> bytes:
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def until(self, marker: bytes, limit: int) -> bytes:
        while (i := self.buf.find(marker)) < 0:
            if len(self.buf) > limit:
                raise UploadError("an upload header or field is too large")
            if not self.fill(len(self.buf) + 1):
                raise UploadError("the upload ended early")
        out = self.buf[:i]
        self.buf = self.buf[i + len(marker) :]
        return out

    def stream_until(self, marker: bytes, write: Callable[[bytes], None]) -> None:
        """Pass everything before `marker` to write, keeping memory to a few chunks."""
        while True:
            i = self.buf.find(marker)
            if i >= 0:
                write(self.buf[:i])
                self.buf = self.buf[i + len(marker) :]
                return
            keep = len(marker) - 1
            if len(self.buf) > keep:
                write(self.buf[: len(self.buf) - keep])
                self.buf = self.buf[len(self.buf) - keep :]
            if not self.fill(len(self.buf) + CHUNK):
                if self.buf.find(marker) < 0:
                    raise UploadError("the upload ended early")


class _Sink:
    """Writes the file part and hashes exactly the bytes written."""

    def __init__(self, f: BinaryIO) -> None:
        self.f, self.sha, self.size = f, hashlib.sha256(), 0

    def write(self, b: bytes) -> None:
        self.sha.update(b)
        self.f.write(b)
        self.size += len(b)


def _disposition(headers: bytes) -> tuple[str, str | None]:
    text = headers.decode("utf-8", errors="replace")
    m = re.search(r"(?im)^content-disposition:\s*form-data(.*)$", text)
    if m is None:
        raise UploadError("an upload part has no form-data disposition")
    params = m.group(1)
    name = re.search(r';\s*name="([^"]*)"', params)
    filename = re.search(r';\s*filename="([^"]*)"', params)
    if name is None:
        raise UploadError("an upload part has no name")
    return name.group(1), (filename.group(1) if filename else None)


def parse(
    stream: BinaryIO,
    length: int,
    content_type: str,
    open_file: Callable[[], Path],
    before_file: Callable[[dict[str, str]], None],
) -> Upload:
    """Parse one upload. open_file() names the file to write the (single) file part to;
    before_file(fields) may raise to refuse the upload before anything is written."""
    delim = b"--" + boundary(content_type)
    r = _Reader(stream, length)
    out = Upload()
    if r.until(b"\r\n", MAX_HEADER) != delim:
        raise UploadError("the upload does not start with its boundary")
    while True:
        headers = r.until(b"\r\n\r\n", MAX_HEADER)
        name, filename = _disposition(headers)
        end = b"\r\n" + delim
        if not filename:  # a plain field, or a file input left empty (filename="")
            value = r.until(end, MAX_FIELD)
            if filename is None:
                if len(out.fields) > 20:
                    raise UploadError("too many form fields")
                out.fields[name] = value.decode("utf-8", errors="replace")
        else:
            if out.path is not None:
                raise UploadError("one file per upload")
            before_file(out.fields)
            out.file_name = filename
            out.path = open_file()
            with out.path.open("xb") as f:
                sink = _Sink(f)
                r.stream_until(end, sink.write)
            out.sha256, out.size = sink.sha.hexdigest(), sink.size
        r.fill(2)
        tail = r.take(2)
        if tail == b"--":
            break
        if tail != b"\r\n":
            raise UploadError("malformed upload")
    if out.path is None:
        raise UploadError("choose a file to upload")
    return out

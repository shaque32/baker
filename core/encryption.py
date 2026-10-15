"""Encryption at rest for a case: its database and the copies of its imported files.

What is encrypted. An encrypted case keeps three things on disk:

    case.db       SQLCipher 4 (AES-256 per page, HMAC-SHA512 per page); its journal is too
    case.key      the case key, wrapped (below); no key in it is usable without a secret
    inputs/*      each copied file in Baker's own format: AES-256-GCM in 1 MiB chunks
    case.cloud-key  only if the expert saved an Anthropic key in this case: that key,
                  AES-256-GCM under the case key (seal_secret), so it opens only with the case

case.json (the case name, the expert's claim order) stays readable, so the case list can name a
locked case. Nothing else in the folder holds case data.

The key. Each case has one random 256-bit key. It is never stored in the clear: case.key holds
it twice, once wrapped (AES-256-GCM) under a key derived from the expert's passphrase (scrypt)
and once under a key derived from a random recovery key that Baker shows once, when the case
is encrypted. Either opens the case. Changing the passphrase re-wraps the case key; nothing is
re-encrypted. A lost passphrase and a lost recovery key mean the case cannot be opened by
anyone, Baker included; the expert's original evidence files are untouched either way.

While Baker runs, an unlocked case key lives in this process's memory only (the keyring
below), so stopping Baker locks every case. Python cannot promise to wipe memory, so a copy
may stay in freed memory until it is reused; the operating system's disk encryption
(FileVault, BitLocker) is still recommended for the computer itself.

File format (inputs). A header, then chunks. The header is

    MAGIC (8) | version (1) | chunk size (4, big-endian) | key id (16) | file id (16)

and every chunk is nonce (12) | ciphertext | tag (16), each holding `chunk size` plain bytes
except the last, which holds the rest (possibly none). Each chunk's associated data is the
header, its index and whether it is the last, so a chunk cannot be moved, swapped in from
another file, dropped from the end or have its end cut off without the read failing. The
SHA-256 Baker records for an imported file is always of the plain bytes, so it still matches
the expert's original file.

`cryptography` and `sqlcipher3` are imported only when an encrypted case is used, so a case
made before encryption existed opens exactly as before, on a computer without them.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import secrets
import struct
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel, ConfigDict, Field

KEY_FORMAT = "baker-case-key/1"
MAGIC = b"BAKERENC"
FILE_VERSION = 1
CHUNK = 1 << 20
KEY_BYTES = 32
NONCE = 12
TAG = 16
_HEADER = struct.Struct(">8sBI16s16s")
HEADER_SIZE = _HEADER.size
SQLITE_HEADER = b"SQLite format 3\x00"

MIN_PASSPHRASE = 12
RECOVERY_BYTES = 20  # 160 bits, 32 base32 characters


class CaseLocked(Exception):
    """The case is encrypted and its key is not unlocked in this process."""


class WrongSecret(Exception):
    """Neither the passphrase nor the recovery key in case.key matches what was entered."""


class EncryptionError(Exception):
    """An encrypted file or key file is damaged, cut short or not Baker's."""


def require() -> None:
    """Raise a plain EncryptionError when this install cannot make or open encrypted cases."""
    try:
        import cryptography.hazmat.primitives.ciphers.aead  # noqa: F401
        import sqlcipher3.dbapi2  # noqa: F401
    except ImportError as err:
        raise EncryptionError(
            f"this install of Baker cannot encrypt cases ({err.name} is missing); run Baker's "
            "installer again, or `pip install -e .` in its folder"
        ) from err


# ---------------------------------------------------------------- key derivation


class Kdf(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = "scrypt"
    n: int = 1 << 17
    r: int = 8
    p: int = 1


DEFAULT_KDF = Kdf()  # about 128 MiB and a fraction of a second per try


def _derive(secret: str, salt: bytes, kdf: Kdf) -> bytes:
    if kdf.name != "scrypt":
        raise EncryptionError(f"unknown key derivation {kdf.name!r}")
    return hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=kdf.n,
        r=kdf.r,
        p=kdf.p,
        maxmem=256 * kdf.n * kdf.r + (1 << 20),
        dklen=KEY_BYTES,
    )


def normalize_passphrase(text: str) -> str:
    """NFKC, so the same passphrase typed on a Mac and on Windows gives the same key."""
    return unicodedata.normalize("NFKC", text)


def check_new_passphrase(passphrase: str, again: str | None = None) -> str:
    """The rules for a new passphrase. Returns it normalized."""
    p = normalize_passphrase(passphrase)
    if again is not None and normalize_passphrase(again) != p:
        raise ValueError("the two passphrases do not match")
    if len(p) < MIN_PASSPHRASE:
        raise ValueError(
            f"use a passphrase of at least {MIN_PASSPHRASE} characters (a few words is easiest)"
        )
    if len(p) > 1024 or any(not ch.isprintable() for ch in p):
        raise ValueError("the passphrase has characters that cannot be typed back reliably")
    return p


def new_recovery_key() -> str:
    raw = base64.b32encode(secrets.token_bytes(RECOVERY_BYTES)).decode("ascii")
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def normalize_recovery_key(text: str) -> str | None:
    """The canonical form of a typed recovery key, or None when it cannot be one."""
    raw = "".join(ch for ch in text.upper() if ch.isalnum())
    raw = raw.translate(str.maketrans({"0": "O", "1": "I", "8": "B"}))
    if len(raw) != 32 or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for ch in raw):
        return None
    return "-".join(raw[i : i + 4] for i in range(0, 32, 4))


# ---------------------------------------------------------------- the key file


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"), validate=True)


def _aesgcm(key: bytes):  # noqa: ANN202 - cryptography's AESGCM, imported only here
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as err:  # pragma: no cover - a broken install
        raise EncryptionError(
            "encrypted cases need the 'cryptography' package; run Baker's installer again"
        ) from err
    return AESGCM(key)


def _invalid_tag() -> type[Exception]:
    from cryptography.exceptions import InvalidTag

    return InvalidTag


class Wrap(BaseModel):
    kind: str  # passphrase | recovery
    kdf: Kdf
    salt: str
    nonce: str
    wrapped: str


class KeyFile(BaseModel):
    format: str = KEY_FORMAT
    key_id: str
    created_at_utc: str
    database: str = "SQLCipher 4 (AES-256, HMAC-SHA512 per page), raw 256-bit key"
    files: str = "AES-256-GCM, 1 MiB chunks, Baker format 1"
    wraps: list[Wrap] = Field(default_factory=list)

    def wrap(self, kind: str) -> Wrap | None:
        return next((w for w in self.wraps if w.kind == kind), None)


def _aad(key_id: str, kind: str) -> bytes:
    return f"{KEY_FORMAT}|{key_id}|{kind}".encode()


def _make_wrap(kind: str, secret: str, dek: bytes, key_id: str, kdf: Kdf) -> Wrap:
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(NONCE)
    kek = _derive(secret, salt, kdf)
    ct = _aesgcm(kek).encrypt(nonce, dek, _aad(key_id, kind))
    return Wrap(kind=kind, kdf=kdf, salt=_b64(salt), nonce=_b64(nonce), wrapped=_b64(ct))


def _open_wrap(w: Wrap, secret: str, key_id: str) -> bytes | None:
    kek = _derive(secret, _unb64(w.salt), w.kdf)
    try:
        dek = _aesgcm(kek).decrypt(_unb64(w.nonce), _unb64(w.wrapped), _aad(key_id, w.kind))
    except _invalid_tag():
        return None
    if len(dek) != KEY_BYTES:
        raise EncryptionError("the case key file holds a key of the wrong length")
    return dek


def new_key_file(
    passphrase: str, kdf: Kdf | None = None, now: datetime | None = None
) -> tuple[KeyFile, bytes, str]:
    """A new case key, wrapped under the passphrase and a new recovery key.
    Returns (key file, case key, recovery key)."""
    kdf = kdf or DEFAULT_KDF
    dek, key_id = secrets.token_bytes(KEY_BYTES), secrets.token_hex(16)
    recovery = new_recovery_key()
    at = (now or datetime.now(UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    kf = KeyFile(
        key_id=key_id,
        created_at_utc=at,
        wraps=[
            _make_wrap("passphrase", check_new_passphrase(passphrase), dek, key_id, kdf),
            _make_wrap("recovery", recovery, dek, key_id, kdf),
        ],
    )
    return kf, dek, recovery


def open_key_file(kf: KeyFile, secret: str) -> bytes:
    """The case key, from the passphrase or the recovery key (either may be typed)."""
    tried = False
    w = kf.wrap("passphrase")
    if w is not None and secret:
        tried = True
        dek = _open_wrap(w, normalize_passphrase(secret), kf.key_id)
        if dek is not None:
            return dek
    rk = normalize_recovery_key(secret)
    w = kf.wrap("recovery")
    if w is not None and rk is not None:
        tried = True
        dek = _open_wrap(w, rk, kf.key_id)
        if dek is not None:
            return dek
    raise WrongSecret(
        "that passphrase or recovery key does not open this case"
        if tried
        else "enter the case's passphrase or recovery key"
    )


def rewrap(kf: KeyFile, dek: bytes, kind: str, secret: str, kdf: Kdf | None = None) -> KeyFile:
    """The same case key, with the `kind` wrap replaced. Nothing else is re-encrypted."""
    w = _make_wrap(kind, secret, dek, kf.key_id, kdf or DEFAULT_KDF)
    return kf.model_copy(update={"wraps": [x for x in kf.wraps if x.kind != kind] + [w]})


def key_path(db: Path) -> Path:
    """case.db -> case.key, some.db -> some.key."""
    return Path(db).with_suffix(".key")


def read_key_file(path: Path) -> KeyFile:
    try:
        kf = KeyFile.model_validate_json(path.read_bytes())
    except ValueError as err:
        raise EncryptionError(f"{path.name} is not a Baker case key file ({err})") from err
    if kf.format != KEY_FORMAT:
        raise EncryptionError(f"{path.name} is in an unknown format {kf.format!r}")
    return kf


def write_key_file(path: Path, kf: KeyFile, *, replace: bool) -> None:
    """Written whole and synced to disk before it is put in place, so a crash leaves the old
    key file or the new one, never half of one."""
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
    data = (json.dumps(kf.model_dump(mode="json"), indent=2) + "\n").encode("utf-8")
    with tmp.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        if not replace and path.exists():
            raise FileExistsError(f"{path.name} already exists")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    _sync_dir(path.parent)


def _sync_dir(folder: Path) -> None:
    if os.name == "nt":  # Windows cannot open a folder to sync it; NTFS journals the rename
        return
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# ---------------------------------------------------------------- the keyring


_keys: dict[str, bytes] = {}
_keys_lock = threading.Lock()


def remember(key_id: str, dek: bytes) -> None:
    with _keys_lock:
        _keys[key_id] = dek


def forget(key_id: str) -> None:
    with _keys_lock:
        _keys.pop(key_id, None)


def forget_all() -> None:
    with _keys_lock:
        _keys.clear()
    _locked()


_lock_hooks: list[Callable[[], None]] = []


def on_lock(hook: Callable[[], None]) -> None:
    """Call hook() whenever this process locks a case or forgets every key, so a module that keeps
    case content in memory drops it with the key (core/selection/audit.py keeps the matcher's
    index of the messages)."""
    if hook not in _lock_hooks:
        _lock_hooks.append(hook)


def _locked() -> None:
    for hook in tuple(_lock_hooks):
        hook()


def unlocked_key(key_id: str) -> bytes | None:
    with _keys_lock:
        return _keys.get(key_id)


# ---------------------------------------------------------------- a case's key


# ---------------------------------------------------------------- small secrets under the case key

SECRET_FORMAT = "baker-case-secret/1"


class SealedSecret(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str = SECRET_FORMAT
    key_id: str
    name: str
    nonce: str
    sealed: str


def secret_path(db: Path, name: str) -> Path:
    """case.db, "cloud-key" -> case.cloud-key, beside the case key."""
    return Path(db).with_suffix(f".{name}")


def seal_secret(db: Path, name: str, value: str) -> Path:
    """Store a small secret (an API key) beside an unlocked case, AES-256-GCM under the case
    key, so it is as unreadable as the case while the case is locked. CaseLocked otherwise."""
    key_id, dek = case_key(db)
    nonce = secrets.token_bytes(NONCE)
    aad = f"{SECRET_FORMAT}|{key_id}|{name}".encode()
    ct = _aesgcm(dek).encrypt(nonce, value.encode("utf-8"), aad)
    s = SealedSecret(key_id=key_id, name=name, nonce=_b64(nonce), sealed=_b64(ct))
    path = secret_path(db, name)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(s.model_dump(mode="json"), indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def open_secret(db: Path, name: str) -> str | None:
    """The secret seal_secret stored for this case, or None if there is none. CaseLocked while
    the case is locked; EncryptionError if the file was altered or belongs to another case."""
    path = secret_path(db, name)
    if not path.is_file():
        return None
    try:
        s = SealedSecret.model_validate_json(path.read_bytes())
    except ValueError as err:
        raise EncryptionError(f"{path.name} is not a sealed Baker secret ({err})") from err
    key_id, dek = case_key(db)
    if s.format != SECRET_FORMAT or s.key_id != key_id or s.name != name:
        raise EncryptionError(f"{path.name} does not belong to this case")
    aad = f"{SECRET_FORMAT}|{key_id}|{name}".encode()
    try:
        return _aesgcm(dek).decrypt(_unb64(s.nonce), _unb64(s.sealed), aad).decode("utf-8")
    except _invalid_tag() as err:
        raise EncryptionError(f"{path.name} was altered and cannot be opened") from err


def is_encrypted_case(db: Path) -> bool:
    """The case has a key file (its database or some of its files may still be plain while an
    interrupted encryption waits to finish)."""
    return key_path(db).is_file()


def is_unlocked(db: Path) -> bool:
    """No key file, or its key is unlocked in this process. A damaged key file counts as
    locked; unlocking then says what is wrong with it."""
    kp = key_path(db)
    if not kp.is_file():
        return True
    try:
        return unlocked_key(read_key_file(kp).key_id) is not None
    except EncryptionError:
        return False


def unlock(db: Path, secret: str) -> bytes:
    """Open the case key with the passphrase or recovery key and keep it for this process."""
    kp = key_path(db)
    if not kp.is_file():
        raise EncryptionError("this case is not encrypted")
    kf = read_key_file(kp)
    dek = open_key_file(kf, secret)
    remember(kf.key_id, dek)
    return dek


def lock(db: Path) -> None:
    kp = key_path(db)
    if kp.is_file():
        forget(read_key_file(kp).key_id)
    _locked()


def case_key(db: Path) -> tuple[str, bytes]:
    """(key id, key) for an unlocked case; CaseLocked otherwise."""
    kp = key_path(db)
    if not kp.is_file():
        raise CaseLocked(
            f"{Path(db).name} is encrypted but its key file {kp.name} is missing; put it back "
            "beside the database"
        )
    kf = read_key_file(kp)
    dek = unlocked_key(kf.key_id)
    if dek is None:
        raise CaseLocked("this case is locked: open it with its passphrase or recovery key")
    return kf.key_id, dek


def create_key(
    db: Path, passphrase: str, kdf: Kdf | None = None, now: datetime | None = None
) -> str:
    """A new key file beside `db`, unlocked. Returns the recovery key, to show once."""
    kf, dek, recovery = new_key_file(passphrase, kdf, now)
    write_key_file(key_path(db), kf, replace=False)
    remember(kf.key_id, dek)
    return recovery


def change_passphrase(db: Path, secret: str, new_passphrase: str, kdf: Kdf | None = None) -> None:
    """Re-wrap the case key under a new passphrase; `secret` is the old passphrase or the
    recovery key. The recovery key stays the same."""
    kp = key_path(db)
    kf = read_key_file(kp)
    dek = open_key_file(kf, secret)
    new = check_new_passphrase(new_passphrase)
    write_key_file(kp, rewrap(kf, dek, "passphrase", new, kdf), replace=True)
    remember(kf.key_id, dek)


def new_recovery(db: Path, kdf: Kdf | None = None) -> str:
    """Replace the recovery key of an unlocked case. Returns the new one, to show once."""
    kp = key_path(db)
    _, dek = case_key(db)
    recovery = new_recovery_key()
    write_key_file(kp, rewrap(read_key_file(kp), dek, "recovery", recovery, kdf), replace=True)
    return recovery


# ---------------------------------------------------------------- the database


def database_is_plain(db: Path) -> bool | None:
    """True for a plain SQLite file, False for anything else, None when there is no file yet
    (or an empty one, which SQLite treats as a new database)."""
    try:
        with Path(db).open("rb") as f:
            head = f.read(len(SQLITE_HEADER))
    except FileNotFoundError:
        return None
    if not head:
        return None
    return head == SQLITE_HEADER


def database_needs_key(db: Path) -> bool:
    plain = database_is_plain(db)
    if plain is None:
        return is_encrypted_case(db)
    return not plain


def sqlcipher_key(dek: bytes) -> str:
    """The PRAGMA key value for a raw 256-bit key (no second key derivation)."""
    return f"x'{dek.hex()}'"


# ---------------------------------------------------------------- files


def _chunk_aad(header: bytes, index: int, last: bool) -> bytes:
    return header + struct.pack(">QB", index, 1 if last else 0)


class EncryptedWriter(io.RawIOBase):
    """Write plain bytes; `close()` writes the last chunk. Does not close `raw`."""

    def __init__(self, raw: BinaryIO, dek: bytes, key_id: str, chunk: int = CHUNK) -> None:
        self.raw, self.chunk, self.index = raw, chunk, 0
        self.gcm = _aesgcm(dek)
        self.header = _HEADER.pack(
            MAGIC, FILE_VERSION, chunk, bytes.fromhex(key_id), secrets.token_bytes(16)
        )
        self.buf = bytearray()
        self.raw.write(self.header)

    def writable(self) -> bool:
        return True

    def _emit(self, data: bytes, last: bool) -> None:
        nonce = secrets.token_bytes(NONCE)
        ct = self.gcm.encrypt(nonce, data, _chunk_aad(self.header, self.index, last))
        self.raw.write(nonce + ct)
        self.index += 1

    def write(self, b: bytes) -> int:  # type: ignore[override]
        if self.closed:
            raise ValueError("write to a closed file")
        self.buf += b
        # Keep at least one byte back so the last chunk is never empty unless the file is.
        while len(self.buf) > self.chunk:
            self._emit(bytes(self.buf[: self.chunk]), last=False)
            del self.buf[: self.chunk]
        return len(b)

    def close(self) -> None:
        # An upload that failed part way has its file closed and deleted first: then there is
        # nothing to finish (this also runs when the writer is garbage collected).
        if not self.closed and not self.raw.closed:
            self._emit(bytes(self.buf), last=True)
            self.buf.clear()
            self.raw.flush()
        super().close()


@dataclass(frozen=True)
class _Layout:
    header: bytes
    chunk: int
    key_id: str
    chunks: int
    size: int  # plain bytes


def _layout(f: BinaryIO, total: int) -> _Layout:
    f.seek(0)
    header = f.read(HEADER_SIZE)
    if len(header) < HEADER_SIZE:
        raise EncryptionError("the encrypted file is cut short (no header)")
    magic, version, chunk, key_id, _file_id = _HEADER.unpack(header)
    if magic != MAGIC:
        raise EncryptionError("not a Baker encrypted file")
    if version != FILE_VERSION or not 1 <= chunk <= 1 << 30:
        raise EncryptionError(f"unknown encrypted file version {version}")
    body = total - HEADER_SIZE
    stored = chunk + NONCE + TAG
    chunks = max(1, -(-body // stored))
    last = body - (chunks - 1) * stored
    if last < NONCE + TAG:
        raise EncryptionError("the encrypted file is cut short")
    return _Layout(header, chunk, key_id.hex(), chunks, (chunks - 1) * chunk + last - NONCE - TAG)


class EncryptedReader(io.RawIOBase):
    """A seekable, read-only view of the plain bytes of an encrypted file. Every chunk read
    is authenticated; a damaged, reordered or truncated file raises EncryptionError."""

    def __init__(self, raw: BinaryIO, dek: bytes) -> None:
        self.raw = raw
        total = raw.seek(0, io.SEEK_END)
        self.lay = _layout(raw, total)
        self.gcm = _aesgcm(dek)
        self.pos = 0
        self._cached: tuple[int, bytes] | None = None

    @property
    def key_id(self) -> str:
        return self.lay.key_id

    @property
    def size(self) -> int:
        return self.lay.size

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.lay.size}[whence]
        if base + offset < 0:
            raise ValueError("negative seek position")
        self.pos = base + offset
        return self.pos

    def _chunk(self, index: int) -> bytes:
        if self._cached is not None and self._cached[0] == index:
            return self._cached[1]
        lay = self.lay
        last = index == lay.chunks - 1
        self.raw.seek(HEADER_SIZE + index * (lay.chunk + NONCE + TAG))
        stored = self.raw.read(lay.chunk + NONCE + TAG)
        try:
            plain = self.gcm.decrypt(
                stored[:NONCE], stored[NONCE:], _chunk_aad(lay.header, index, last)
            )
        except _invalid_tag() as err:
            raise EncryptionError(
                f"the encrypted file is damaged or not this case's (chunk {index})"
            ) from err
        self._cached = (index, plain)
        return plain

    def readinto(self, b) -> int:  # type: ignore[override]  # noqa: ANN001 - a writable buffer
        if self.pos >= self.lay.size:
            return 0
        index, offset = divmod(self.pos, self.lay.chunk)
        data = self._chunk(index)[offset : offset + len(b)]
        n = len(data)
        b[:n] = data
        self.pos += n
        return n

    def readall(self) -> bytes:
        out = bytearray()
        while self.pos < self.lay.size:
            index, offset = divmod(self.pos, self.lay.chunk)
            data = self._chunk(index)[offset:]
            out += data
            self.pos += len(data)
        return bytes(out)

    def close(self) -> None:
        if not self.closed:
            self.raw.close()
        super().close()


def is_encrypted_file(path: Path) -> bool:
    with Path(path).open("rb") as f:
        return f.read(len(MAGIC)) == MAGIC


def _file_key(path: Path, key_id: str) -> bytes:
    dek = unlocked_key(key_id)
    if dek is None:
        raise CaseLocked(
            f"{Path(path).name} is encrypted and its case is locked: open the case with its "
            "passphrase or recovery key first"
        )
    return dek


def open_input(path: Path) -> BinaryIO:
    """Open a copied input read-only: the file itself when it is plain, else a decrypting,
    seekable reader over it (CaseLocked when its case key is not unlocked)."""
    raw = Path(path).open("rb")
    try:
        head = raw.read(HEADER_SIZE)
        if not head.startswith(MAGIC):
            raw.seek(0)
            return raw
        if len(head) < HEADER_SIZE:
            raise EncryptionError(f"{Path(path).name} is cut short (no header)")
        key_id = _HEADER.unpack(head)[3].hex()
        return io.BufferedReader(EncryptedReader(raw, _file_key(path, key_id)), CHUNK)  # type: ignore[return-value]
    except BaseException:
        raw.close()
        raise


def input_size(path: Path) -> int:
    """Plain bytes in a copied input, encrypted or not."""
    with Path(path).open("rb") as raw:
        head = raw.read(len(MAGIC))
        total = raw.seek(0, io.SEEK_END)
        if head != MAGIC:
            return total
        return _layout(raw, total).size


def encrypt_file(
    src: Path,
    dst: Path,
    key_id: str,
    dek: bytes,
    chunk: int = CHUNK,
    progress: Callable[[int], None] | None = None,
) -> str:
    """Encrypt `src` into a new file `dst`; returns the SHA-256 of the plain bytes."""
    sha = hashlib.sha256()
    with src.open("rb") as fin, dst.open("xb") as fout:
        w = EncryptedWriter(fout, dek, key_id, chunk)
        while block := fin.read(CHUNK):
            sha.update(block)
            w.write(block)
            if progress is not None:
                progress(len(block))
        w.close()
        fout.flush()
        os.fsync(fout.fileno())
    return sha.hexdigest()


def plain_sha256(path: Path) -> str:
    """SHA-256 of a copied input's plain bytes, read back through decryption when encrypted."""
    sha = hashlib.sha256()
    with open_input(path) as f:
        while block := f.read(CHUNK):
            sha.update(block)
    return sha.hexdigest()

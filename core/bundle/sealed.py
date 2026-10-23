"""An encrypted bundle: the bundle's zip sealed under a passphrase the examiner chooses.

An encrypted case never exports in plain form. Its bundle is the zip encrypted with AES-256-GCM
under a key derived from a bundle passphrase (scrypt, as for case keys, core/encryption.py),
which the examiner gives counsel, or the other side, by another channel. Layout:

    MAGIC, a 4-byte big-endian header length, the JSON header {kdf, salt, nonce}, then the
    ciphertext of the whole zip, with the header as associated data.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from core import encryption

MAGIC = b"BAKER-BUNDLE-AES256GCM-1\n"


def is_sealed(data: bytes) -> bool:
    return data.startswith(MAGIC)


def is_sealed_file(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(len(MAGIC)) == MAGIC


def seal(data: bytes, passphrase: str, kdf: encryption.Kdf | None = None) -> bytes:
    kdf = kdf or encryption.DEFAULT_KDF
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    header = json.dumps(
        {"kdf": kdf.model_dump(), "salt": encryption._b64(salt), "nonce": encryption._b64(nonce)},
        sort_keys=True,
    ).encode("utf-8")
    key = encryption._derive(encryption.normalize_passphrase(passphrase), salt, kdf)
    body = encryption._aesgcm(key).encrypt(nonce, data, header)
    return MAGIC + len(header).to_bytes(4, "big") + header + body


def open_sealed(blob: bytes, passphrase: str) -> bytes:
    """The zip inside, or WrongSecret for a wrong passphrase or an altered file."""
    if not is_sealed(blob):
        raise encryption.EncryptionError("not an encrypted Baker bundle")
    rest = blob[len(MAGIC) :]
    n = int.from_bytes(rest[:4], "big")
    header, body = rest[4 : 4 + n], rest[4 + n :]
    try:
        h = json.loads(header)
        kdf = encryption.Kdf.model_validate(h["kdf"])
        salt, nonce = encryption._unb64(h["salt"]), encryption._unb64(h["nonce"])
    except (ValueError, KeyError, TypeError) as e:
        raise encryption.EncryptionError(f"the bundle's header cannot be read ({e})") from e
    if kdf != encryption.DEFAULT_KDF or len(salt) != 16 or len(nonce) != 12:
        # The header is read before anything is authenticated, so only the settings seal()
        # writes are accepted: another file cannot make the key derivation fail or run long.
        raise encryption.EncryptionError("the bundle's encryption settings are not ones Baker uses")
    try:
        key = encryption._derive(encryption.normalize_passphrase(passphrase), salt, kdf)
    except (ValueError, MemoryError) as e:
        raise encryption.EncryptionError(f"the bundle's key cannot be derived ({e})") from e
    try:
        return encryption._aesgcm(key).decrypt(nonce, body, header)
    except encryption._invalid_tag() as e:
        raise encryption.WrongSecret(
            "wrong bundle passphrase, or the bundle was changed after it was written"
        ) from e

"""A Mabillon license, checked on this computer with no connection.

The license server (workers/license/, PR 4) signs each license with an Ed25519 key. The app holds
only the public half (`SIGNING_KEYS`), so it can check a license offline and nobody can make one
by editing the file. The signature covers the exact bytes of the license text, which is kept as
received, so no re-encoding can change what was signed.

A license from sign-in must be renewed within 30 days of when it was issued (`GRACE`); the app
renews it at most once a day when it is online (`RENEW_AFTER`). A license file for a lab with no
connection (`offline`) needs no renewal and is good until it expires.

This module imports no network client: tests/test_account.py checks that.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

# Key id -> the license server's Ed25519 public key (32 bytes, hex). Empty until the server's
# signing key is made (PR 4): until then no license verifies, and sign-in stays off
# (account.SIGNIN_ON).
SIGNING_KEYS: dict[str, str] = {}

GRACE = timedelta(days=30)
RENEW_AFTER = timedelta(days=1)
MAX_TEXT = 4096  # a license is a few hundred bytes; anything bigger is not one
LICENSE_ID = re.compile(r"^lic_[A-Za-z0-9]{8,40}$")

State = Literal["signed_out", "active", "renew_due", "lapsed", "expired", "invalid"]


class BadLicense(ValueError):
    """The license text or its signature does not check out."""


class License(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    v: Literal[1]
    aud: Literal["mabillon"]
    kid: str = Field(min_length=1, max_length=40)
    id: str = Field(pattern=LICENSE_ID.pattern)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    plan: str = Field(min_length=1, max_length=40)
    issued_at: AwareDatetime
    expires: AwareDatetime
    offline: bool = False

    @property
    def renew_by(self) -> datetime:
        """When this license stops working without a renewal."""
        if self.offline:
            return self.expires
        return min(self.issued_at + GRACE, self.expires)


@dataclass(frozen=True)
class Signed:
    """A license as the server sent it: its text and the signature over that text."""

    text: str
    signature: str  # base64url, padding optional

    def to_json(self) -> dict[str, str]:
        return {"license": self.text, "signature": self.signature}

    @classmethod
    def from_json(cls, raw: object) -> Signed:
        if not isinstance(raw, dict):
            raise BadLicense("not a license")
        text, sig = raw.get("license"), raw.get("signature")
        if not isinstance(text, str) or not isinstance(sig, str):
            raise BadLicense("not a license")
        if len(text) > MAX_TEXT or len(sig) > 200:
            raise BadLicense("not a license")
        return cls(text, sig)


def _b64(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as err:
        raise BadLicense("the signature is not readable") from err


def verify(signed: Signed, keys: dict[str, str] | None = None) -> License:
    """The license, once its signature checks out against one of our public keys."""
    keys = SIGNING_KEYS if keys is None else keys
    try:
        head = json.loads(signed.text)
    except json.JSONDecodeError as err:
        raise BadLicense("the license is not readable") from err
    kid = head.get("kid") if isinstance(head, dict) else None
    if not isinstance(kid, str) or kid not in keys:
        raise BadLicense("the license was not signed by a key this Mabillon knows")
    try:
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(keys[kid]))
        public.verify(_b64(signed.signature), signed.text.encode("utf-8"))
    except (InvalidSignature, ValueError) as err:
        raise BadLicense("the license's signature does not match") from err
    try:
        lic = License.model_validate(head)
    except ValidationError as err:
        raise BadLicense("the license is missing a field or has a wrong one") from err
    if lic.expires <= lic.issued_at:
        raise BadLicense("the license ends before it starts")
    return lic


@dataclass(frozen=True)
class Stored:
    """What sign-in keeps on this computer: the signed license and, for a license from sign-in,
    the token that renews it (never for a license file)."""

    signed: Signed
    token: str | None = None


@dataclass(frozen=True)
class Status:
    state: State
    message: str
    license: License | None = None

    @property
    def may_start_audit(self) -> bool:
        return self.state in ("active", "renew_due")

    @property
    def wants_renewal(self) -> bool:
        """Whether the app should try to renew now (it may fail offline; that is fine)."""
        return self.state in ("renew_due", "lapsed")


def _day(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%d %B %Y").lstrip("0")


ALWAYS = "Opening cases, review, the report and export still work."


def status(
    stored: Stored | None, now: datetime | None = None, keys: dict[str, str] | None = None
) -> Status:
    """Where this computer's license stands. Plain sentences, for the Account page."""
    now = now or datetime.now(UTC)
    if stored is None:
        return Status("signed_out", "Not signed in.")
    try:
        lic = verify(stored.signed, keys)
    except BadLicense as err:
        return Status("invalid", f"The saved license cannot be used: {err}. Sign in again.")
    if now >= lic.expires:
        return Status(
            "expired",
            f"The license for {lic.email} ended on {_day(lic.expires)}. New audits need a "
            f"current license. {ALWAYS}",
            lic,
        )
    if now >= lic.renew_by:
        return Status(
            "lapsed",
            f"Signed in as {lic.email}, but Mabillon has not reached the license server since "
            f"{_day(lic.issued_at)}. Connect to the internet once to keep starting new audits. "
            f"{ALWAYS}",
            lic,
        )
    good = f"Signed in as {lic.email}. License good through {_day(lic.expires)}."
    if lic.offline:
        good = f"Licensed to {lic.email} from a license file, good through {_day(lic.expires)}."
    due = not lic.offline and stored.token is not None and now >= lic.issued_at + RENEW_AFTER
    return Status("renew_due" if due else "active", good, lic)


# -- on this computer


def account_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".mabillon" / "account"


def license_file(home: Path | None = None) -> Path:
    return account_dir(home) / "license.json"


def save(stored: Stored, home: Path | None = None) -> Path:
    """Write the license for this account only (0600 in a 0700 folder), replacing the old one
    in one step so a crash never leaves half a file."""
    folder = account_dir(home)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o700)
    except OSError:
        pass
    body = stored.signed.to_json()
    if stored.token is not None:
        body["token"] = stored.token
    path = license_file(home)
    # A file of its own for each write (mkstemp makes it 0600), so two Mabillons saving at once
    # never write into or remove each other's; license.json is replaced only once it is closed.
    fd, tmp = tempfile.mkstemp(prefix="license.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(body, f)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def load(home: Path | None = None) -> Stored | None:
    """The saved license, or None when there is none. A file that is not a license loads as one
    whose check fails, so the Account page says so rather than pretending to be signed out."""
    path = license_file(home)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return Stored(Signed("", ""))
    try:
        signed = Signed.from_json(raw)
    except BadLicense:
        return Stored(Signed("", ""))
    token = raw.get("token")
    return Stored(signed, token if isinstance(token, str) and token else None)


def replace_if_unchanged(expected: Stored, new: Stored, home: Path | None = None) -> bool:
    """Save a renewal only if the saved license is still the one it renewed. A sign-out or a new
    sign-in, from this app or from `mabillon license` in another process, may have changed it
    while the renewal was on the network; then the renewal is dropped, never written back."""
    if load(home) != expected:
        return False
    save(new, home)
    return True


def clear(home: Path | None = None) -> None:
    license_file(home).unlink(missing_ok=True)


def read_license_file(data: bytes, keys: dict[str, str] | None = None) -> Stored:
    """A license file for a lab with no connection, checked before it is saved. Only an offline
    license is taken this way; a sign-in license needs its renewal token."""
    if len(data) > MAX_TEXT * 2:
        raise BadLicense("this is not a Mabillon license file")
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as err:
        raise BadLicense("this is not a Mabillon license file") from err
    signed = Signed.from_json(raw)
    lic = verify(signed, keys)
    if not lic.offline:
        raise BadLicense("this license is for sign-in, not a license file")
    return Stored(signed)

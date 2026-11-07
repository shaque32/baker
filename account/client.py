"""The only connection Mabillon makes outside an opted-in case's cloud stance labels: the license
check, to https://account.getmabillon.com and nowhere else.

What each request carries, and nothing more (docs/SECURITY_PRIVACY.md, once signed):

- sign in, once:  the one-time code from the emailed link, its verifier, the Mabillon version
- renew, at most daily when online:  the license id, the sign-in token, the Mabillon version
- sign out:  the license id and the sign-in token

Nothing from any case: no case names, files, records, claims, decisions, notes or folder paths,
and not the computer's name. Every request is written to ~/.mabillon/account/account.log, with
its time and its fields (secrets cut to their first 6 characters), before it is sent.

Nothing calls this while sign-in is off (account.SIGNIN_ON).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from account import ACCOUNT_HOST
from account import license as lic

BASE = f"https://{ACCOUNT_HOST}"
TIMEOUT = 15
MAX_ANSWER = 16 * 1024
SECRET_FIELDS = {"code", "verifier", "token"}

Send = Callable[[urllib.request.Request, float], Any]


class AccountError(Exception):
    """Sign-in or renewal did not go through. `reachable` is False when the server could not be
    reached at all (offline, firewall), so the app keeps its license and tries again later."""

    def __init__(self, message: str, reachable: bool = True, code: str | None = None) -> None:
        super().__init__(message)
        self.reachable = reachable
        self.code = code


def _shown(body: dict[str, str]) -> dict[str, str]:
    return {k: (v[:6] + "…" if k in SECRET_FIELDS else v) for k, v in body.items()}


def log_file(home: Path | None = None) -> Path:
    return lic.account_dir(home) / "account.log"


def _urlopen(req: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - https, one fixed host


class Client:
    def __init__(
        self,
        version: str,
        home: Path | None = None,
        keys: dict[str, str] | None = None,
        send: Send | None = None,
    ) -> None:
        self.version = version
        self.home = home
        self.keys = keys
        self._send = send or _urlopen

    def _log(self, entry: dict[str, object]) -> None:
        path = log_file(self.home)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now(UTC).isoformat(), **entry}) + "\n")

    def _post(self, path: str, body: dict[str, str]) -> dict[str, Any]:
        url = BASE + path
        # logged before it goes: if logging fails, it never goes
        self._log({"send": url, "fields": _shown(body)})
        req = urllib.request.Request(  # noqa: S310 - the URL is BASE, https, built above
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": f"Mabillon/{self.version}"},
            method="POST",
        )
        try:
            with self._send(req, TIMEOUT) as resp:
                status, raw = resp.status, resp.read(MAX_ANSWER + 1)
        except urllib.error.HTTPError as err:
            status, raw = err.code, err.read(MAX_ANSWER + 1) if err.fp else b""
        except (urllib.error.URLError, OSError) as err:
            self._log({"answer": url, "failed": type(err).__name__})
            raise AccountError(
                "Could not reach the license server. Check the internet connection and try again.",
                reachable=False,
            ) from err
        self._log({"answer": url, "status": status})
        try:
            answer = json.loads(raw) if raw and len(raw) <= MAX_ANSWER else {}
        except ValueError:
            answer = {}
        if not isinstance(answer, dict):
            answer = {}
        if status >= 400:
            code = answer.get("error") if isinstance(answer.get("error"), str) else None
            message = answer.get("message")
            raise AccountError(
                message
                if isinstance(message, str) and message
                else f"The license server refused the request ({status}).",
                code=code,
            )
        return answer

    def _stored(self, answer: dict[str, Any], token: str | None) -> lic.Stored:
        try:
            signed = lic.Signed.from_json(answer)
            lic.verify(signed, self.keys)
        except lic.BadLicense as err:
            raise AccountError(
                f"The license server sent a license that does not check: {err}."
            ) from err
        return lic.Stored(signed, token)

    def exchange(self, code: str, verifier: str) -> lic.Stored:
        """The license for a finished browser sign-in."""
        answer = self._post("/api/token", {"code": code, "verifier": verifier, "v": self.version})
        token = answer.get("token")
        if not isinstance(token, str) or not 20 <= len(token) <= 200:
            raise AccountError("The license server's answer had no sign-in token.")
        return self._stored(answer, token)

    def renew(self, stored: lic.Stored) -> lic.Stored:
        """A freshly signed copy of the same license."""
        if stored.token is None:
            raise AccountError("A license file is not renewed.")
        old = lic.verify(stored.signed, self.keys)
        answer = self._post(
            "/api/renew", {"license_id": old.id, "token": stored.token, "v": self.version}
        )
        new = self._stored(answer, stored.token)
        if lic.verify(new.signed, self.keys).id != old.id:
            raise AccountError("The license server sent a different license.")
        return new

    def sign_out(self, stored: lic.Stored) -> None:
        """Ask the server to drop this computer's sign-in token. The caller deletes the license
        here whether or not this reaches the server."""
        if stored.token is None:
            return
        try:
            license_id = lic.verify(stored.signed, self.keys).id
        except lic.BadLicense:
            return
        self._post("/api/signout", {"license_id": license_id, "token": stored.token})

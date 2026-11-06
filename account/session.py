"""Sign-in as the screen sees it: start, finish, renew, sign out, use a license file, and whether
a new audit may start.

cli/main.py builds this with the license client (account/client.py) and the system browser, and
hands it to the screen, so no file in ui/ imports a network client. While sign-in is off
(account.SIGNIN_ON), every audit may start and nothing here connects.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import account
from account import flow
from account import license as lic

RETRY_SECONDS = 60 * 60  # a renewal that failed is tried again after an hour, not on every page


class LicenseServer(Protocol):
    def exchange(self, code: str, verifier: str) -> lic.Stored: ...
    def renew(self, stored: lic.Stored) -> lic.Stored: ...
    def sign_out(self, stored: lic.Stored) -> None: ...


def _message(err: Exception) -> str:
    return str(err) or type(err).__name__


class SignIn:
    def __init__(
        self,
        port: int,
        version: str,
        server: LicenseServer,
        open_browser: Callable[[str], bool],
        home: Path | None = None,
        keys: dict[str, str] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.flow = flow.SignInFlow(port, monotonic)
        self.version = version
        self.server = server
        self.open_browser = open_browser
        self.home = home
        self.keys = keys
        self.clock = clock
        self._monotonic = monotonic
        self._last_try: float | None = None
        self._lock = threading.Lock()

    @property
    def on(self) -> bool:
        return account.SIGNIN_ON

    def stored(self) -> lic.Stored | None:
        return lic.load(self.home)

    def status(self) -> lic.Status:
        return lic.status(self.stored(), self.clock(), self.keys)

    def may_start_audit(self) -> tuple[bool, str]:
        """Whether a new audit may start, and why not. Only new audits are ever held back."""
        if not self.on:
            return True, ""
        self.renew_if_due()
        s = self.status()
        if s.may_start_audit:
            return True, ""
        if s.state == "signed_out":
            return False, "Sign in on the Account page to start a new audit. " + lic.ALWAYS
        return False, s.message

    def start(self) -> str:
        """Open the sign-in page in the system browser. Returns what to tell the examiner."""
        url = self.flow.start(self.version)
        if self.open_browser(url):
            return (
                "Your browser opened Mabillon's sign-in page. Enter your work email there and "
                "click the link we send. You come back here signed in."
            )
        self.flow.cancel()
        return "Mabillon could not open your browser. Try again, or use a license file."

    def finish(self, code: str | None, state: str | None) -> tuple[bool, str]:
        """The browser came back with a code. Returns (signed in, what the browser tab says)."""
        pending = self.flow.take(state)
        if pending is None:
            return False, (
                "This sign-in is out of date or was already used. Start again in Mabillon."
            )
        if not code or len(code) > 200:
            return False, "The sign-in link did not carry a code. Start again in Mabillon."
        try:
            stored = self.server.exchange(code, pending.verifier)
        except Exception as err:  # noqa: BLE001 - every failure is shown, none is fatal
            return False, f"Not signed in: {_message(err)}"
        lic.save(stored, self.home)
        got = lic.status(stored, self.clock(), self.keys)
        if got.license is None:
            return False, f"Not signed in: {got.message}"
        return True, f"Signed in as {got.license.email}. Go back to Mabillon."

    def renew_if_due(self) -> str | None:
        """Renew when the license is due and the last try was over an hour ago. A failure keeps
        the license as it is. Returns a note when a renewal was tried and failed."""
        with self._lock:
            stored = self.stored()
            if stored is None or stored.token is None:
                return None
            if not lic.status(stored, self.clock(), self.keys).wants_renewal:
                return None
            now = self._monotonic()
            if self._last_try is not None and now - self._last_try < RETRY_SECONDS:
                return None
            self._last_try = now
            try:
                lic.save(self.server.renew(stored), self.home)
            except Exception as err:  # noqa: BLE001 - offline is normal; the grace covers it
                return f"The license was not renewed: {_message(err)}"
            return None

    def sign_out(self) -> str:
        stored = self.stored()
        self.flow.cancel()
        if stored is None:
            return "Not signed in."
        note = ""
        try:
            self.server.sign_out(stored)
        except Exception:  # noqa: BLE001 - the license here goes either way
            note = " The license server was not reached, but this computer is signed out."
        lic.clear(self.home)
        return "Signed out on this computer." + note

    def use_license_file(self, data: bytes) -> str:
        stored = lic.read_license_file(data, self.keys)  # BadLicense says what is wrong
        lic.save(stored, self.home)
        return lic.status(stored, self.clock(), self.keys).message

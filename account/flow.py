"""The browser sign-in's one-use values (OAuth 2.0 for native apps, RFC 8252, with PKCE, RFC 7636).

1. `start()` makes a random `state` and a random verifier, and gives the address of the sign-in
   page with the state, the verifier's SHA-256 (the challenge) and the address the browser is to
   come back to: http://127.0.0.1:<port>/signin/done on this screen.
2. The page emails a one-time link. The link sends the browser back with `code` and `state`.
3. `take(state)` hands back the verifier once, within 10 minutes, for the state it made, and
   then forgets it. account/client.py trades the code and the verifier for the license.

Only the app knows the verifier, so a code caught on the way back is no use to anyone else. Only
one sign-in waits at a time: starting again replaces the one before. Nothing here connects.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

from account import ACCOUNT_HOST

DONE_PATH = "/signin/done"
WAIT_SECONDS = 10 * 60


def challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def done_url(port: int) -> str:
    return f"http://127.0.0.1:{port}{DONE_PATH}"


@dataclass(frozen=True)
class Pending:
    state: str
    verifier: str
    made: float


class SignInFlow:
    def __init__(self, port: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.port = port
        self._clock = clock
        self._pending: Pending | None = None

    def start(self, version: str) -> str:
        """A new sign-in: the address to open in the system browser."""
        pending = Pending(secrets.token_urlsafe(32), secrets.token_urlsafe(48), self._clock())
        self._pending = pending
        query = urlencode(
            {
                "state": pending.state,
                "challenge": challenge_for(pending.verifier),
                "challenge_method": "S256",
                "return": done_url(self.port),
                "v": version,
            }
        )
        return f"https://{ACCOUNT_HOST}/signin?{query}"

    def _live(self) -> Pending | None:
        p = self._pending
        if p is not None and self._clock() - p.made > WAIT_SECONDS:
            self._pending = p = None
        return p

    def waiting_for(self, state: str | None) -> bool:
        """Whether a hand-back with this state is the sign-in this screen started (it is not
        used up by asking)."""
        p = self._live()
        return (
            p is not None
            and state is not None
            and hmac.compare_digest(state.encode(), p.state.encode())
        )

    def take(self, state: str | None) -> Pending | None:
        """The waiting sign-in for this state, once; None for any other state, or after it was
        taken, replaced or left for more than 10 minutes."""
        if not self.waiting_for(state):
            return None
        p, self._pending = self._pending, None
        return p

    def cancel(self) -> None:
        self._pending = None

"""The expert review screen's request handling, independent of any socket.

App.handle(Request) -> Response does everything: it checks the request came from this
machine's own pages, reads or changes the case database, and renders a page. ui/server.py
wraps it in the standard library's HTTP server bound to 127.0.0.1; tests call it directly.

Every change goes through core/review/actions.py (evidence, verdicts, claims, stipulations), so
the hash-chained audit log records it with the reviewing expert's name. "Re-run verdicts" goes
through core/review/redecide.py, which calls core/audit/rules.py and the invariants; the screen
never sets a verdict itself. Nothing here makes a network call.

Local-server protections. Another web page open in the same browser can send requests to
127.0.0.1, so:
- the Host header must name this server (127.0.0.1 or localhost on its port), which blocks DNS
  rebinding;
- every POST carries a random token that only this server's own pages contain, and its Origin
  (when the browser sends one) must be this server;
- every response forbids scripts, framing and outside loads (Content-Security-Policy) and is
  never cached.
"""

from __future__ import annotations

import hmac
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from core.audit.invariants import InvariantViolation, check_report_text
from core.contracts import ClaimStatus, ClaimType, EvidenceStatus, Verdict
from core.db import connect
from core.report.html import render_report
from core.review import actions
from core.review.actions import ReviewError
from core.review.redecide import redecide
from ui import pages

CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)
MAX_BODY = 1_000_000


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)  # lower-case names
    form: dict[str, str] = field(default_factory=dict)


@dataclass
class Response:
    status: int
    body: bytes
    headers: list[tuple[str, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def header(self, name: str) -> str | None:
        return next((v for k, v in self.headers if k.lower() == name.lower()), None)


class App:
    def __init__(self, db_path: Path, expert: str | None = None, port: int = 0) -> None:
        if not Path(db_path).exists():
            raise FileNotFoundError(f"no case database at {db_path}")
        self.db_path = Path(db_path)
        self.token = secrets.token_urlsafe(32)
        self.expert: str | None = None
        self.flash: tuple[str, bool] | None = None
        self.port = port
        if expert:
            self.set_expert(expert)

    # -- identity

    def set_expert(self, name: str) -> None:
        name = " ".join(name.split())
        if not name or len(name) > 60 or any(not ch.isprintable() for ch in name):
            raise ReviewError("enter your name (up to 60 characters)")
        self.expert = name

    @property
    def actor(self) -> str:
        if not self.expert:
            raise ReviewError("enter your name on the case page before reviewing")
        return f"expert:{self.expert}"

    # -- request checks

    def allowed_hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def _origin_ok(self, req: Request) -> bool:
        origin = req.headers.get("origin")
        if origin is not None and origin not in {f"http://{h}" for h in self.allowed_hosts()}:
            return False
        site = req.headers.get("sec-fetch-site")
        return site in (None, "same-origin", "none")

    # -- entry point

    def handle(self, req: Request) -> Response:
        if req.headers.get("host") not in self.allowed_hosts():
            return self._plain(400, "This screen only answers requests from this computer.")
        try:
            conn = connect(self.db_path)
        except sqlite3.Error as err:
            return self._plain(500, f"cannot open the case database: {err}")
        try:
            if req.method == "GET":
                return self._get(conn, req)
            if req.method == "POST":
                if not self._origin_ok(req) or not hmac.compare_digest(
                    req.form.get("token", ""), self.token
                ):
                    return self._plain(403, "This form did not come from this review screen.")
                return self._post(conn, req)
            return self._plain(405, "method not allowed")
        finally:
            conn.close()

    # -- GET

    def _page(self) -> pages.Page:
        flash, self.flash = self.flash, None
        return pages.Page(self.token, self.expert, flash)

    def _get(self, conn: sqlite3.Connection, req: Request) -> Response:
        p = req.path
        page = self._page()
        if p == "/":
            return self._html(pages.overview(conn, page))
        if p == "/claims":
            return self._html(pages.claims_queue(conn, page))
        if p == "/claim":
            body = pages.claim_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such claim")
        if p == "/claim/new":
            return self._html(pages.new_claim_page(conn, page))
        if p == "/evidence":
            body = pages.evidence_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such evidence item")
        if p == "/log":
            return self._html(pages.log_page(conn, page, req.query.get("all") == "1"))
        if p in ("/report", "/report.html"):
            resp = self._html(render_report(conn))
            if req.query.get("download") == "1" or p == "/report.html":
                resp.headers.append(
                    ("Content-Disposition", 'attachment; filename="baker-report.html"')
                )
            return resp
        return self._not_found(page, "no such page")

    # -- POST

    def _post(self, conn: sqlite3.Connection, req: Request) -> Response:
        f = req.form
        back = f.get("next", "")
        if not back.startswith("/") or back.startswith("//"):
            back = "/"
        handlers: dict[str, Callable[[], str]] = {
            "/expert": lambda: self._set_expert(f),
            "/evidence/decide": lambda: self._decide(conn, f),
            "/verdict": lambda: self._verdict(conn, f),
            "/claim/edit": lambda: self._edit_claim(conn, f),
            "/claim/add": lambda: self._add_claim(conn, f),
            "/stipulate": lambda: self._stipulate(conn, f),
            "/stipulation/withdraw": lambda: self._withdraw(conn, f),
            "/redecide": lambda: self._redecide(conn),
        }
        handler = handlers.get(req.path)
        if handler is None:
            return self._not_found(self._page(), "no such action")
        try:
            msg = handler()
            self.flash = (msg, False)
            if req.path == "/claim/add":
                back = pages.link("/claim", id=f.get("id", ""))
        except (ReviewError, InvariantViolation, ValueError, sqlite3.IntegrityError) as err:
            self.flash = (f"Not recorded: {err}", True)
        return Response(303, b"", [("Location", back), *self._security_headers()])

    def _set_expert(self, f: dict[str, str]) -> str:
        self.set_expert(f.get("name", ""))
        return f"Reviewing as {self.expert}. Your name is recorded with every decision."

    def _decide(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        status = EvidenceStatus(f.get("status", ""))
        if status == EvidenceStatus.AI_ACCEPTED:
            raise ReviewError("an expert accepts, dismisses or reopens")
        actions.decide_evidence(conn, f.get("id", ""), status, self.actor, f.get("reason", ""))
        return (
            f"Recorded: {status.value}. Re-run the verdicts when you are ready; the verdict does "
            "not change until then."
        )

    def _verdict(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        claim = f.get("claim", "")
        if f.get("action") == "confirm":
            actions.confirm_verdict(conn, claim, self.actor, f.get("note", ""))
            return f"Verdict on {claim} confirmed."
        verdict = Verdict(f.get("verdict", ""))
        actions.override_verdict(conn, claim, verdict, self.actor, f.get("note", ""))
        return f"Verdict on {claim} overridden: {verdict.value}."

    def _edit_claim(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        status = ClaimStatus(f.get("status", ""))
        text = f.get("text") if status == ClaimStatus.EDITED else None
        if text is not None:
            text = text.strip()
            if not text:
                raise ReviewError("the claim text is empty")
        actions.set_claim_status(conn, f.get("claim", ""), status, self.actor, text)
        return f"Claim {f.get('claim', '')} is {status.value}."

    def _add_claim(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        cid = f.get("id", "").strip()
        text = f.get("text", "").strip()
        if not cid or not text:
            raise ReviewError("a claim needs an id and its text")
        para = f.get("paragraph", "")
        if conn.execute("SELECT 1 FROM govdoc_paragraphs WHERE id = ?", (para,)).fetchone() is None:
            raise ReviewError("pick the paragraph the claim comes from")
        actions.add_claim(conn, cid, para, text, ClaimType(f.get("type", "")), self.actor)
        return f"Added {cid}. It needs a full audit before it has a verdict."

    def _stipulate(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        actions.stipulate_device_owner(conn, f.get("device", ""), f.get("person", ""), self.actor)
        return "Stipulation recorded. Re-run the verdicts to apply it."

    def _withdraw(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        actions.withdraw_stipulation(conn, f.get("id", ""), self.actor)
        return "Stipulation withdrawn. Re-run the verdicts to apply it."

    def _redecide(self, conn: sqlite3.Connection) -> str:
        result = redecide(conn, self.actor)
        msg = f"Verdicts re-run with the rules ({len(result.decisions)} claims)."
        if result.skipped:
            msg += " Needs a full audit: " + ", ".join(sorted(result.skipped)) + "."
        return msg

    # -- responses

    @staticmethod
    def _security_headers() -> list[tuple[str, str]]:
        return [
            ("Content-Security-Policy", CSP),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
            ("Cache-Control", "no-store"),
        ]

    def _html(self, body: str, status: int = 200) -> Response:
        try:
            check_report_text(body)
        except InvariantViolation as err:
            return self._plain(500, f"page withheld: {err}")
        return Response(
            status,
            body.encode("utf-8"),
            [("Content-Type", "text/html; charset=utf-8"), *self._security_headers()],
        )

    def _not_found(self, page: pages.Page, message: str) -> Response:
        return self._html(pages.error_page(page, 404, message), 404)

    def _plain(self, status: int, message: str) -> Response:
        return Response(
            status,
            message.encode("utf-8"),
            [("Content-Type", "text/plain; charset=utf-8"), *self._security_headers()],
        )

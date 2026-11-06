"""The expert review screen's request handling, independent of any socket.

App.handle(Request) -> Response does everything: it checks the request came from this
machine's own pages, reads or changes the case database, and renders a page. App.handle_upload
does the same for a file upload, streamed to disk (ui/upload.py). ui/server.py wraps both in the
standard library's HTTP server bound to 127.0.0.1; tests call them directly.

Starting a case. Started on a cases folder (`mabillon serve`), the screen lists the cases and makes
new ones (core/casework/cases.py). "Set up and run" imports files into the case folder (copied,
read-only, SHA-256 hashed), proposes claims with the local model, takes the expert's claim
decisions, claim order and device-owner stipulations, checks the model, and runs the audit in
the background (core/casework/jobs.py). While it runs, finished claims can be reviewed; claims
it has not finished say "Labeling incomplete", and nothing that would make the run inconsistent
(new files, claim changes, stipulations, re-running the verdicts) is accepted until it ends.

Every change goes through core/review/actions.py (evidence, verdicts, claims, stipulations), so
the hash-chained audit log records it with the reviewing expert's name. "Re-run verdicts" goes
through core/review/redecide.py, which calls core/audit/rules.py and the invariants; the screen
never sets a verdict itself. Nothing here makes a network call.

Each case page the examiner opens is recorded in the same audit log as a `view` entry, with the
time, the examiner's name, the page and the evidence it listed (core/review/activity.py). The
Activity page shows that trail with time on each page; a view never changes a verdict.

Local-server protections. Every request first needs this launch's screen key, which ui/server.py
checks before handle() runs (ui/screen_key.py), so another account on the computer cannot read
the screen. Another web page open in the same browser can send requests to 127.0.0.1, so:
- the Host header must name this server (127.0.0.1 or localhost on its port), which blocks DNS
  rebinding;
- every POST carries a random token that only this server's own pages contain, and its Origin
  (when the browser sends one) must be this server;
- every response forbids scripts, framing and outside loads (Content-Security-Policy) and is
  never cached.
"""

from __future__ import annotations

import functools
import hmac
import html
import json
import re
import secrets
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from urllib.parse import parse_qs, urlsplit

from core import db, encryption, pipeline
from core.audit.invariants import InvariantViolation, check_report_text
from core.casework import cases, jobs, protect
from core.casework import cloud as cloud_policy
from core.casework.model_check import ModelCheck, check_model
from core.contracts import (
    ClaimStatus,
    ClaimType,
    EvidenceStatus,
    ExcerptSplit,
    IdentityLinkStatus,
    Verdict,
)
from core.db import CaseLocked, connect
from core.encryption import EncryptionError
from core.identity.links import propose_links
from core.llm import cloud as cloud_llm
from core.report.html import Header as ReportHeader
from core.report.html import render_report
from core.report.letter import request_letter
from core.restore.store import ExhibitError, add_exhibit, match_exhibits, remove_exhibit
from core.review import actions, activity, audit_log, flags, withheld
from core.review.actions import ReviewError
from core.review.redecide import redecide
from core.review.status import claim_names, claim_state
from core.review.status import claim_states as claim_states_now
from core.support import bug_report
from core.timeline import settings as timeline_settings
from ui import (
    help_pages,
    identity_pages,
    pages,
    restore_pages,
    selection_pages,
    theme,
    timeline_pages,
    upload,
)

CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; font-src 'self'; img-src 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)
FONT_PREFIX = "/static/fonts/"
MAX_BODY = 1_000_000
TEXTAREA = re.compile(r"<textarea([^>]*)>[^<]*</textarea>")
MAX_UPLOAD = 16 * 1024**3  # a full Cellebrite PDF report can run to gigabytes

# What each action needs: an open case, and no background job of these kinds running.
NEEDS_NO_JOB: dict[str, tuple[str, ...]] = {
    "/claim/edit": ("audit",),
    "/claim/add": ("audit", "propose"),
    "/claims/move": ("audit",),
    "/claims/accept_all": ("audit", "propose"),
    "/stipulate": ("audit",),
    "/stipulation/withdraw": ("audit",),
    "/device/names": ("audit",),
    "/person/add": ("audit",),
    "/person/remove": ("audit",),
    "/person/aliases": ("audit",),
    "/person/alias/add": ("audit",),
    "/event/add": ("audit",),
    "/event/remove": ("audit",),
    "/identity/decide": ("audit",),
    "/identity/link": ("audit",),
    "/identity/look": ("audit",),
    "/redecide": ("audit",),
    "/evidence/confirm": ("audit",),
    "/testability/decide": ("audit",),
    "/testability/confirm": ("audit",),
    "/claims/propose": ("audit", "propose", "model_check"),
    "/model/check": ("audit", "propose", "model_check"),
    "/audit/start": ("audit", "propose", "model_check"),
    "/cloud/case": ("audit",),
    "/cloud/key": ("audit",),
    "/cloud/key/remove": ("audit",),
    "/case/import": ("audit", "propose", "model_check"),
    "/case/remove_file": ("audit", "propose", "model_check"),
    "/case/new": ("audit", "propose", "model_check"),
    "/case/open": ("audit", "propose", "model_check"),
    "/case/encrypt": ("audit", "propose", "model_check"),
    "/case/lock": ("audit", "propose", "model_check"),
}
NO_CASE_GET = {"/cases"}
HELP_GET = {"/help", "/help/bug-report.json"}  # with or without a case open
NO_CASE_POST = {"/expert", "/case/new", "/case/open"}
# Posts that must not have the case database open while they run: encrypting replaces the
# database file (Windows cannot replace an open file), and locking forgets its key.
OWN_DB_POST = {"/case/encrypt", "/case/lock", "/case/recovery/done"}


_EVIDENCE_HREF = re.compile(r"""href=['"](/evidence\?[^'"]*)['"]""")


def listed_evidence(html_text: str) -> list[str]:
    """The evidence items a rendered page links to (its /evidence?id= links), in page order,
    each once. A link stands for an item the page listed, not one the examiner opened."""
    seen: dict[str, None] = {}
    for m in _EVIDENCE_HREF.finditer(html_text):
        for v in parse_qs(urlsplit(html.unescape(m.group(1))).query).get("id", []):
            seen.setdefault(v, None)
    return list(seen)


def _real_components(
    conn: sqlite3.Connection, ai_review: bool, cloud: cloud_policy.CloudChoice | None = None
) -> pipeline.Components:
    return pipeline.real_components(conn, ai_review=ai_review, cloud=cloud)


def _real_extractor(conn: sqlite3.Connection) -> object:
    from core.claims import extract

    return extract.create(conn)


class _Refused(Exception):
    pass


class _Counting:
    """Counts what a parser read, so the rest of a refused upload can be drained."""

    def __init__(self, stream: BinaryIO) -> None:
        self.stream, self.read_bytes = stream, 0

    def read(self, n: int = -1) -> bytes:
        b = self.stream.read(n)
        self.read_bytes += len(b)
        return b


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
    """One screen. Either on one case database (`db_path`, as `mabillon serve --db`) or on a cases
    folder (`home`), where the expert makes and opens cases.

    components_for, extractor_for and model_check build the real local-model parts by default;
    tests pass stand-ins. model_check=None skips the model check (a test without a model)."""

    def __init__(
        self,
        db_path: Path | None = None,
        expert: str | None = None,
        port: int = 0,
        *,
        home: Path | None = None,
        components_for: jobs.ComponentsFor | None = None,
        extractor_for: jobs.ExtractorFor | None = None,
        model_check: jobs.ModelCheckFn | None = check_model,
        cloud_config: Path | None = None,
        name_file: Path | None = None,
    ) -> None:
        if db_path is None and home is None:
            raise ValueError("give a case database or a cases folder")
        if db_path is not None and not Path(db_path).exists():
            raise FileNotFoundError(f"no case database at {db_path}")
        self.home = None if db_path is not None else Path(home)  # type: ignore[arg-type]
        self.single = None if db_path is None else cases.Case(Path(db_path))
        self.case: cases.Case | None = None
        self.recovery: tuple[Path, str] | None = None  # a recovery key to show once
        self.token = secrets.token_urlsafe(32)
        self.expert: str | None = None
        self.flash: tuple[str, bool] | None = None
        self.port = port
        self.path = ""  # the request being answered, so a page can mark its tab
        self._stand_in = ""  # the open case's demo or test-run banner, set per request
        self._added: str | None = None
        self.jobs = jobs.Jobs()
        self._reported: jobs.Job | None = None  # the finished job whose result Set up showed
        self._claim_draft: dict[str, str] | None = None  # a refused Add a claim, to refill
        self.components_for = components_for or _real_components
        self.extractor_for = extractor_for or _real_extractor
        self.model_check = model_check
        self.last_check: ModelCheck | None = None
        self.session = secrets.token_hex(8)  # names this screen's page views in the trail
        self._last_view: tuple[tuple, datetime] | None = None  # the last page loaded, and when
        self._unrecorded: list[str] = []  # views that could not be written, not yet shown
        self.clock: Callable[[], datetime] = lambda: datetime.now(UTC)
        self.cloud_config = (
            cloud_config  # None: $MABILLON_CLOUD_CONFIG, else ~/.mabillon/cloud.json
        )
        # The examiner's name is remembered on this computer (the server passes the settings
        # file; tests and one-off screens do not), so a restart does not ask for it again.
        self.name_file = name_file
        if not expert and name_file is not None:
            try:
                expert = json.loads(name_file.read_text(encoding="utf-8")).get("name")
            except (OSError, ValueError, AttributeError):
                expert = None
        if expert:
            try:
                self.set_expert(expert)
            except ReviewError:
                self.expert = None
        if self.single is not None and not protect.is_locked(self.single):
            try:
                self.open_case(self.single)
            except audit_log.ChainBroken as err:  # the screen starts, the case stays shut
                self.flash = (f"Not opened: {err}", True)

    def _open(self) -> cases.Case:
        if self.case is None:
            raise ReviewError("open or make a case first")
        return self.case

    @property
    def db_path(self) -> Path | None:
        return None if self.case is None else self.case.db

    def open_case(self, case: cases.Case) -> None:
        if protect.is_locked(case):
            raise CaseLocked("this case is locked: open it with its passphrase or recovery key")
        conn = connect(case.db)
        anchors = audit_log.anchors_path(case.db)
        try:
            # a broken or cut-short log fails closed: no review, no writes
            audit_log.require_intact(conn, anchors)
            audit_log.anchor(conn, anchors)  # first, so an unwritable anchor changes nothing
            if pipeline.mark_stale_runs_stopped(conn):  # nothing in this process runs them
                audit_log.anchor(conn, anchors)
        except audit_log.ChainBroken:
            if self.case is not None and self.case.db == case.db:  # re-opened after tampering
                self._close_broken(case)
            raise
        finally:
            conn.close()
        self.case = case
        self.last_check = None

    def _close_broken(self, case: cases.Case) -> None:
        """Close the open case whose log no longer verifies, stop a background job on it (it
        stops after the claim or paragraph in hand), and lock the case if it is encrypted."""
        job = self.jobs.current
        if job is not None and job.running and job.db == case.db:
            job.stop.set()
        self.case = None
        self.recovery = None
        self.last_check = None
        if protect.state(case) != "plain":
            protect.lock(case)

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
        self.path = req.path
        self._stand_in = ""
        if req.headers.get("host") not in self.allowed_hosts():
            return self._plain(400, "This screen only answers requests from this computer.")
        if req.method not in ("GET", "POST"):
            return self._plain(405, "method not allowed")
        if req.method == "GET" and req.path.startswith(FONT_PREFIX):
            return self._font(req.path[len(FONT_PREFIX) :])
        if req.method == "POST" and not self._origin_ok(req):
            return self._plain(403, "This form did not come from this review screen.")
        if req.method == "POST" and not hmac.compare_digest(req.form.get("token", ""), self.token):
            return self._stale_page()
        if req.method == "POST":
            self._last_view = None  # whatever the post did, the next page is a new view
        if req.method == "GET" and req.path in HELP_GET:
            if self._opened_here(req):
                self._last_view = None  # the examiner left the case pages
            return self._help(req.path)
        if self.case is None:
            if req.method == "GET" and req.path not in NO_CASE_GET:
                return self._redirect("/cases")
            if req.method == "POST" and req.path not in NO_CASE_POST:
                self.flash = ("Open or make a case first.", True)
                return self._redirect("/cases")
            if req.method == "GET":
                return self._cases()
            return self._post(None, req)
        if protect.is_locked(self.case):
            self.case = None
            self.flash = ("The case is locked. Open it with its passphrase.", True)
            return self._redirect("/cases")
        if req.method == "POST" and req.path not in NO_CASE_POST:  # opening a case is fine
            stale = self._stale_case(req.form)
            if stale is not None:
                self.flash = (stale, True)
                return self._redirect("/")
        if req.method == "POST" and req.path in OWN_DB_POST:
            return self._post(None, req)
        try:
            conn = connect(self.case.db)
            conn.execute("PRAGMA busy_timeout = 10000")  # an audit may be saving a claim
        except CaseLocked as err:
            self.case = None
            self.flash = (str(err), True)
            return self._redirect("/cases")
        except db.Error as err:
            return self._plain(500, f"cannot open the case database: {err}")
        try:  # the log may have changed since the case opened: every page checks it again
            audit_log.require_intact(conn, audit_log.anchors_path(self.case.db))
        except audit_log.ChainBroken as err:
            conn.close()
            self._close_broken(self.case)
            what = "No report" if req.path in ("/report", "/report.html") else "Case closed"
            self.flash = (f"{what}: {err}", True)
            return self._redirect("/cases")
        try:
            self._stand_in = pages.stand_in_note(conn)
        except (*db.Error, InvariantViolation):
            # the banner never stops a request: a run the case cannot read shows none here, and
            # the page the request opens says what is wrong with it
            self._stand_in = ""
        try:
            if req.method == "GET":
                if req.path in activity.RECORD_FIRST:  # it shows the trail up to itself
                    self._note_view(conn, req, None)
                    return self._unrecorded_warning(self._get(conn, req))
                resp = self._get(conn, req)
                self._note_view(conn, req, resp)
                return self._unrecorded_warning(resp)
            return self._post(conn, req)
        except pipeline.StoredVerdictInvalid as err:  # a GET only: _post flashes it
            self._last_view = None  # not a view of the page asked for
            back = pages.link(req.path, **req.query) if req.path in activity.PAGES else "/"
            return self._html(pages.stored_verdict_page(self._page(), str(err), back), 409)
        finally:
            conn.close()

    def _stale_page(self) -> Response:
        """A post whose token this screen never issued: almost always a tab left open from
        before Mabillon was restarted (each start makes a new token). Nothing was saved."""
        page = self._page()
        return self._html(
            pages.error_page(
                page,
                403,
                "This page is out of date: Mabillon was restarted after it opened, so nothing "
                "was saved. Open the case again and make the change there.",
            ),
            403,
        )

    def _stale_case(self, form: dict[str, str]) -> str | None:
        """Why a post must be refused because its page was drawn for another case (a second tab
        opened a different case since), or None. A form names its case in for_case; a post
        that does not (an older test client) is taken as meant for the open case."""
        sent = form.get("for_case", "")
        if not sent or self.case is None or sent == _case_key(self.case):
            return None
        meant = sent
        if self.home is not None:
            meant = next(
                (c.name for c in cases.list_cases(self.home) if _case_key(c) == sent), sent
            )
        return (
            f"Nothing was saved: that page was for the case {meant}, but {self.case.name} is "
            "open now (it was opened in another tab or window). Open the right case from Cases "
            "and make the change there."
        )

    def _note_view(self, conn: sqlite3.Connection, req: Request, resp: Response | None) -> None:
        """Record the page the examiner just opened in the case's audit log (core/review/
        activity.py), with the evidence the rendered page links to. A page that shows the trail
        or the log (resp None) is recorded before it renders, so it includes itself. A reload of
        the same page within activity.REFRESH of the last load, with nothing posted between, is
        the same view and is not recorded again (the audit progress page refreshes itself every
        few seconds); a later reload, such as the page reopened after the screen was closed, is
        a new view."""
        if not self._opened_here(req):
            return  # another site's request (an image tag, a fetch) is not the examiner's view
        if (resp is not None and resp.status != 200) or req.path not in activity.PAGES:
            self._last_view = None  # the examiner went elsewhere, so the next page is new
            return
        if self.case is None:
            return
        key = (str(self.case.db), self.expert, req.path, tuple(sorted(req.query.items())))
        now = self.clock()
        if self._last_view is not None and self._last_view[0] == key:
            if now - self._last_view[1] <= activity.REFRESH:
                self._last_view = (key, now)  # a page refreshing itself stays one view
                return
        listed: list[str] = []
        if resp is not None and (resp.header("Content-Type") or "").startswith("text/html"):
            listed = listed_evidence(resp.text)
        try:
            activity.record_view(
                conn,
                now,
                f"expert:{self.expert}" if self.expert else None,
                req.path,
                session=self.session,
                query=req.query,
                listed=listed,
            )
        except db.Error as err:  # busy past the timeout, or a full disk: say so, never hide it
            page = activity.PAGES.get(req.path, req.path)
            self._unrecorded.append(f"{page} ({err})")
            self._last_view = None  # the examiner left the last recorded page all the same
            return
        self._last_view = (key, now)

    def _opened_here(self, req: Request) -> bool:
        """A page the examiner opened in this screen: a document load from this server, or one
        typed or bookmarked. Browsers send Sec-Fetch headers; one that sends none is taken at
        its word, as for the forms."""
        dest = req.headers.get("sec-fetch-dest")
        return self._origin_ok(req) and dest in (None, "document")

    def _unrecorded_warning(self, resp: Response) -> Response:
        """Put the views Mabillon could not record at the top of this page, if it is a page shown
        on screen; a download carries none, so the warning waits for the next page shown."""
        if not self._unrecorded or resp.status != 200 or resp.header("Content-Disposition"):
            return resp
        if not (resp.header("Content-Type") or "").startswith("text/html"):
            return resp
        text = resp.text
        at = text.find("<main")
        at = text.find(">", at if at >= 0 else text.find("<body")) + 1
        if at <= 0:
            return resp
        warning = (
            "<div class='flash err' role='alert'>Mabillon could not record that you opened these "
            "pages, so they are not in the activity trail: "
            + html.escape("; ".join(self._unrecorded))
            + ".</div>"
        )
        self._unrecorded = []
        resp.body = (text[:at] + warning + text[at:]).encode("utf-8")
        return resp

    # -- GET

    def _job(self, *kinds: str) -> jobs.Job | None:
        job = self.jobs.current
        if job is None or (kinds and job.kind not in kinds):
            return None
        if self.case is None or job.db != self.case.db:
            return None
        return job

    def _page(self) -> pages.Page:
        flash, self.flash = self.flash, None
        notice, busy = "", False
        job = self._job()
        if job is not None and job.running:
            busy = job.kind == "audit"
            what = {
                "audit": f"The audit is running: {job.done} of {job.total} claims finished."
                + ("" if self.path == "/run" else " <a href='/run'>See its progress</a>."),
                "propose": f"The local model is proposing claims: {job.done} of {job.total} "
                "paragraphs. <a href='/setup'>See the claims</a>.",
                "model_check": "Checking the model. <a href='/setup'>See the result</a>.",
            }
            notice = what[job.kind]
        return pages.Page(
            self.token,
            self.expert,
            flash,
            case_name=None if self.case is None else self.case.name,
            notice=notice,
            busy=busy,
            many_cases=self.home is not None,
            path=self.path,
            cloud=self._case_uses_cloud(),
            case_key="" if self.case is None else _case_key(self.case),
            stand_in=self._stand_in if self.case is not None else "",
        )

    def _get(self, conn: sqlite3.Connection, req: Request) -> Response:
        p = req.path
        if p == "/cases":
            return self._cases()
        if p == "/setup":
            return self._html(self._setup(conn))
        if p == "/run":
            return self._html(self._run(conn))
        page = self._page()
        if p == "/":
            return self._html(pages.overview(conn, page))
        if p == "/claims":
            return self._html(pages.claims_queue(conn, page, self._next_step(conn)))
        if p == "/claim":
            body = pages.claim_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such claim")
        if p == "/claim/new":
            draft, self._claim_draft = self._claim_draft, None
            return self._html(pages.new_claim_page(conn, page, draft))
        if p == "/evidence":
            body = pages.evidence_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such evidence item")
        if p == "/identities":
            return self._html(identity_pages.identities_page(conn, page))
        if p == "/exhibits":
            return self._html(restore_pages.exhibits_page(conn, page))
        if p == "/exhibit":
            body = restore_pages.exhibit_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such exhibit")
        if p == "/exhibit/match":
            body = restore_pages.match_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such match")
        if p == "/selection":
            return self._html(selection_pages.selection_page(conn, page, self._timeline()))
        if p == "/selection/context":
            body = selection_pages.context_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such message")
        if p == "/request-letter":
            return self._html(restore_pages.letter_page(conn, page))
        if p == "/timeline":
            return self._html(timeline_pages.timeline_page(conn, page, self._timeline()))
        if p == "/gaps":
            return self._html(timeline_pages.gaps_page(conn, page, self._timeline()))
        if p == "/request-letter.txt":
            return self._letter_text(conn, page)
        if p == "/flags/summary.json":
            body = flags.summary_json(conn, req.query.get("pilot", ""))
            return Response(
                200,
                body.encode("utf-8"),
                [
                    ("Content-Type", "application/json; charset=utf-8"),
                    ("Content-Disposition", 'attachment; filename="mabillon-flag-summary.json"'),
                    *self._security_headers(),
                ],
            )
        if p == "/log":
            q = req.query
            return self._html(
                pages.log_page(conn, page, q.get("all") == "1", q.get("views") == "1")
            )
        if p == "/activity":
            return self._html(
                pages.activity_page(
                    conn, page, req.query.get("claim", ""), req.query.get("all") == "1"
                )
            )
        if p == "/activity.csv":
            return Response(
                200,
                activity.csv_text(activity.steps(conn)).encode("utf-8"),
                [
                    ("Content-Type", "text/csv; charset=utf-8"),
                    ("Content-Disposition", 'attachment; filename="mabillon-activity.csv"'),
                    *self._security_headers(),
                ],
            )
        if p in ("/report", "/report.html"):
            case = self._open()
            try:  # handle() checked the log; anchor its newest entry before the report goes out
                audit_log.anchor(conn, audit_log.anchors_path(case.db))
            except audit_log.ChainBroken as err:
                self._close_broken(case)
                self.flash = (f"No report: {err}", True)
                return self._redirect("/cases")
            made = self.clock()
            header = ReportHeader(case.name, self.expert, made)
            body = render_report(conn, timeline=self._timeline(), header=header)
            download = req.query.get("download") == "1" or p == "/report.html"
            if not download:  # on screen, the vendored fonts; a saved copy uses system fonts
                body = body.replace("<style>", f"<style>{theme.FONT_CSS}", 1)
                # On screen only: a way back into the app and a way to save it.
                body = body.replace(
                    "<h1>Mabillon claims report</h1>",
                    "<p class='screen-only' style='margin:0 0 12px'><a href='/'>Back to the "
                    "case</a> · <a href='/report?download=1'>Save this report (HTML)</a></p>"
                    "<h1>Mabillon claims report</h1>",
                    1,
                )
            resp = self._html(body)
            if download:
                name = _report_file_name(case.name, made)
                resp.headers.append(("Content-Disposition", f'attachment; filename="{name}"'))
            return resp
        return self._not_found(page, "no such page")

    # -- POST

    def _post(self, conn: sqlite3.Connection | None, req: Request) -> Response:
        f = req.form
        back = f.get("next", "")
        if not back.startswith("/") or back.startswith("//"):
            back = "/"
        handlers: dict[str, Callable[[], str]] = {
            "/expert": lambda: self._set_expert(conn, f),
            "/case/new": lambda: self._new_case(f),
            "/case/open": lambda: self._open_case(f),
            "/case/encrypt": lambda: self._encrypt(f),
            "/case/lock": lambda: self._lock(),
            "/case/passphrase": lambda: self._change_passphrase(f),
            "/case/recovery/done": lambda: self._recovery_done(),
            "/case/recovery/new": lambda: self._new_recovery(f),
            "/case/remove_file": lambda: self._remove_file(conn, f),  # type: ignore[arg-type]
            "/evidence/decide": lambda: self._decide(conn, f),  # type: ignore[arg-type]
            "/evidence/confirm": lambda: self._confirm(conn, f),  # type: ignore[arg-type]
            "/verdict": lambda: self._verdict(conn, f),  # type: ignore[arg-type]
            "/rationale/acknowledge": lambda: self._acknowledge(conn, f),  # type: ignore[arg-type]
            "/claim/edit": lambda: self._edit_claim(conn, f),  # type: ignore[arg-type]
            "/claims/accept_all": lambda: self._accept_all(conn, f),  # type: ignore[arg-type]
            "/claim/add": lambda: self._add_claim(conn, f),  # type: ignore[arg-type]
            "/claims/move": lambda: self._move_claim(conn, f),  # type: ignore[arg-type]
            "/claims/propose": lambda: self._propose(),
            "/stipulate": lambda: self._stipulate(conn, f),  # type: ignore[arg-type]
            "/stipulation/withdraw": lambda: self._withdraw(conn, f),  # type: ignore[arg-type]
            "/device/names": lambda: self._name_device(conn, f),  # type: ignore[arg-type]
            "/person/add": lambda: self._add_person(conn, f),  # type: ignore[arg-type]
            "/person/remove": lambda: self._remove_person(conn, f),  # type: ignore[arg-type]
            "/person/aliases": lambda: self._set_aliases(conn, f),  # type: ignore[arg-type]
            "/person/alias/add": lambda: self._add_alias(conn, f),  # type: ignore[arg-type]
            "/event/add": lambda: self._add_event(conn, f),  # type: ignore[arg-type]
            "/event/remove": lambda: self._remove_event(conn, f),  # type: ignore[arg-type]
            "/identity/decide": lambda: self._decide_link(conn, f),  # type: ignore[arg-type]
            "/identity/link": lambda: self._link_account(conn, f),  # type: ignore[arg-type]
            "/identity/look": lambda: self._look_for_links(conn),  # type: ignore[arg-type]
            "/redecide": lambda: self._redecide(conn),  # type: ignore[arg-type]
            "/testability/decide": lambda: self._decide_repair(conn, f),  # type: ignore[arg-type]
            "/testability/confirm": lambda: self._confirm_agent_fail(conn, f),  # type: ignore[arg-type]
            "/model/check": lambda: self._check_model(),
            "/audit/start": lambda: self._start_audit(conn, f),  # type: ignore[arg-type]
            "/audit/stop": lambda: self._stop_audit(),
            "/cloud/case": lambda: self._cloud_case(conn, f),  # type: ignore[arg-type]
            "/cloud/key": lambda: self._cloud_key(f),
            "/cloud/key/remove": lambda: self._cloud_key_remove(),
            "/exhibit/add": lambda: self._add_exhibit(conn, f),  # type: ignore[arg-type]
            "/exhibit/remove": lambda: self._remove_exhibit(conn, f),  # type: ignore[arg-type]
            "/exhibit/rematch": lambda: self._rematch(conn, f),  # type: ignore[arg-type]
            "/timeline/settings": lambda: self._timeline_settings(conn, f),  # type: ignore[arg-type]
            "/flag/add": lambda: self._add_flag(conn, f),  # type: ignore[arg-type]
            "/flag/withdraw": lambda: self._withdraw_flag(conn, f),  # type: ignore[arg-type]
            "/activity/report": lambda: self._activity_in_report(conn, f),  # type: ignore[arg-type]
        }
        handler = handlers.get(req.path)
        if handler is None:
            return self._not_found(self._page(), "no such action")
        try:
            self._guard(req.path)
            msg = handler()
            self.flash = (msg, False)
            if req.path == "/claim/add":
                back = pages.link("/claim", id=f.get("id", ""))
            if req.path in ("/case/new", "/case/open"):
                back = "/setup#recovery" if self._recovery_for_open() else self._landing()
            if req.path == "/case/encrypt":
                back = "/setup#recovery"
            if req.path == "/case/lock":
                back = "/cases"
            if req.path == "/exhibit/add" and self._added:
                back = pages.link("/exhibit", id=self._added)
        except (
            ReviewError,
            audit_log.ChainBroken,
            CaseLocked,
            EncryptionError,
            ExhibitError,
            InvariantViolation,
            ValueError,
            *db.IntegrityError,
        ) as err:
            verb = "Not opened" if req.path == "/case/open" else "Not recorded"
            self.flash = (f"{verb}: {err}", True)
            if (
                isinstance(err, audit_log.ChainBroken)
                and self.case is not None
                and req.path not in ("/case/open", "/case/new")  # not the open case's log
            ):
                self._close_broken(self.case)  # e.g. encrypting a case blocked since it opened
                back = "/cases"
        except db.OperationalError as err:  # the audit held the database too long
            self.flash = (f"Not recorded, the case database was busy ({err}). Try again.", True)
        return self._redirect(back)

    def _guard(self, path: str) -> None:
        job = self.jobs.current
        if job is not None and job.running and job.kind in NEEDS_NO_JOB.get(path, ()):
            what = {
                "audit": "the audit",
                "propose": "claim proposal",
                "model_check": "the model check",
            }[job.kind]
            raise ReviewError(f"wait until {what} finishes (or stop it)")
        if path == "/redecide" and self.case is not None:
            conn = connect(self.case.db)
            try:
                if pipeline.view_run(conn) != pipeline.last_run(conn):
                    raise ReviewError(
                        "the latest audit has not finished; resume it before re-running the "
                        "verdicts"
                    )
            finally:
                conn.close()

    def _timeline(self) -> timeline_settings.Settings:
        return timeline_settings.from_case(self._open().settings)

    def _timeline_settings(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        s = timeline_settings.save(
            self._open(), conn, self.actor, f.get("tolerance_min", ""), f.get("gap_hours", "")
        )
        return (
            f"Saved: time tolerance {s.tolerance_min} min, shortest quiet stretch "
            f"{s.gap_hours} h. Findings only; no verdict changes."
        )

    def _activity_in_report(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        include = f.get("include") == "1"
        if not activity.set_in_report(
            conn, self.clock(), self.actor, include, session=self.session
        ):
            return (
                "No change: the report already "
                + ("includes" if include else "leaves out")
                + (" examiner activity.")
            )
        if include:
            return "The report now includes examiner activity, with time on page, for this case."
        return "The report now leaves out examiner activity for this case."

    def _set_expert(self, conn: sqlite3.Connection | None, f: dict[str, str]) -> str:
        before = self.expert
        self.set_expert(f.get("name", ""))
        if self.name_file is not None:
            try:
                self.name_file.parent.mkdir(parents=True, exist_ok=True)
                self.name_file.write_text(json.dumps({"name": self.expert}), encoding="utf-8")
            except OSError:
                pass  # remembered for this launch only
        if before is not None and before != self.expert and conn is not None:
            # A change of name mid-case is on the record: decisions before and after it carry
            # different names, and the log says they came from one screen.
            cases._logged(
                conn,
                self.clock(),
                self.actor,
                "reviewer.rename",
                {"from": f"expert:{before}", "to": self.actor, "session": self.session},
            )
            return (
                f"Reviewing as {self.expert} (was {before}). The change is in the audit log; "
                "decisions from now on carry the new name."
            )
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

    def _decide_repair(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        """The claim page's card: accept or reject one testability proposal."""
        choice = f.get("decision", "")
        if choice not in ("accept", "reject"):
            raise ReviewError("accept or reject the agent's proposal")
        try:
            attempt = int(f.get("attempt", ""))
        except ValueError:
            raise ReviewError("no agent proposal named") from None
        actions.decide_repair(
            conn,
            f.get("claim", ""),
            f.get("run", ""),
            attempt,
            choice == "accept",
            self.actor,
            f.get("reason", ""),
        )
        if choice == "reject":
            return "Recorded: rejected. No later audit uses the agent's proposal."
        return (
            "Recorded: accepted. The next audit tests the claim with these assumptions, if the "
            "agent gives them again for this claim's text; nothing changes until then."
        )

    def _confirm_agent_fail(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        """Rules 0.4.0's step: confirm a failed check on an assumption the testability agent
        proposed, with the expert's reason in the audit log, then re-run the verdicts so the
        claim shows the result."""
        if pipeline.view_run(conn) != pipeline.last_run(conn):
            raise ReviewError(
                "the latest audit has not finished; resume it before confirming a contradiction"
            )
        actions.confirm_agent_fail(
            conn,
            f.get("claim", ""),
            f.get("check", ""),
            self.actor,
            f.get("reason", ""),
            seen=f.get("seen", ""),
        )
        done = "Failed check confirmed"
        try:
            return f"{done}. {self._redecide(conn)}"
        except audit_log.ChainBroken:
            raise  # _post closes the case
        except Exception as err:  # noqa: BLE001 - the confirm is recorded either way
            return f"{done} and recorded. The verdicts were not re-run: {err}."

    def _confirm(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        """Rule 1b's one-click step: decide a contradiction waiting for the expert, with the
        expert's reason in the audit log, then re-run the verdicts so the claim shows the result."""
        status = EvidenceStatus(f.get("status", ""))
        if status not in (EvidenceStatus.ACCEPTED, EvidenceStatus.DISMISSED):
            raise ReviewError("confirm or dismiss the contradiction")
        if pipeline.view_run(conn) != pipeline.last_run(conn):
            raise ReviewError(
                "the latest audit has not finished; resume it before confirming a contradiction"
            )
        eid = f.get("id", "")
        # A page left open across a later audit may post an item that is no longer the one
        # waiting on this claim (Codex on #98): only an item the latest run shows as waiting.
        row = conn.execute(
            "SELECT a.claim_id FROM evidence_items e JOIN assumptions a ON a.id = e.assumption_id"
            " WHERE e.id = ?",
            (eid,),
        ).fetchone()
        st = claim_state(conn, row[0]) if row else None
        item = next((x for x in st.evidence if x.id == eid), None) if st else None
        if st is None or item is None or not (st.contradiction_found and st.to_confirm(item)):
            raise ReviewError(
                "this contradiction is not waiting for you in the latest audit; reload the claim"
            )
        actions.decide_evidence(conn, eid, status, self.actor, f.get("reason", ""))
        done = "Contradiction confirmed" if status == EvidenceStatus.ACCEPTED else "Dismissed"
        try:
            return f"{done}. {self._redecide(conn)}"
        except audit_log.ChainBroken:
            raise  # _post closes the case
        except Exception as err:  # noqa: BLE001 - the decision is recorded either way (Codex on #98)
            return f"{done} and recorded. The verdicts were not re-run: {err}."

    def _verdict(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        claim = f.get("claim", "")
        if f.get("action") == "confirm":
            actions.confirm_verdict(conn, claim, self.actor, f.get("note", ""))
            return f"Verdict on {_named(conn, claim)} confirmed."
        verdict = Verdict(f.get("verdict", ""))
        actions.override_verdict(conn, claim, verdict, self.actor, f.get("note", ""))
        return f"Verdict on {_named(conn, claim)} overridden: {verdict.value}."

    def _acknowledge(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        """The expert has seen that an item's rationale is withheld (core/review/withheld.py)."""
        w, new = withheld.acknowledge(conn, f.get("id", ""), self.actor)
        if not new:
            return f"Already acknowledged, by {w.acknowledged_by}."
        return "Acknowledged. The audit log records the item, the word and the rationale's SHA-256."

    def _edit_claim(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        status = ClaimStatus(f.get("status", ""))
        text = f.get("text") if status == ClaimStatus.EDITED else None
        if text is not None:
            text = text.strip()
            if not text:
                raise ReviewError("the claim text is empty")
        actions.set_claim_status(conn, f.get("claim", ""), status, self.actor, text)
        return f"Claim {_named(conn, f.get('claim', ''))} is {status.value}."

    def _accept_all(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        """Accept, as written, the proposed claims the page listed (only those: a claim
        proposed after the page was drawn was not read, so it waits)."""
        shown = [c for c in f.get("claims", "").split(",") if c]
        still = {
            r[0]
            for r in conn.execute("SELECT id FROM claims WHERE status = 'proposed'")
            if r[0] in shown
        }
        if not still:
            raise ReviewError("no proposed claim from that list is still waiting")
        for cid in shown:
            if cid in still:
                actions.set_claim_status(conn, cid, ClaimStatus.ACCEPTED, self.actor)
        left = conn.execute("SELECT COUNT(*) FROM claims WHERE status = 'proposed'").fetchone()[0]
        return f"Accepted {len(still)} claim{'s' if len(still) != 1 else ''} as written." + (
            f" {left} more proposed since that page was drawn; decide on them below."
            if left
            else ""
        )

    def _add_claim(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        # What the expert typed is kept for the form if anything below refuses it.
        self._claim_draft = {k: f.get(k, "") for k in ("paragraph", "text", "id", "type")}
        cid = f.get("id", "").strip()
        text = f.get("text", "").strip()
        if not cid or not text:
            raise ReviewError("a claim needs an id and its text")
        para = f.get("paragraph", "")
        if conn.execute("SELECT 1 FROM govdoc_paragraphs WHERE id = ?", (para,)).fetchone() is None:
            raise ReviewError("pick the paragraph the claim comes from")
        if conn.execute("SELECT 1 FROM claims WHERE id = ?", (cid,)).fetchone() is not None:
            raise ReviewError(
                f"the case already has a claim called {cid} (removed claims keep their id). "
                "Give this one another id; your text is still in the form"
            )
        actions.add_claim(conn, cid, para, text, ClaimType(f.get("type", "")), self.actor)
        self._claim_draft = None
        return f"Added {_named(conn, cid)}. It needs a full audit before it has a verdict."

    def _name_device(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        names = [n for n in f.get("names", "").split(",") if n.strip()]
        kept = actions.name_device(conn, f.get("device", ""), names, self.actor)
        if not kept:
            return "Names cleared." + _applies(conn, " Run the audit again to apply it.")
        return f"Saved {', '.join(kept)}." + _applies(
            conn, " Run the audit again so claims that name it are tested."
        )

    def _stipulate(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        actions.stipulate_device_owner(conn, f.get("device", ""), f.get("person", ""), self.actor)
        propose_links(conn)  # a renamed owner may carry other names now
        return "Stipulation recorded." + _applies(conn, " Re-run the verdicts to apply it.")

    # -- identities

    def _add_person(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        pid = actions.add_person(conn, f.get("name", ""), self.actor)
        found = propose_links(conn)
        mine = [lid for lid in found.added if lid.endswith(f"|{pid}")]
        return (
            f"Added {f.get('name', '').strip()}. Mabillon proposed {len(mine)} link(s) to decide. "
            "It applies on the next audit run."
        )

    def _remove_person(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        actions.remove_person(conn, f.get("id", ""), self.actor)
        return "Person removed. It applies on the next audit run."

    def _set_aliases(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        names = [n for n in f.get("aliases", "").split(",") if n.strip()]
        kept = actions.set_aliases(conn, f.get("id", ""), names, self.actor)
        if not kept:
            return "Other names cleared." + _applies(conn, " It applies on the next audit run.")
        return f"Saved {', '.join(kept)}." + _applies(
            conn, " Run the audit again so claims that use them are tested."
        )

    def _add_alias(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        from core.identity import aliases

        pid = f.get("id", "")
        have = [a.alias for a in aliases.stored(conn) if a.person_id == pid]
        kept = actions.set_aliases(conn, pid, [*have, f.get("alias", "")], self.actor)
        return f"Saved {', '.join(kept)}." + _applies(
            conn, " Run the audit again so claims that use them are tested."
        )

    def _add_event(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        first = f.get("first_day", "")
        name = actions.add_event(
            conn,
            f.get("name", ""),
            first,
            f.get("last_day", "") or first,
            f.get("paragraph", ""),
            f.get("defined_as", ""),
            self.actor,
        )
        return f"Saved the event {name}." + _applies(
            conn, " Run the audit again so claims dated by it are tested."
        )

    def _remove_event(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        actions.remove_event(conn, f.get("name", ""), self.actor)
        return "Event removed. It applies on the next audit run."

    def _decide_link(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        status = IdentityLinkStatus(f.get("status", ""))
        actions.decide_identity_link(conn, f.get("id", ""), status, self.actor, f.get("note", ""))
        return (
            f"Link {status.value}. It reaches the checks on the next audit run; re-running the "
            "verdicts alone does not apply it."
        )

    def _link_account(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        actions.link_account(
            conn, f.get("account", ""), f.get("person", ""), self.actor, f.get("note", "")
        )
        return "Link recorded and confirmed. It reaches the checks on the next audit run."

    def _look_for_links(self, conn: sqlite3.Connection) -> str:
        found = propose_links(conn)
        return (
            f"Looked again: {len(found.added)} new proposal(s), {len(found.removed)} withdrawn "
            "because the names no longer match."
        )

    def _add_flag(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        flags.add_flag(
            conn,
            f.get("claim", ""),
            f.get("kind", ""),
            self.actor,
            evidence_id=f.get("evidence") or None,
            should_be=f.get("should_be", flags.NOT_SURE),
            record=f.get("record", ""),
            note=f.get("note", ""),
            seen_run=f.get("seen_run") if "seen_run" in f else None,
        )
        return "Flag saved for your error log. It changes no verdict and nothing is sent."

    def _withdraw_flag(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        flags.withdraw_flag(conn, f.get("flag", ""), self.actor)
        return "Flag withdrawn. It stays in the audit log and no longer counts."

    def _withdraw(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        actions.withdraw_stipulation(conn, f.get("id", ""), self.actor)
        return "Stipulation withdrawn." + _applies(conn, " Re-run the verdicts to apply it.")

    # -- cases

    def _cases(self) -> Response:
        page = self._page()
        if self.home is None:
            single = self.single
            locked = single is not None and protect.is_locked(single)
            blocked = None
            if single is not None and not locked and self.case is None:
                blocked = _chain_problem(single)
            return self._html(
                pages.cases_page(page, None, [], str(single.db if single else ""), locked, blocked)
            )
        rows = []
        for c in cases.list_cases(self.home):
            try:
                lock = _lock_state(c)
                if lock in ("locked", "partial-locked"):
                    state = "locked"
                else:
                    conn = connect(c.db)
                    try:
                        try:
                            audit_log.require_intact(conn, audit_log.anchors_path(c.db))
                            state = _stage(c, conn)
                        except audit_log.ChainBroken as err:
                            state = f"Review blocked: {err.problem}"
                    finally:
                        conn.close()
            except (*db.Error, InvariantViolation, CaseLocked, EncryptionError) as err:
                lock, state = "plain", f"cannot read: {err}"
            rows.append((c.folder.name, c.name, state, lock))
        return self._html(pages.cases_page(page, self.home, rows, None))

    def _new_case(self, f: dict[str, str]) -> str:
        if self.home is None:
            raise ReviewError("this screen was started on one case database")
        passphrase = None
        if f.get("encrypt") == "1":
            passphrase = f.get("passphrase", "")
            if passphrase != f.get("passphrase2", ""):
                raise ReviewError("the two passphrases do not match")
        case = cases.create_case(self.home, f.get("name", ""), self.actor, passphrase=passphrase)
        try:
            self.open_case(case)
        except audit_log.ChainBroken as err:  # e.g. its anchor file cannot be written
            cases.recovery_key_for(case)  # drop the key from memory with the case
            if protect.state(case) != "plain":
                protect.lock(case)
            shutil.rmtree(case.folder, ignore_errors=True)  # made just now; nothing else in it
            raise ReviewError(f"the case was not made, because {err.problem}") from err
        key = cases.recovery_key_for(case)
        if key is not None:
            self.recovery = (case.db, key)
            return (
                f"Made the encrypted case {case.name}. Write down its recovery key, shown at the "
                "top of this page."
            )
        return f"Made the case {case.name}. Import its files below."

    def _next_step(self, conn: sqlite3.Connection) -> str | None:
        """Before the first audit, the setup step that comes next, in its own words."""
        if self.case is None or pipeline.view_run(conn) is not None:
            return None
        todo = [r for r in cases.readiness(self.case, conn) if not r.ok]
        return todo[0].text if todo else "start the audit."

    def _landing(self) -> str:
        """Where opening a case lands: an audited case on its Case page, with what waits on the
        expert; a case still being set up on Set up and run."""
        if self.case is None:
            return "/setup"
        conn = connect(self.case.db)
        try:
            return "/" if pipeline.view_run(conn) is not None else "/setup"
        finally:
            conn.close()

    def _open_case(self, f: dict[str, str]) -> str:
        if self.home is None:
            if self.single is None:
                raise ReviewError("this screen was started on one case database")
            target = self.single
        else:
            slug = f.get("case", "")
            match = [c for c in cases.list_cases(self.home) if c.folder.name == slug]
            if not match:
                raise ReviewError("no such case")
            target = match[0]
        unlocked = False
        if protect.is_locked(target):
            try:
                encryption.unlock(target.db, f.get("passphrase", ""))
            except encryption.WrongSecret as err:
                raise ReviewError(str(err)) from err
            unlocked = True
        try:
            self.open_case(target)
        except audit_log.ChainBroken:
            if unlocked:
                protect.lock(target)  # not opened, so its key does not stay in memory
            raise
        return f"Unlocked and opened {target.name}." if unlocked else f"Opened {target.name}."

    # -- encryption

    def _recovery_for_open(self) -> str | None:
        if self.recovery is None or self.case is None or self.recovery[0] != self.case.db:
            return None
        return self.recovery[1]

    def _encrypt(self, f: dict[str, str]) -> str:
        case = self._open()
        partial = protect.state(case) == "partial"
        done = protect.encrypt_case(
            case,
            f.get("passphrase", ""),
            self.actor,
            again=None if partial else f.get("passphrase2", ""),
        )
        self.recovery = (case.db, done.recovery_key)
        return (
            f"Encrypted {case.name}: the database and {done.files} copied file(s). Write down "
            "its recovery key, shown at the top of this page."
        )

    def _lock(self) -> str:
        case = self._open()
        if protect.state(case) == "plain":
            raise ReviewError("this case is not encrypted, so there is nothing to lock")
        if self._recovery_for_open() is not None:
            raise ReviewError(
                'write down the recovery key at the top of this page and press "I have written '
                'it down" first. Locking now would lose the only copy of it'
            )
        protect.lock(case)
        self.case = None
        self.recovery = None
        self.last_check = None
        return f"Locked {case.name}. Its passphrase or recovery key opens it again."

    def _change_passphrase(self, f: dict[str, str]) -> str:
        protect.change_passphrase(
            self._open(), f.get("current", ""), f.get("new", ""), f.get("new2", ""), self.actor
        )
        return "Passphrase changed. The recovery key is the same as before."

    def _recovery_done(self) -> str:
        if self.case is not None and self.recovery is not None and self.recovery[0] == self.case.db:
            protect.recovery_pending(self.case, False)
        self.recovery = None
        return "Recovery key hidden. Mabillon keeps no copy of it."

    def _remove_file(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        from core.casework.remove import remove_file

        name = remove_file(self._open(), conn, f.get("source", ""), self.actor, f.get("reason", ""))
        return f"Removed {name} from the case. Your original file is not touched."

    def _new_recovery(self, f: dict[str, str]) -> str:
        case = self._open()
        key = protect.new_recovery_key(case, f.get("passphrase", ""), self.actor)
        self.recovery = (case.db, key)
        return (
            "Made a new recovery key. Write it down now: it is shown at the top of this page, "
            "and the old one no longer opens the case."
        )

    # -- set up and run

    def _setup(self, conn: sqlite3.Connection) -> str:
        case = self._open()
        page = self._page()
        job = self._job()
        running = job.kind if job is not None and job.running else None
        order = cases.claim_order(case, conn)
        check = self.last_check
        if job is not None and job.check is not None:
            check = job.check
        if check is not None:
            model_lines = check.lines
            when = _when(check.checked_at_utc)
            note = (
                f"The model passed its check {when}."
                if check.ok
                else f"The model failed its check {when}. The audit cannot run until it passes."
            )
        elif self.model_check is None:
            model_lines, note = None, "The model check is off for this screen."
        else:
            model_lines, note = (
                None,
                "Not checked yet. The audit checks the model before it starts, or check it now "
                "(the first check reads the whole 9 GB file, a minute or two).",
            )
        if job is not None and job.kind == "model_check" and job.running and job.hashed:
            done, total = job.hashed
            note = f"Checking: SHA-256 of the model file, {done * 100 // max(total, 1)}%."
        spc, source = jobs.seconds_per_call()
        cloud_spc = jobs.CLOUD_SECONDS_PER_CALL if self._cloud_choice(conn).use else None
        n = len(order)
        if cloud_spc is None:
            calls = f"about {jobs.CALLS_PER_CLAIM} model calls per claim at {spc:.0f} s per call"
        else:
            calls = (
                f"per claim, about {jobs.CALLS_PER_CLAIM - jobs.LOCAL_CALLS_PER_CLAIM} cloud calls"
                f" at {cloud_spc:.0f} s and {jobs.LOCAL_CALLS_PER_CLAIM} local call at {spc:.0f} s"
            )
        estimate = (
            f"Rough estimate for {n} claims: "
            f"{jobs.duration(jobs.estimate_seconds(n, spc, cloud_spc))} ({calls}, {source})."
            if n
            else ""
        )
        attempt = pipeline.latest_attempt(conn)
        resumable = None
        if attempt is not None and attempt["status"] != "running" and running != "audit":
            resumable = (
                f"The last audit stopped after {len(attempt['manifest'])} of "
                f"{len(attempt['claim_order'] or ())} claims ({attempt['note'] or 'no reason'})."
                " Resume it: finished claims reuse their stored model outputs."
            )
        # A finished propose or model check reports once, even over the "updates itself" note
        # from starting it (a fast failure ends before the page that started it is shown).
        if (
            job is not None
            and not job.running
            and job.kind in ("propose", "model_check")
            and self._reported is not job
        ):
            if page.flash is None or page.flash[0].endswith(UPDATES):
                page.flash = (job.message, job.state != "done")
            self._reported = job
        return pages.setup_page(
            conn,
            page,
            inputs_folder=str(case.inputs),
            order=order,
            ready=cases.readiness(case, conn),
            counts=cases.source_counts(conn),
            model_lines=model_lines,
            model_note=note,
            estimate=estimate,
            job_kind=running,
            resumable=resumable,
            protection=protect.state(case),
            recovery_key=self._recovery_for_open(),
            recovery_unconfirmed=protect.recovery_unconfirmed(case),
            cloud=self._cloud_choice(conn),
            cloud_case=cloud_policy.case_cloud(conn),
            cloud_key=self._cloud_key_state(),
            cloud_key_from=self._cloud_key_source(),
            audited=_audited(conn),
            model_ok=None
            if check is None or (job is not None and job.running and job.kind == "model_check")
            else check.ok,
        )

    def _move_claim(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        delta = -1 if f.get("delta") == "-1" else 1
        order = cases.move_claim(self._open(), conn, f.get("claim", ""), delta)
        cid = f.get("claim", "")
        return f"{_named(conn, cid)} now runs at position {order.index(cid) + 1}."

    def _propose(self) -> str:
        _ = self.actor  # a named expert starts model work on the case
        self.jobs.start(
            jobs.Job("propose", self._open().db),
            jobs.propose_job(extractor_for=self.extractor_for),
        )
        return "The local model is proposing claims in the background. " + UPDATES

    def _check_model(self) -> str:
        if self.model_check is None:
            raise ReviewError("the model check is off for this screen")
        check = self.model_check

        def run(job: jobs.Job) -> None:
            jobs.model_check_job(check)(job)
            self.last_check = job.check

        self.jobs.start(jobs.Job("model_check", self._open().db), run)
        return "Checking the model in the background. " + UPDATES

    # -- cloud

    def _cloud_load(self) -> cloud_llm.CloudConfig:
        case_db = self.case.db if self.case is not None else None
        return cloud_llm.load_config(self.cloud_config, case_db=case_db)

    def _cloud_choice(self, conn: sqlite3.Connection) -> cloud_policy.CloudChoice:
        return cloud_policy.choose(conn, self._cloud_load)

    def _case_uses_cloud(self) -> bool:
        """For the header pill: does the open case send stance questions to the cloud?"""
        if self.case is None:
            return False
        job = self._job("audit")
        if job is not None and job.running and job.cloud:
            return True  # the running audit keeps the choice it started with
        try:
            conn = connect(self.case.db)
        except (*db.Error, CaseLocked, EncryptionError):
            return False
        try:
            return self._cloud_choice(conn).use
        finally:
            conn.close()

    def _cloud_key_state(self) -> str | None:
        """None when a key is set up; otherwise why not, in a few words."""
        try:
            self._cloud_load()
        except cloud_llm.CloudConfigError as err:
            return str(err)
        return None

    def _cloud_key_ready(self) -> bool:
        """For the bug report: a broken or unreadable cloud setup reads as no key."""
        try:
            return self._cloud_key_state() is None
        except OSError:
            return False

    def _cloud_case(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        _ = self._open()
        entry = cloud_policy.set_cloud(
            conn,
            self.actor,
            allowed=f.get("allowed") == "1",
            csam=f.get("csam") == "1",
        )
        if entry["csam"]:
            return "Saved: this case may contain CSAM, so it runs on the local model only."
        if entry["allowed"]:
            return (
                "Saved: this case may use cloud AI. If the cloud model stops answering, the audit"
                " pauses."
            )
        return "Saved: this case runs on the local model only."

    def _cloud_key_remove(self) -> str:
        _ = self.actor
        case_db = self.case.db if self.case is not None else None
        where = cloud_llm.remove_key(self.cloud_config, case_db=case_db)
        if where == "case":
            return "Removed the Anthropic key saved in this case."
        if where == "file":
            return "Removed the Anthropic key saved on this computer."
        raise ReviewError("no saved Anthropic key to remove")

    def _cloud_key_source(self) -> str | None:
        case_db = self.case.db if self.case is not None else None
        try:
            return cloud_llm.key_source(self.cloud_config, case_db=case_db)
        except OSError:
            return None

    def _cloud_key(self, f: dict[str, str]) -> str:
        _ = self.actor  # a named expert sets the key
        key = f.get("api_key", "").strip()
        if not key.startswith("sk-ant-"):
            raise ReviewError("that does not look like an Anthropic API key (it starts sk-ant-)")
        if len(key) < 20 or any(c.isspace() for c in key):
            raise ReviewError("that key is too short or has a space in it: paste the whole key")
        case_db = self.case.db if self.case is not None else None
        try:
            where = cloud_llm.save_key(key, self.cloud_config, case_db=case_db)
        except cloud_llm.CloudConfigError as err:
            raise ReviewError(str(err)) from err
        if case_db is not None and where == encryption.secret_path(
            Path(case_db), cloud_llm.CASE_SECRET
        ):
            return (
                "Saved your Anthropic key in this case, encrypted with the case's key: it can be"
                " read only while the case is unlocked."
            )
        return "Saved your Anthropic key on this computer, readable by your user account only."

    def _start_audit(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        case = self._open()
        actor = self.actor
        ready = cases.readiness(case, conn)
        todo = [
            r for r in ready if not r.ok and not (r.acknowledge and f.get(r.acknowledge) == "1")
        ]
        if todo:
            raise ReviewError("not ready: " + " ".join(r.text for r in todo))
        order = cases.claim_order(case, conn)
        spc, _ = jobs.seconds_per_call()
        job = jobs.Job("audit", case.db, total=len(order))
        choice = self._cloud_choice(conn)
        job.cloud = choice.use
        cloud_spc = jobs.CLOUD_SECONDS_PER_CALL if choice.use else None
        job.estimate_seconds = jobs.estimate_seconds(len(order), spc, cloud_spc)
        check = self.model_check
        components_for = self.components_for
        if components_for is _real_components:
            components_for = functools.partial(_real_components, cloud=choice)

        def model_check_once(progress: object = None) -> ModelCheck:
            result = check(progress=progress)  # type: ignore[misc]
            self.last_check = result
            return result

        self.jobs.start(
            job,
            jobs.audit_job(
                actor=actor,
                order=order,
                components_for=components_for,
                model_check=model_check_once if check is not None else None,
                cloud_opt_in=choice.use,
                ai_review=f.get("ai_review") == "1",
                label_all=f.get("label_all") == "1",
                challenge=f.get("no_challenge") != "1",
            ),
        )
        where = (
            f" Stance labels come from the cloud model ({choice.config.model}); if it stops "
            "answering, the audit pauses. The local model does the other steps."
            if choice.use and choice.config is not None
            else ""
        )
        attempt = pipeline.latest_attempt(conn)
        reused = len(attempt["manifest"]) if attempt is not None else 0
        what = f"{len(order)} claims"
        if reused:
            # A resume reuses finished claims' stored outputs; the estimate is for the rest.
            left = max(len(order) - reused, 0)
            job.estimate_seconds = jobs.estimate_seconds(left, spc, cloud_spc)
            what = f"the {left} claims left ({reused} already finished are reused)"
        first = (
            f"Checking the model first; if it passes, the audit runs on {what}"
            if check is not None
            else f"The audit started on {what}"
        )
        return (
            f"{first}, {jobs.duration(job.estimate_seconds)} by a rough estimate.{where} Each "
            "claim appears for review as soon as it is labeled."
        )

    def _stop_audit(self) -> str:
        job = self._job("audit")
        if job is None or not job.running:
            raise ReviewError("no audit is running")
        job.stop.set()
        return "Stopping after the claim being labeled now. Finished claims are kept."

    def _run(self, conn: sqlite3.Connection) -> str:
        page = self._page()
        job = self._job("audit")
        run = None
        for r in conn.execute(
            "SELECT id, started_at_utc, status, note, config_json FROM pipeline_runs"
            " ORDER BY started_at_utc DESC, id DESC"
        ):
            if '"mode":"rules_only"' not in r[4]:
                run = {"id": r[0], "started_at_utc": r[1], "status": r[2], "note": r[3]}
                break
        rows: list[tuple] = []
        if run is not None:
            rows = list(
                conn.execute(
                    "SELECT position, claim_id, state, candidates_total, candidates_labeled,"
                    " model_calls FROM run_claims WHERE pipeline_run_id = ? ORDER BY position",
                    (run["id"],),
                )
            )
        left = ""
        if job is not None and job.running:
            spc = job.seconds_per_call() or jobs.seconds_per_call()[0]
            remaining = max(job.total - job.done, 0)
            elapsed = (datetime.now(UTC) - job.started_at).total_seconds()
            togo = jobs.duration(jobs.estimate_seconds(remaining, spc))
            left = (
                f"Running for {jobs.duration(elapsed)}; {togo} left by a rough estimate "
                f"({spc:.0f} s per model call"
                + (", measured in this run)." if job.seconds_per_call() else ").")
            )
        return pages.run_page(conn, page, run=run, rows=rows, job=job, left=left)

    # -- upload

    def handle_upload(self, req: Request, stream: BinaryIO, length: int | None) -> Response:
        """POST /case/import as multipart/form-data, streamed into the case's inputs folder."""
        if req.headers.get("host") not in self.allowed_hosts():
            return self._plain(400, "This screen only answers requests from this computer.")
        if req.path != "/case/import":
            return self._plain(404, "no such upload")
        if not self._origin_ok(req):
            return self._plain(403, "This form did not come from this review screen.")
        if length is None:
            return self._plain(411, "the upload has no length")
        if length > MAX_UPLOAD:
            return self._plain(413, "the file is larger than this screen accepts")
        if self.case is None:
            self.flash = ("Open or make a case first.", True)
            return self._redirect("/cases")
        case = self.case
        try:  # uploads skip handle(), so they check the log here, before a byte is written
            conn = connect(case.db)
            try:
                audit_log.require_intact(conn, audit_log.anchors_path(case.db))
            finally:
                conn.close()
        except (audit_log.ChainBroken, CaseLocked) as err:
            if isinstance(err, audit_log.ChainBroken):  # stop a job first, then drain
                self._close_broken(case)
            else:
                self.case = None
            _drain(stream, length)
            self.flash = (f"Not imported: {err}", True)
            return self._redirect("/cases")
        counted = _Counting(stream)
        written: list[Path] = []

        def open_file() -> Path:
            written.append(cases.upload_path(case))
            return written[-1]

        def before_file(fields: dict[str, str]) -> None:
            if not hmac.compare_digest(fields.get("token", ""), self.token):
                raise _Refused
            stale = self._stale_case(fields)
            if stale is not None:
                raise ReviewError(stale.removeprefix("Nothing was saved: "))
            self._last_view = None  # an accepted post: the page it returns to is a new view
            self._guard("/case/import")
            _ = self.actor

        try:
            wrap = cases.input_writer(case)
        except CaseLocked as err:
            _drain(stream, length)
            self.case = None
            self.flash = (f"Not imported: {err}", True)
            return self._redirect("/cases")
        try:
            up = upload.parse(
                counted,
                length,
                req.headers.get("content-type", ""),
                open_file,
                before_file,
                wrap=wrap,
            )
        except _Refused:
            for p in written:
                cases.discard(p)
            _drain(stream, length - counted.read_bytes)  # else the browser shows a reset
            return self._stale_page()
        except (upload.UploadError, ReviewError, OSError) as err:
            for p in written:
                cases.discard(p)
            _drain(stream, length - counted.read_bytes)
            self.flash = (f"Not imported: {err}", True)
            return self._redirect("/setup#files")
        _drain(stream, length - counted.read_bytes)
        conn = connect(case.db)
        conn.execute("PRAGMA busy_timeout = 10000")
        try:
            got = cases.import_upload(
                case,
                conn,
                up.path,  # type: ignore[arg-type]
                up.sha256,  # type: ignore[arg-type]
                up.file_name or "",
                up.fields.get("kind", ""),
                self.actor,
                date_order=up.fields.get("date_order") or None,
            )
            self.flash = (
                f"Imported {got.file_name} as {got.source_id}: {got.summary}. "
                f"SHA-256 {got.sha256}.",
                False,
            )
        except Exception as err:  # noqa: BLE001 - any parser failure: nothing stored, say why
            self.flash = (f"Not imported: {err}", True)
        finally:
            conn.close()
        return self._redirect("/setup#files")

    # -- Context Restore

    def _add_exhibit(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        self._added = None
        ex = add_exhibit(
            conn,
            f.get("label", ""),
            f.get("text", "").replace("\r\n", "\n"),
            ExcerptSplit(f.get("split", "line")),
            self.actor,
            f.get("paragraph") or None,
        )
        self._added = ex.id
        return f"Added {ex.label} and searched the extraction for each quoted message."

    def _remove_exhibit(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        remove_exhibit(conn, f.get("id", ""), self.actor)
        return "Exhibit removed."

    def _rematch(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        n = match_exhibits(conn, [f["id"]] if f.get("id") else None)
        return f"Searched {n} exhibit(s) again against the messages imported now."

    def _letter_text(self, conn: sqlite3.Connection, page: pages.Page) -> Response:
        text = request_letter(conn)
        if text is None:
            return self._not_found(page, "no request is needed for this case")
        try:
            check_report_text(text)
        except InvariantViolation as err:
            return self._plain(500, f"letter withheld: {err}")
        return Response(
            200,
            text.encode("utf-8"),
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Disposition", 'attachment; filename="mabillon-request-draft.txt"'),
                *self._security_headers(),
            ],
        )

    def _redecide(self, conn: sqlite3.Connection) -> str:
        result = redecide(conn, self.actor)
        msg = f"Verdicts re-run with the rules ({len(result.decisions)} claims)."
        if result.carried:
            n = len(result.carried)
            msg += f" Your verdict decision{'s' if n > 1 else ''} on {n} unchanged claim" + (
                "s carry over." if n > 1 else " carries over."
            )
        if result.lapsed:
            msg += (
                " The verdict changed on "
                + ", ".join(claim_names(conn, result.lapsed))
                + ", so your earlier confirmation or override no longer applies: confirm "
                "again."
            )
        if result.skipped:
            msg += " Needs a full audit: " + ", ".join(claim_names(conn, result.skipped)) + "."
        return msg

    # -- help and the bug report

    def _bug_report(self) -> str:
        """The bug report text for this screen, checked clean (raises NotClean)."""
        case = self.case if self.case is not None and not protect.is_locked(self.case) else None
        conn = None
        if case is not None and case.db.exists():  # never create an empty database here
            try:
                conn = connect(case.db)
                conn.execute("PRAGMA busy_timeout = 10000")
            except (*db.Error, CaseLocked, EncryptionError):
                conn = None
        try:
            job = self._job() if case is not None else None  # only the open case's job
            count = None
            if self.home is not None:
                try:
                    count = len(cases.list_cases(self.home))
                except OSError:
                    count = None
            report = bug_report.build(
                case=case,
                conn=conn,
                job=job,
                last_check=self.last_check,
                cloud_key_ready=self._cloud_key_ready(),
                many_cases=self.home is not None,
                case_count=count,
            )
            return bug_report.render(report, bug_report.sensitive_values(case, conn))
        finally:
            if conn is not None:
                conn.close()

    def _help(self, path: str) -> Response:
        previewed = getattr(self, "_previewed_report", None)
        if path == "/help/bug-report.json" and previewed and previewed[0] is self.case:
            # save exactly the text the Help page showed, not a newer build of it
            text, withheld = previewed[1], None
        else:
            try:
                text, withheld = self._bug_report(), None
            except bug_report.NotClean as err:
                text, withheld = None, str(err)
        if path == "/help/bug-report.json":
            if text is None:
                return self._plain(500, f"Bug report withheld: {withheld}. Nothing was saved.")
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            return Response(
                200,
                text.encode("utf-8"),
                [
                    ("Content-Type", "application/json; charset=utf-8"),
                    (
                        "Content-Disposition",
                        f'attachment; filename="mabillon-bug-report-{stamp}.json"',
                    ),
                    *self._security_headers(),
                ],
            )
        self._previewed_report = (self.case, text) if text is not None else None
        page = self._page()
        return self._html(help_pages.help_page(page, text, withheld, self.case is not None))

    # -- responses

    @staticmethod
    def _security_headers() -> list[tuple[str, str]]:
        return [
            ("Content-Security-Policy", CSP),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            # same-origin, not no-referrer: under no-referrer a browser sends "Origin: null"
            # with this screen's own forms, and the Origin check refuses every one of them.
            ("Referrer-Policy", "same-origin"),
            ("Cache-Control", "no-store"),
        ]

    def _html(self, body: str, status: int = 200) -> Response:
        try:
            # A textarea holds cited claim text for the expert to edit; it cannot carry the
            # cited-text span, so its contents are left out of the check like any cited span.
            check_report_text(TEXTAREA.sub("<textarea></textarea>", body))
        except InvariantViolation as err:
            return self._plain(500, f"page withheld: {err}")
        return Response(
            status,
            body.encode("utf-8"),
            [("Content-Type", "text/html; charset=utf-8"), *self._security_headers()],
        )

    def _font(self, name: str) -> Response:
        """One of the vendored fonts, by exact file name; nothing else is served from disk."""
        if name not in theme.FONT_FILES:
            return self._plain(404, "no such file")
        headers = [h for h in self._security_headers() if h[0] != "Cache-Control"]
        return Response(
            200,
            (theme.FONT_DIR / name).read_bytes(),
            [("Content-Type", "font/woff2"), ("Cache-Control", "max-age=86400"), *headers],
        )

    def _redirect(self, location: str) -> Response:
        return Response(303, b"", [("Location", location), *self._security_headers()])

    def _not_found(self, page: pages.Page, message: str) -> Response:
        return self._html(pages.error_page(page, 404, message), 404)

    def _plain(self, status: int, message: str) -> Response:
        return Response(
            status,
            message.encode("utf-8"),
            [("Content-Type", "text/plain; charset=utf-8"), *self._security_headers()],
        )


def _chain_problem(case: cases.Case) -> str | None:
    """Why this (unlocked) case cannot be opened for review, or None when its chain verifies."""
    try:
        conn = connect(case.db)
    except (*db.Error, CaseLocked) as err:
        return f"cannot read: {err}"
    try:
        audit_log.require_intact(conn, audit_log.anchors_path(case.db))
    except (audit_log.ChainBroken, *db.Error) as err:
        return str(err)
    finally:
        conn.close()
    return None


UPDATES = "This page updates itself."


def _named(conn: sqlite3.Connection, claim_id: str) -> str:
    """A claim as messages name it ("¶6.2", as on screen), not by its internal id."""
    return (claim_names(conn, [claim_id]) or [claim_id])[0]


def _when(iso_utc: str) -> str:
    """A check's time in words on this computer's clock: "today at 14:05", "on 3 Nov at 09:12"."""
    try:
        at = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return f"at {iso_utc}"
    now = datetime.now(at.tzinfo)
    clock = at.strftime("%H:%M")
    if at.date() == now.date():
        return f"today at {clock}"
    return f"on {at.day} {at.strftime('%b')} at {clock}"


def _audited(conn: sqlite3.Connection) -> str | None:
    """The date of the last finished audit, or None."""
    run = pipeline.last_run(conn)
    if run is None or run.get("partial") or run.get("status") not in (None, "completed"):
        return None
    return cases.audited_on(conn, run)


def _applies(conn: sqlite3.Connection, after_a_run: str) -> str:
    """The second half of a setup change's message: before any audit it simply applies when
    the audit runs; after one, what to run again."""
    if conn.execute("SELECT 1 FROM pipeline_runs LIMIT 1").fetchone() is None:
        return " It applies when you run the audit."
    return after_a_run


def _report_file_name(case_name: str, made: datetime) -> str:
    """A saved report's file name, so two cases' reports never share one:
    mabillon-report-us-v-alvarez-2026-11-05.html (letters, digits and dashes only)."""
    slug = re.sub(r"[^a-z0-9]+", "-", case_name.lower()).strip("-")[:60].strip("-") or "case"
    return f"mabillon-report-{slug}-{made.strftime('%Y-%m-%d')}.html"


def _stage(case: cases.Case, conn: sqlite3.Connection) -> str:
    """The Cases list's line for a case: its stage, what waits on the expert, what is next."""
    if pipeline.view_run(conn) is None:
        return cases.stage_line(case, conn)
    states = claim_states_now(conn)
    waiting = sum(1 for st in states if pages.needs_you(st))
    stale = any(st.decision is not None and st.stale for st in states)
    return cases.stage_line(case, conn, needs_you=waiting, stale=stale)


def _case_key(case: cases.Case) -> str:
    """Names a case in its forms: its folder in a cases folder, else its database file."""
    return case.folder.name if case.db.name == cases.DB_NAME else case.db.name


def _lock_state(case: cases.Case) -> str:
    """plain, locked, open, or for an encryption that did not finish (part of the case still
    readable on disk) partial-locked or partial."""
    st = protect.state(case)
    if st == "plain":
        return "plain"
    locked = protect.is_locked(case)
    if st == "partial":
        return "partial-locked" if locked else "partial"
    return "locked" if locked else "open"


def _drain(stream: BinaryIO, n: int) -> None:
    """Read and drop the rest of a refused upload so the browser sees the answer, not a reset."""
    while n > 0:
        chunk = stream.read(min(n, 1 << 20))
        if not chunk:
            return
        n -= len(chunk)

"""The expert review screen's request handling, independent of any socket.

App.handle(Request) -> Response does everything: it checks the request came from this
machine's own pages, reads or changes the case database, and renders a page. App.handle_upload
does the same for a file upload, streamed to disk (ui/upload.py). ui/server.py wraps both in the
standard library's HTTP server bound to 127.0.0.1; tests call them directly.

Starting a case. Started on a cases folder (`baker serve`), the screen lists the cases and makes
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
import re
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from core import pipeline
from core.audit.invariants import InvariantViolation, check_report_text
from core.casework import cases, jobs
from core.casework.model_check import ModelCheck, check_model
from core.contracts import ClaimStatus, ClaimType, EvidenceStatus, ExcerptSplit, Verdict
from core.db import connect
from core.report.html import render_report
from core.report.letter import request_letter
from core.restore.store import ExhibitError, add_exhibit, match_exhibits, remove_exhibit
from core.review import actions
from core.review.actions import ReviewError
from core.review.redecide import redecide
from ui import pages, restore_pages, theme, upload

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
    "/stipulate": ("audit",),
    "/stipulation/withdraw": ("audit",),
    "/redecide": ("audit",),
    "/claims/propose": ("audit", "propose", "model_check"),
    "/model/check": ("audit", "propose", "model_check"),
    "/audit/start": ("audit", "propose", "model_check"),
    "/case/import": ("audit", "propose", "model_check"),
    "/case/new": ("audit", "propose", "model_check"),
    "/case/open": ("audit", "propose", "model_check"),
}
NO_CASE_GET = {"/cases"}
NO_CASE_POST = {"/expert", "/case/new", "/case/open"}


def _real_components(conn: sqlite3.Connection, ai_review: bool) -> pipeline.Components:
    return pipeline.real_components(conn, ai_review=ai_review)


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
    """One screen. Either on one case database (`db_path`, as `baker serve --db`) or on a cases
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
    ) -> None:
        if db_path is None and home is None:
            raise ValueError("give a case database or a cases folder")
        if db_path is not None and not Path(db_path).exists():
            raise FileNotFoundError(f"no case database at {db_path}")
        self.home = None if db_path is not None else Path(home)  # type: ignore[arg-type]
        self.case: cases.Case | None = None
        self.token = secrets.token_urlsafe(32)
        self.expert: str | None = None
        self.flash: tuple[str, bool] | None = None
        self.port = port
        self.path = ""  # the request being answered, so a page can mark its tab
        self._added: str | None = None
        self.jobs = jobs.Jobs()
        self.components_for = components_for or _real_components
        self.extractor_for = extractor_for or _real_extractor
        self.model_check = model_check
        self.last_check: ModelCheck | None = None
        if expert:
            self.set_expert(expert)
        if db_path is not None:
            self.open_case(cases.Case(Path(db_path)))

    def _open(self) -> cases.Case:
        if self.case is None:
            raise ReviewError("open or make a case first")
        return self.case

    @property
    def db_path(self) -> Path | None:
        return None if self.case is None else self.case.db

    def open_case(self, case: cases.Case) -> None:
        conn = connect(case.db)
        try:
            pipeline.mark_stale_runs_stopped(conn)  # nothing in this process runs them
        finally:
            conn.close()
        self.case = case
        self.last_check = None

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
        if req.headers.get("host") not in self.allowed_hosts():
            return self._plain(400, "This screen only answers requests from this computer.")
        if req.method not in ("GET", "POST"):
            return self._plain(405, "method not allowed")
        if req.method == "GET" and req.path.startswith(FONT_PREFIX):
            return self._font(req.path[len(FONT_PREFIX) :])
        if req.method == "POST" and (
            not self._origin_ok(req)
            or not hmac.compare_digest(req.form.get("token", ""), self.token)
        ):
            return self._plain(403, "This form did not come from this review screen.")
        if self.case is None:
            if req.method == "GET" and req.path not in NO_CASE_GET:
                return self._redirect("/cases")
            if req.method == "POST" and req.path not in NO_CASE_POST:
                self.flash = ("Open or make a case first.", True)
                return self._redirect("/cases")
            if req.method == "GET":
                return self._cases()
            return self._post(None, req)
        try:
            conn = connect(self.case.db)
            conn.execute("PRAGMA busy_timeout = 10000")  # an audit may be saving a claim
        except sqlite3.Error as err:
            return self._plain(500, f"cannot open the case database: {err}")
        try:
            if req.method == "GET":
                return self._get(conn, req)
            return self._post(conn, req)
        finally:
            conn.close()

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
                "audit": f"The audit is running: {job.done} of {job.total} claims finished. "
                "<a href='/run'>See its progress</a>.",
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
            return self._html(pages.claims_queue(conn, page))
        if p == "/claim":
            body = pages.claim_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such claim")
        if p == "/claim/new":
            return self._html(pages.new_claim_page(conn, page))
        if p == "/evidence":
            body = pages.evidence_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such evidence item")
        if p == "/exhibits":
            return self._html(restore_pages.exhibits_page(conn, page))
        if p == "/exhibit":
            body = restore_pages.exhibit_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such exhibit")
        if p == "/exhibit/match":
            body = restore_pages.match_page(conn, page, req.query.get("id", ""))
            return self._html(body) if body else self._not_found(page, "no such match")
        if p == "/request-letter":
            return self._html(restore_pages.letter_page(conn, page))
        if p == "/request-letter.txt":
            return self._letter_text(conn, page)
        if p == "/log":
            return self._html(pages.log_page(conn, page, req.query.get("all") == "1"))
        if p in ("/report", "/report.html"):
            body = render_report(conn)
            download = req.query.get("download") == "1" or p == "/report.html"
            if not download:  # on screen, the vendored fonts; a saved copy uses system fonts
                body = body.replace("<style>", f"<style>{theme.FONT_CSS}", 1)
            resp = self._html(body)
            if download:
                resp.headers.append(
                    ("Content-Disposition", 'attachment; filename="baker-report.html"')
                )
            return resp
        return self._not_found(page, "no such page")

    # -- POST

    def _post(self, conn: sqlite3.Connection | None, req: Request) -> Response:
        f = req.form
        back = f.get("next", "")
        if not back.startswith("/") or back.startswith("//"):
            back = "/"
        handlers: dict[str, Callable[[], str]] = {
            "/expert": lambda: self._set_expert(f),
            "/case/new": lambda: self._new_case(f),
            "/case/open": lambda: self._open_case(f),
            "/evidence/decide": lambda: self._decide(conn, f),  # type: ignore[arg-type]
            "/verdict": lambda: self._verdict(conn, f),  # type: ignore[arg-type]
            "/claim/edit": lambda: self._edit_claim(conn, f),  # type: ignore[arg-type]
            "/claim/add": lambda: self._add_claim(conn, f),  # type: ignore[arg-type]
            "/claims/move": lambda: self._move_claim(conn, f),  # type: ignore[arg-type]
            "/claims/propose": lambda: self._propose(),
            "/stipulate": lambda: self._stipulate(conn, f),  # type: ignore[arg-type]
            "/stipulation/withdraw": lambda: self._withdraw(conn, f),  # type: ignore[arg-type]
            "/redecide": lambda: self._redecide(conn),  # type: ignore[arg-type]
            "/model/check": lambda: self._check_model(),
            "/audit/start": lambda: self._start_audit(conn, f),  # type: ignore[arg-type]
            "/audit/stop": lambda: self._stop_audit(),
            "/exhibit/add": lambda: self._add_exhibit(conn, f),  # type: ignore[arg-type]
            "/exhibit/remove": lambda: self._remove_exhibit(conn, f),  # type: ignore[arg-type]
            "/exhibit/rematch": lambda: self._rematch(conn, f),  # type: ignore[arg-type]
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
                back = "/setup"
            if req.path == "/exhibit/add" and self._added:
                back = pages.link("/exhibit", id=self._added)
        except (
            ReviewError,
            ExhibitError,
            InvariantViolation,
            ValueError,
            sqlite3.IntegrityError,
        ) as err:
            self.flash = (f"Not recorded: {err}", True)
        except sqlite3.OperationalError as err:  # the audit held the database too long
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

    # -- cases

    def _cases(self) -> Response:
        page = self._page()
        if self.home is None:
            return self._html(pages.cases_page(page, None, [], str(self.db_path)))
        rows = []
        for c in cases.list_cases(self.home):
            try:
                conn = connect(c.db)
                try:
                    state = cases.last_audit_line(conn)
                finally:
                    conn.close()
            except (sqlite3.Error, InvariantViolation) as err:
                state = f"cannot read: {err}"
            rows.append((c.folder.name, c.name, state))
        return self._html(pages.cases_page(page, self.home, rows, None))

    def _new_case(self, f: dict[str, str]) -> str:
        if self.home is None:
            raise ReviewError("this screen was started on one case database")
        case = cases.create_case(self.home, f.get("name", ""), self.actor)
        self.open_case(case)
        return f"Made the case {case.name}. Import its files below."

    def _open_case(self, f: dict[str, str]) -> str:
        if self.home is None:
            raise ReviewError("this screen was started on one case database")
        slug = f.get("case", "")
        match = [c for c in cases.list_cases(self.home) if c.folder.name == slug]
        if not match:
            raise ReviewError("no such case")
        self.open_case(match[0])
        return f"Opened {match[0].name}."

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
            note = f"Checked {check.checked_at_utc}."
        elif self.model_check is None:
            model_lines, note = None, "The model check is off for this screen."
        else:
            model_lines, note = None, "Not checked yet. The audit checks the model first."
        if job is not None and job.kind == "model_check" and job.running and job.hashed:
            done, total = job.hashed
            note = f"Checking: SHA-256 of the model file, {done * 100 // max(total, 1)}%."
        spc, source = jobs.seconds_per_call()
        n = len(order)
        estimate = (
            f"Rough estimate for {n} claims: {jobs.duration(jobs.estimate_seconds(n, spc))} "
            f"(about {jobs.CALLS_PER_CLAIM} model calls per claim at {spc:.0f} s per call, "
            f"{source}). Claims labeled before reuse their stored outputs and take seconds."
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
        if job is not None and not job.running and job.kind in ("propose", "model_check"):
            if page.flash is None:
                page.flash = (job.message, job.state != "done")
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
        )

    def _move_claim(self, conn: sqlite3.Connection, f: dict[str, str]) -> str:
        delta = -1 if f.get("delta") == "-1" else 1
        order = cases.move_claim(self._open(), conn, f.get("claim", ""), delta)
        cid = f.get("claim", "")
        return f"{cid} now runs at position {order.index(cid) + 1}."

    def _propose(self) -> str:
        _ = self.actor  # a named expert starts model work on the case
        self.jobs.start(
            jobs.Job("propose", self._open().db),
            jobs.propose_job(extractor_for=self.extractor_for),
        )
        return "The local model is proposing claims in the background. This page updates itself."

    def _check_model(self) -> str:
        if self.model_check is None:
            raise ReviewError("the model check is off for this screen")
        check = self.model_check

        def run(job: jobs.Job) -> None:
            jobs.model_check_job(check)(job)
            self.last_check = job.check

        self.jobs.start(jobs.Job("model_check", self._open().db), run)
        return "Checking the model in the background. This page updates itself."

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
        job.estimate_seconds = jobs.estimate_seconds(len(order), spc)
        check = self.model_check

        def model_check_once(progress: object = None) -> ModelCheck:
            result = check(progress=progress)  # type: ignore[misc]
            self.last_check = result
            return result

        self.jobs.start(
            job,
            jobs.audit_job(
                actor=actor,
                order=order,
                components_for=self.components_for,
                model_check=model_check_once if check is not None else None,
                ai_review=f.get("ai_review") == "1",
                label_all=f.get("label_all") == "1",
            ),
        )
        return (
            f"The audit started on {len(order)} claims, {jobs.duration(job.estimate_seconds)} by "
            "a rough estimate. Each claim appears for review as soon as it is labeled."
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
        counted = _Counting(stream)
        written: list[Path] = []

        def open_file() -> Path:
            written.append(cases.upload_path(case))
            return written[-1]

        def before_file(fields: dict[str, str]) -> None:
            if not hmac.compare_digest(fields.get("token", ""), self.token):
                raise _Refused
            self._guard("/case/import")
            _ = self.actor

        try:
            up = upload.parse(
                counted, length, req.headers.get("content-type", ""), open_file, before_file
            )
        except _Refused:
            for p in written:
                cases.discard(p)
            return self._plain(403, "This form did not come from this review screen.")
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
                ("Content-Disposition", 'attachment; filename="baker-request-draft.txt"'),
                *self._security_headers(),
            ],
        )

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


def _drain(stream: BinaryIO, n: int) -> None:
    """Read and drop the rest of a refused upload so the browser sees the answer, not a reset."""
    while n > 0:
        chunk = stream.read(min(n, 1 << 20))
        if not chunk:
            return
        n -= len(chunk)

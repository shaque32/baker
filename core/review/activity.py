"""The examiner's activity trail: each page the examiner opened in a case, in the audit log.

A page view is an audit-log entry with action `view` (core/review/audit_log.py), so it is
hash-chained with the expert's decisions, kept inside the case database (encrypted with it in
an encrypted case) and checked by `baker verify-log`. Nothing here is sent anywhere: the cloud
stance call sends only the filled-in stance prompt (core/llm/cloud.py), never the audit log.

What a view records: the time (UTC), the examiner's name, the screen session, the page, the
item it was opened on (a claim, an evidence item, an exhibit, a message), the evidence items
the page linked to, and for an evidence item its record and where that record sits in its
source (source id and locator). It never records the page's text.

What it cannot show. The screen runs no scripts, so Baker cannot tell what part of a page was
on screen, whether a folded section was opened, or whether the examiner read it. "Time on
page" is the time from opening a page to the examiner's next page or action in the same
session: an upper bound on attention, never proof of reading. A stretch longer than IDLE is
shown as such ("may include time away") and left out of totals. The last page of a session has
no end time. Views never change a verdict and are not an expert decision.

In the report. The report's Examiner activity table (core/report/html.py) is opt-in per case
and off by default: the expert turns it on or off on the Activity page, and each change is an
audit-log entry (action `report.activity`, with their name). The newest such entry decides, so
a report rendered from the audit log alone, as a bundle's is, gets the same answer.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from core.contracts import AuditLogEntry
from core.review import audit_log
from core.review.actions import _expert

VIEW = "view"
REPORT_ACTION = "report.activity"  # the expert put the activity table in the report, or not
UNNAMED = "viewer:unnamed"  # a page opened before the examiner entered a name
IDLE = timedelta(minutes=30)
MAX_LISTED = 500  # evidence ids kept per view; a longer list says how many were left out
MAX_VALUE = 200  # characters kept of a query value other than the item id, which is kept whole

PAGES = {
    "/": "Case overview",
    "/claims": "Claims queue",
    "/claim": "Claim",
    "/claim/new": "Add a claim",
    "/evidence": "Evidence item",
    "/identities": "Identities",
    "/exhibits": "Exhibits",
    "/exhibit": "Exhibit",
    "/exhibit/match": "Exhibit match",
    "/selection": "Selection audit",
    "/selection/context": "Message in its exchange",
    "/request-letter": "Full-extraction request",
    "/request-letter.txt": "Full-extraction request (download)",
    "/timeline": "Timeline check",
    "/gaps": "Gaps",
    "/flags/summary.json": "Flag summary (download)",
    "/log": "Audit log",
    "/activity": "Activity",
    "/activity.csv": "Activity (download)",
    "/report": "Report",
    "/report.html": "Report (download)",
    "/setup": "Set up and run",
    "/run": "Audit progress",
}

# Pages that show the trail or the log: recorded before they render, so they include
# themselves and end the time on the page before them. Not the report: it anchors the log
# first, and a report that cannot be anchored must leave the case unchanged.
RECORD_FIRST = frozenset({"/activity", "/activity.csv", "/log"})


def view_payload(
    conn: sqlite3.Connection,
    page: str,
    *,
    session: str,
    query: Mapping[str, str] | None = None,
    listed: Iterable[str] = (),
) -> dict:
    """The payload of one view entry. An evidence item's record and source location are read
    from the case, so the trail says where the record sits without storing its text."""
    query = dict(query or {})
    p: dict = {"page": page, "session": session}
    ident = query.pop("id", None)
    if ident is not None:
        p["id"] = ident  # whole, so the trail names the very claim or evidence item opened
    if query:
        p["query"] = {k[:MAX_VALUE]: v[:MAX_VALUE] for k, v in sorted(query.items())}
        if any(len(k) > MAX_VALUE or len(v) > MAX_VALUE for k, v in query.items()):
            p["query_cut"] = True  # a value was cut to MAX_VALUE characters
    if page == "/evidence" and ident is not None:
        row = conn.execute(
            "SELECT e.record_id, e.source_id, e.locator, a.claim_id FROM evidence_items e"
            " JOIN assumptions a ON a.id = e.assumption_id WHERE e.id = ?",
            (ident,),
        ).fetchone()
        if row is not None:
            p.update(record_id=row[0], source_id=row[1], locator=row[2], claim_id=row[3])
    items = list(dict.fromkeys(listed))
    if items:
        p["listed"] = items[:MAX_LISTED]
        if len(items) > MAX_LISTED:
            p["listed_left_out"] = len(items) - MAX_LISTED
    return p


def record_view(
    conn: sqlite3.Connection,
    at_utc: datetime,
    actor: str | None,
    page: str,
    *,
    session: str,
    query: Mapping[str, str] | None = None,
    listed: Iterable[str] = (),
) -> AuditLogEntry:
    """Append one view to the audit log, in its own transaction. actor: 'expert:<name>', or
    None before the examiner entered a name."""
    payload = view_payload(conn, page, session=session, query=query, listed=listed)
    with conn:
        return audit_log.append(conn, at_utc, actor or UNNAMED, VIEW, payload)


def in_report(conn: sqlite3.Connection) -> bool:
    """Whether the report shows the Examiner activity table: the newest `report.activity`
    entry says so; with none, it does not (off by default)."""
    row = conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq DESC LIMIT 1",
        (REPORT_ACTION,),
    ).fetchone()
    if row is None:
        return False
    try:
        payload = json.loads(row[0])
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("include") is True


def set_in_report(
    conn: sqlite3.Connection,
    at_utc: datetime,
    actor: str,
    include: bool,
    *,
    session: str | None = None,
) -> bool:
    """The expert's choice to put the activity table in the report, or leave it out, as an
    audit-log entry with their name and the screen session it came from (None: the command
    line), so a command never ends a page's time. Returns False, and logs nothing, when it is
    already so."""
    _expert(actor)
    if in_report(conn) == include:
        return False
    with conn:
        audit_log.append(
            conn, at_utc, actor, REPORT_ACTION, {"include": include, "session": session}
        )
    return True


# ---------------------------------------------------------------- reading the trail


@dataclass(frozen=True)
class Step:
    """One entry of the trail: a page view, or an action the examiner logged."""

    seq: int
    at_utc: str
    actor: str
    action: str
    payload: dict
    hash: str
    claim_id: str | None = None
    evidence_id: str | None = None
    seconds: float | None = None  # time on page until the next step; views only
    away: bool = False  # seconds is longer than IDLE

    @property
    def is_view(self) -> bool:
        return self.action == VIEW

    @property
    def examiner(self) -> str:
        if self.actor.startswith("expert:"):
            return self.actor[len("expert:") :]
        return "(no name entered)" if self.actor == UNNAMED else self.actor

    @property
    def where(self) -> str:
        """The page, or the action, in words."""
        if not self.is_view:
            return self.action
        page = str(self.payload.get("page", ""))
        return PAGES.get(page, page)


def _time(at: str) -> datetime | None:
    try:
        return datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return None


def _claims_of(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[str, str]]:
    """evidence id -> claim id, verdict id -> claim id."""
    ev = dict(
        conn.execute(
            "SELECT e.id, a.claim_id FROM evidence_items e JOIN assumptions a"
            " ON a.id = e.assumption_id"
        ).fetchall()
    )
    vd = dict(conn.execute("SELECT id, claim_id FROM verdicts").fetchall())
    return ev, vd


def steps(conn: sqlite3.Connection) -> list[Step]:
    """Every view and every action an expert logged, oldest first, each view with its time on
    page. A view's time ends at the next step; it has none when it was the last step, or when
    the next step is a view from another screen session (the screen was closed meanwhile, at a
    time Baker did not record). Read from the audit log only."""
    ev_claim, vd_claim = _claims_of(conn)
    rows = conn.execute(
        "SELECT seq, at_utc, actor, action, payload_json, hash FROM audit_log"
        " WHERE action = ? OR actor LIKE 'expert:%' ORDER BY seq",
        (VIEW,),
    ).fetchall()
    raw: list[Step] = []
    flag_claim: dict[str, object] = {}  # a withdrawal names only its flag
    for seq, at, actor, action, payload_json, h in rows:
        try:
            p = json.loads(payload_json)
        except ValueError:
            p = {}
        if not isinstance(p, dict):
            p = {}
        evidence = p.get("evidence_id")
        if action == VIEW and p.get("page") == "/evidence":
            evidence = p.get("id")
        claim = p.get("claim_id")
        if action == VIEW and p.get("page") == "/claim":
            claim = p.get("id")
        if claim is None and isinstance(evidence, str):
            claim = ev_claim.get(evidence)
        if claim is None and isinstance(p.get("verdict_id"), str):
            claim = vd_claim.get(p["verdict_id"])
        if action == "flag.add" and isinstance(p.get("flag_id"), str):
            flag_claim[p["flag_id"]] = claim
        if claim is None and action == "flag.withdraw":
            claim = flag_claim.get(p.get("flag_id"))
        raw.append(
            Step(
                seq=seq,
                at_utc=at,
                actor=actor,
                action=action,
                payload=p,
                hash=h,
                claim_id=claim if isinstance(claim, str) else None,
                evidence_id=evidence if isinstance(evidence, str) else None,
            )
        )
    next_view: list[int | None] = [None] * (len(raw) + 1)  # the first view at or after i
    for i in range(len(raw) - 1, -1, -1):
        next_view[i] = i if raw[i].is_view else next_view[i + 1]
    out: list[Step] = []
    for i, s in enumerate(raw):
        seconds = None
        end = _end(raw, i, next_view) if s.is_view else None
        start = _time(s.at_utc)
        if start is not None and end is not None and end >= start:
            seconds = (end - start).total_seconds()
        away = seconds is not None and seconds > IDLE.total_seconds()
        out.append(replace(s, seconds=seconds, away=away))
    return out


def _end(raw: list[Step], i: int, next_view: list[int | None]) -> datetime | None:
    """When the view raw[i] ended: at the next step, if that step is a view in the same screen
    session, or an action by the same examiner that the same session's next view follows (the
    page a form returns to). Otherwise unknown: the screen was closed, or the next step came
    from another session, another examiner or the command line."""
    view = raw[i]
    session = view.payload.get("session")
    if i + 1 >= len(raw):
        return None
    nxt = raw[i + 1]
    if nxt.is_view:
        return _time(nxt.at_utc) if nxt.payload.get("session") == session else None
    if nxt.actor != view.actor:
        return None
    if "session" in nxt.payload and nxt.payload["session"] != session:
        return None  # an action that names its session (None: the command line) is not this page's
    j = next_view[i + 2] if i + 2 <= len(raw) else None
    if j is None or raw[j].payload.get("session") != session:
        return None
    return _time(nxt.at_utc)


def duration(seconds: float | None, away: bool = False) -> str:
    """Time on page in words."""
    if seconds is None:
        return "unknown (no later step in this session)"
    if away:
        return f"over {int(IDLE.total_seconds() // 60)} min, may include time away"
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min {s} s" if s else f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m} min"


@dataclass
class ClaimActivity:
    """What the trail holds for one claim."""

    claim_id: str
    opened: int = 0  # views of the claim's page
    first_at: str | None = None
    last_at: str | None = None
    seconds: float = 0.0  # time on its pages, stretches over IDLE and untimed views left out
    away: int = 0  # stretches over IDLE
    untimed: int = 0  # views whose end Baker did not record
    evidence_opened: set[str] = field(default_factory=set)
    evidence_listed: set[str] = field(default_factory=set)
    listed_capped: bool = False  # a view listed more than MAX_LISTED: evidence_listed is a floor
    actions: int = 0  # expert actions logged on the claim or its evidence


def by_claim(trail: list[Step]) -> dict[str, ClaimActivity]:
    """Per claim: how often its page and its evidence items were opened, when first and last,
    time on those pages, the evidence its page listed and the expert actions on it."""
    out: dict[str, ClaimActivity] = {}
    for s in trail:
        if s.claim_id is None:
            continue
        a = out.setdefault(s.claim_id, ClaimActivity(s.claim_id))
        if not s.is_view:
            a.actions += 1
            continue
        page = s.payload.get("page")
        if page not in ("/claim", "/evidence"):
            continue
        a.first_at = a.first_at or s.at_utc
        a.last_at = s.at_utc
        if page == "/claim":
            a.opened += 1
            a.evidence_listed.update(x for x in s.payload.get("listed", []) if isinstance(x, str))
            a.listed_capped |= bool(s.payload.get("listed_left_out"))
        elif s.evidence_id is not None:
            a.evidence_opened.add(s.evidence_id)
        if s.away:
            a.away += 1
        elif s.seconds is None:
            a.untimed += 1
        else:
            a.seconds += s.seconds
    return out


def time_on_pages(a: ClaimActivity) -> str:
    """A claim's time on its pages in words, saying what the total leaves out."""
    idle = int(IDLE.total_seconds() // 60)
    out = duration(a.seconds)
    if a.away:
        out += f", plus {a.away} over {idle} min"
    if a.untimed:
        out += f", plus {a.untimed} not timed"
    return out


def listed_count(a: ClaimActivity) -> str:
    n = len(a.evidence_listed)
    return f"at least {n}" if a.listed_capped else str(n)


def summary(trail: list[Step]) -> dict:
    views = [s for s in trail if s.is_view]
    return {
        "views": len(views),
        "sessions": len({s.payload.get("session") for s in views}),
        "examiners": sorted({s.examiner for s in views}),
        "first_at": views[0].at_utc if views else None,
        "last_at": views[-1].at_utc if views else None,
    }


CSV_COLUMNS = (
    "seq",
    "at_utc",
    "examiner",
    "action",
    "page",
    "id",
    "claim_id",
    "evidence_id",
    "record_id",
    "source_id",
    "locator",
    "evidence_listed",
    "seconds_on_page",
    "note",
    "session",
    "entry_hash",
)


_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _cell(v: object) -> object:
    """A text cell a spreadsheet would run as a formula gets a leading apostrophe."""
    return "'" + v if isinstance(v, str) and v.startswith(_FORMULA) else v


def csv_text(trail: list[Step]) -> str:
    """The trail as CSV, one row per step, with each entry's audit-log hash so a row can be
    matched to the log `baker verify-log` checks."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for s in trail:
        p = s.payload
        note = ""
        if s.is_view and s.seconds is None:
            note = "time on page not recorded (last step, or the screen was closed)"
        elif s.away:
            note = "may include time away"
        row = [
            s.seq,
            s.at_utc,
            s.examiner,
            s.action,
            p.get("page", "") if s.is_view else "",
            p.get("id", "") if s.is_view else "",
            s.claim_id or "",
            s.evidence_id or "",
            p.get("record_id", ""),
            p.get("source_id", ""),
            p.get("locator", ""),
            len(p.get("listed", [])) + int(p.get("listed_left_out", 0)) if s.is_view else "",
            "" if s.seconds is None else f"{s.seconds:.0f}",
            note,
            p.get("session", "") if s.is_view else "",
            s.hash,
        ]
        w.writerow([_cell(v) for v in row])
    return buf.getvalue()

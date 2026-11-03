"""Why a claim got its verdict, in plain English, for the claim page.

A verdict's reasons (VerdictDecision.reasons) are written by the signed verdict rules
(core/audit/rules.py) for replay: each cites its rule number, the assumption by its stored text,
and the check's full detail with every case id ("Rule 1a: check time failed on 'The message
"its done" (person:dev:item1:owner ...)': Outside the window: msg:item1:Chats!1011 at ...").
They are the audit trail, and they stay exactly as stored: the claim page folds them under
"Technical details", and the report prints them in full.

`lines` gives each reason a first line a reader can follow: people and phones by the names the
case gives them, records as links, times in the claim's own zone. It reads the claim's stored
assumptions, checks and evidence, never decides anything, and changes no verdict: a reason it
cannot place prints as the rules wrote it, ids shown by name. Reasons that say the same thing
about one assumption (five records contradicting it) share one line.

Display only. The words here are Mabillon's (e()); text from the document or a record goes
through q(), as everywhere else, so the forbidden-word check reads them as cited.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.contracts import Assumption, AssumptionKind, CheckResult, EvidenceItem
from core.report.fmt import e, q
from core.report.names import Names
from core.review import device_names

_RULE = re.compile(r"^Rule (\w+): ")
_RECORD = re.compile(r"^Rule \w+: (\S+) (contradicts|complicates) ")
_COUNTED = re.compile(r"Counted (\d+) (\w+); the claim says ([^.]+)")
_WAITING = re.compile(r"; (\d+) AI-accepted item\(s\) await an expert")
_COVERED_AT = re.compile(r"covered at tier (\w+) by ")
_IGNORED = re.compile(r"^Ignored (\d+) evidence items")
_HOW = re.compile(
    r"\((accepted by an expert|accepted by the AI reviewer|model label on an? \w+ record, "
    r"not reviewed)\)"
)

PENDING = "Contradiction found, confirm to finalize"
AGENT_CONFIRMED = "An agent proposed this assumption, and an expert confirmed the failure."

_CHECK_LABEL = {
    "time": "time",
    "sender": "sender",
    "count": "count",
    "absence": "no-contact",
    "weekday": "weekday",
    "contact": "contact",
    "same_account": "same-account",
    "identity": "identity",
}
_KIND = {"msg": "message", "call": "call", "contact": "contact entry", "loc": "location"}
_RECORD_TABLES = ("messages", "calls", "contacts", "locations", "attachments")
_TIERS = {
    "derived": "a check of the phone records",
    "observed": "the phone records",
    "confirmed": "evidence an expert accepted",
    "ai_reviewed": "the AI reviewer's acceptance, not an expert's",
    "inferred": "an inference",
}
_NEEDS = {
    AssumptionKind.MEANING: "Only an expert can accept what the words mean.",
    AssumptionKind.EVENT: "Only a passing check or an expert can establish what happened.",
    AssumptionKind.IDENTITY: "Only a passing check or an expert can establish who it was.",
    AssumptionKind.COMPLETENESS: (
        "Only a passing check or an expert can establish what the records leave out."
    ),
}


@dataclass
class Line:
    """One plain line (HTML) and the reasons it stands for, verbatim as the rules stored them."""

    html: str
    reasons: list[str] = field(default_factory=list)


def _clock(dt: datetime) -> str:
    """'9:31 PM on March 4, 2026' (no strftime padding flags, which Windows lacks)."""
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'} on {dt:%B} {dt.day}, {dt.year}"


def _zone(name: str | None) -> tuple[tzinfo, str] | None:
    """The zone and how a reader says it: 'New York time', or 'UTC'."""
    if not name:
        return None
    try:
        z = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    if name.upper() in ("UTC", "ETC/UTC"):
        return z, "UTC"
    return z, name.rsplit("/", 1)[-1].replace("_", " ") + " time"


def _offset(minutes: int) -> str:
    if minutes == 0:
        return "UTC"
    sign = "+" if minutes > 0 else "-"
    h, m = divmod(abs(minutes), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


@dataclass
class _Record:
    id: str
    source_id: str | None
    ts_utc: datetime | None = None
    offset_min: int | None = None
    ts_raw: str | None = None
    sender: str | None = None  # a message's sending account: "SMS +12125550122"
    saved_as: str | None = None  # the name this phone saved for that account, as written
    name: str | None = None  # a contact entry's name, as written

    @property
    def kind(self) -> str:
        return _KIND.get(self.id.split(":", 1)[0], "record")


class _Case:
    """What the lines read from the case, each table read once a page."""

    def __init__(self, conn: sqlite3.Connection, names: Names) -> None:
        self.conn = conn
        self.names = names
        self._records: dict[str, _Record] = {}
        self._phones: dict[str, str] | None = None

    def record(self, rid: str) -> _Record:
        if rid in self._records:
            return self._records[rid]
        out = _Record(rid, None)
        m = self.conn.execute(
            "SELECT m.source_id, m.ts_utc, m.ts_offset_min, m.ts_raw, t.app, a.identifier,"
            " a.display_name FROM messages m LEFT JOIN threads t ON t.id = m.thread_id"
            " LEFT JOIN accounts a ON a.id = m.sender_account_id WHERE m.id = ?",
            (rid,),
        ).fetchone()
        if m is not None:
            out.source_id, ts, out.offset_min, out.ts_raw = m[0], m[1], m[2], m[3]
            out.ts_utc = datetime.fromisoformat(ts) if ts else None
            if m[5]:
                out.sender = " ".join(x for x in (m[4], m[5]) if x)
                out.saved_as = m[6] or None
        else:
            c = self.conn.execute(
                "SELECT source_id, ts_utc, ts_offset_min, ts_raw FROM calls WHERE id = ?", (rid,)
            ).fetchone()
            if c is not None:
                out.source_id, out.offset_min, out.ts_raw = c[0], c[2], c[3]
                out.ts_utc = datetime.fromisoformat(c[1]) if c[1] else None
            else:
                k = self.conn.execute(
                    "SELECT source_id, name FROM contacts WHERE id = ?", (rid,)
                ).fetchone()
                if k is not None:
                    out.source_id, out.name = k[0], k[1] or None
                for table in () if k is not None else _RECORD_TABLES[3:]:
                    r = self.conn.execute(
                        f"SELECT source_id FROM {table} WHERE id = ?",  # noqa: S608
                        (rid,),
                    ).fetchone()
                    if r is not None:
                        out.source_id = r[0]
                        break
        self._records[rid] = out
        return out

    def phone(self, source_id: str | None) -> str:
        """A source's phone as the case names it: the expert's name for it, else its label."""
        if self._phones is None:
            given = device_names.logged_names(self.conn)
            self._phones = {}
            for did, sid in self.conn.execute("SELECT id, source_id FROM devices ORDER BY id"):
                names = given.get(did)
                self._phones.setdefault(sid, names[0] if names else self.names.name(did))
        if source_id is None:
            return "the phone"
        return self._phones.get(source_id, source_id)

    def zone_of(self, source_id: str | None) -> str | None:
        if source_id is None:
            return None
        row = self.conn.execute(
            "SELECT timezone FROM devices WHERE source_id = ? AND timezone IS NOT NULL",
            (source_id,),
        ).fetchone()
        return row[0] if row else None


class _Writer:
    def __init__(
        self,
        conn: sqlite3.Connection,
        assumptions: list[Assumption],
        checks: list[CheckResult],
        evidence: list[EvidenceItem],
        names: Names,
        href: Callable[[str], str | None] | None,
    ) -> None:
        self.case = _Case(conn, names)
        self.names = names
        self.assumptions = assumptions
        self.checks = checks
        self.evidence = evidence
        self.href = href

    # ---- pieces

    def said(self, a: Assumption) -> str:
        """An assumption's text with its ids shown by name."""
        return self.names.html(a.text)

    def _label(self, r: _Record, when: bool) -> str:
        """'message on Item 1', a contact by its saved name; `when` adds the record's time in
        its phone's zone, to tell apart records that would read alike."""
        kind = e(r.kind) + (f" “{q(r.name)}”" if r.name else "")
        label = f"{kind} on {e(self.case.phone(r.source_id))}"
        if when and r.ts_utc is not None:
            zone = _zone(self.case.zone_of(r.source_id))
            at = r.ts_utc.astimezone(zone[0]) if zone else r.ts_utc
            label += e(f", {_clock(at)}" + ("" if zone else " UTC"))
        return label

    def records(self, rids: list[str], most: int = 3) -> str:
        """Links to the records, the first `most` of them, then how many more."""
        recs = [self.case.record(r) for r in rids]
        plain = [self._label(r, False) for r in recs]
        labels = [self._label(r, plain.count(p) > 1) for r, p in zip(recs, plain, strict=True)]
        shown = []
        for r, label in list(zip(recs, labels, strict=True))[:most]:
            if labels.count(label) > 1:  # still alike (no time): number them
                label += e(f" ({labels[: recs.index(r) + 1].count(label)})")
            target = self.href(r.id) if self.href else None
            shown.append(
                f"<span title='{e(r.id)}'>{label}</span>"
                if target is None
                else f"<a href='{e(target)}' title='{e(r.id)}'>{label}</a>"
            )
        more = len(rids) - len(shown)
        if more:
            shown.append(e(f"{more} more"))
        if len(shown) <= 2:
            return " and ".join(shown)
        return "; ".join(shown[:-1]) + "; and " + shown[-1]

    def assumption_in(self, reason: str) -> Assumption | None:
        """The assumption a reason quotes, by its stored text (the longest that fits)."""
        found = [a for a in self.assumptions if f"'{a.text}'" in reason]
        return max(found, key=lambda a: len(a.text)) if found else None

    def check_in(self, reason: str, a: Assumption, detail: bool = True) -> CheckResult | None:
        """The failed check a reason names on its assumption; `detail`: the reason quotes the
        check's detail (rule 1a), so two checks of one name on one assumption stay apart."""
        for c in self.checks:
            if c.assumption_id == a.id and f"check {c.check_name} failed" in reason:
                if not detail or (c.detail and c.detail in reason):
                    return c
        return None

    # ---- one line per rule

    def failed_check(self, c: CheckResult, a: Assumption) -> str:
        if c.check_name == "time":
            told = self.time_line(c, a)
            if told:
                return told
        if c.check_name == "sender":
            told = self.sender_line(c, a)
            if told:
                return told
        if c.check_name == "absence" and c.record_ids:
            kinds = Counter(self.case.record(r).kind for r in c.record_ids)
            held = " and ".join(_plural(n, k) for k, n in kinds.most_common())
            return (
                f"The phone records hold {e(held)} in that window, so this does not hold: "
                f"{self.said(a)}. Records: {self.records(list(c.record_ids))}."
            )
        if c.check_name == "count":
            m = _COUNTED.search(c.detail)
            if m:
                return (
                    f"The phone records hold {e(m[1])} {e(m[2])} where the claim needs "
                    f"{e(m[3])}: {self.said(a)}."
                )
        label = _CHECK_LABEL.get(c.check_name, c.check_name)
        rec = f" ({self.records(list(c.record_ids))})" if c.record_ids else ""
        return f"The {e(label)} check on the phone records{rec} does not match: {self.said(a)}."

    def time_line(self, c: CheckResult, a: Assumption) -> str | None:
        w = a.params.window
        recs = [self.case.record(r) for r in c.record_ids]
        recs = [r for r in recs if r.ts_utc is not None]
        if w is None or not recs:
            return None
        zone = _zone(w.tz) or _zone(self.case.zone_of(recs[0].source_id))
        if zone is None:
            return None
        z, zname = zone
        times = list(dict.fromkeys(_clock(r.ts_utc.astimezone(z)) for r in recs if r.ts_utc))
        what = recs[0].kind if len({r.kind for r in recs}) == 1 else "record"
        phones = {r.source_id for r in recs}
        who = (
            "Both phones record"
            if len(phones) == 2
            else f"All {len(phones)} phones record"
            if len(phones) > 2
            else "The phone records"
        )
        it = f"the {what}" if len(times) == 1 else "it"
        out = [
            f"{e(who)} {e(it)} at {e(' and at '.join(times))} ({e(zname)}), "
            f"not \u201c{q(w.raw)}\u201d as the claim states."
        ]
        for r in recs:
            if r.offset_min is None or r.ts_utc is None or not r.ts_raw:
                continue
            own = r.ts_utc.astimezone(z).utcoffset()
            if own is not None and int(own.total_seconds() // 60) != r.offset_min:
                out.append(
                    f"{e(self.case.phone(r.source_id))} prints it in {e(_offset(r.offset_min))} "
                    f"as \u201c{q(r.ts_raw)}\u201d, not in {e(zname)}."
                )
        out.append(f"Records: {self.records(list(c.record_ids))}.")
        return " ".join(out)

    def sender_line(self, c: CheckResult, a: Assumption) -> str | None:
        recs = [self.case.record(r) for r in c.record_ids]
        saved: dict[str, list[str]] = {}
        for r in recs:
            if r.sender:
                names = saved.setdefault(r.sender, [])
                if r.saved_as and r.saved_as not in names:
                    names.append(r.saved_as)
        people = a.params.person_ids or a.params.sent_by
        if not saved or not people:
            return None
        who = " or ".join(self.names.html(p) for p in people)
        froms = " and ".join(
            e(acct)
            + (
                " (saved as " + ", ".join(f"\u201c{q(n)}\u201d" for n in names) + ")"
                if names
                else ""
            )
            for acct, names in saved.items()
        )
        copies = "Every copy was" if len(recs) > 1 else "It was"
        return (
            f"No copy of the message came from {who}. {copies} sent from {froms}. "
            f"Records: {self.records(list(c.record_ids))}."
        )

    def line(self, reason: str) -> tuple[tuple[str, ...] | None, str]:
        """(group key, plain line HTML) for one reason; reasons with one key share a line."""
        m = _RULE.match(reason)
        rule = m[1] if m else ""
        a = self.assumption_in(reason)
        pending = PENDING in reason
        tail = " It counts once you confirm it." if pending else ""

        ignored = _IGNORED.match(reason)
        if ignored:
            n = int(ignored[1])
            return None, e(f"Left out {_plural(n, 'item')} that belong to other claims.")

        if rule == "1a" and a is not None:
            c = self.check_in(reason, a)
            if c is not None:
                line = self.failed_check(c, a)
                if AGENT_CONFIRMED in reason:
                    line += " An expert confirmed this failure."
                return None, line + tail

        rec = _RECORD.match(reason)
        if rec and a is not None:
            rid, verb = rec[1], rec[2]
            found = _HOW.search(reason[rec.end() :])
            how = found[1] if found else ""
            side = rule == "3d" and "non-core" in reason
            key = (rule, verb, a.id, how, str(pending), str(side))
            return key, rid  # finished in `lines`, which joins a group's records

        if rule == "3d" and a is not None and "check" in reason:
            c = self.check_in(reason, a, detail=False)
            label = _CHECK_LABEL.get(c.check_name, c.check_name) if c else "a"
            return None, (
                f"A {e(label)} check failed on a side point of the claim, which keeps it "
                f"from being supported: {self.said(a)}."
            )

        if rule == "2" and a is not None:
            if "is not covered" in reason:
                if "is proposed, but no expert has confirmed it" in reason:
                    return None, (
                        f"Not established: {self.said(a)}. Who uses the phone is proposed but "
                        "not confirmed by an expert yet."
                    )
                need = _NEEDS.get(a.kind, "It needs a passing check or an expert's acceptance.")
                return None, f"Not established: {self.said(a)}. {e(need)}"
            cov = _COVERED_AT.search(reason)
            if cov:
                by = _TIERS.get(cov[1], cov[1].replace("_", " "))
                return None, f"Shown by {e(by)}: {self.said(a)}."

        if rule == "3" and "expert-confirmed" in reason:
            return None, e(
                "Every part of the claim that has to be true is backed, and an expert accepted "
                "the supporting evidence."
            )
        if rule == "3" and "AI-reviewed" in reason:
            return None, e(
                "Every part of the claim that has to be true is backed, but the support rests on "
                "the AI reviewer, not an expert. You can confirm or override it."
            )
        if rule == "3a":
            return None, e("Nothing was tested: no part of this claim could be checked.")
        if rule == "3c":
            waiting = _WAITING.search(reason)
            line = (
                "No expert has accepted a supporting record yet. AI review sorts evidence but "
                "cannot make a claim supported."
                if "by an expert" in reason
                else "Neither an expert nor the AI reviewer has accepted a supporting record yet."
            )
            if waiting:
                n = int(waiting[1])
                verb = "waits" if n == 1 else "wait"
                line += f" {_plural(n, 'record')} the AI reviewer accepted {verb} for you."
            return None, e(line)
        if rule == "3e":
            return None, e(
                "The claim's central point was never tested: no check covers what this kind of "
                "claim turns on."
            )
        if rule == "3f" and a is not None:
            return None, (
                f"{self.said(a)} rests on AI review alone, which cannot carry this kind of "
                "claim. It needs a check or an expert."
            )
        return None, self.names.html(reason)

    def group_line(self, key: tuple[str, ...], rids: list[str]) -> str:
        rule, verb, aid, how, pending, side = key
        a = next(x for x in self.assumptions if x.id == aid)
        many = len(rids) > 1
        who = _plural(len(rids), "record") if many else "A record"
        verb_s = verb if not many else verb[:-1]  # contradicts -> contradict
        where = "a side point of the claim" if side == "True" else "this"
        out = f"{e(who)} {e(verb_s)} {e(where)}: {self.said(a)}."
        if how == "accepted by an expert":
            out += " An expert accepted " + ("each." if many else "it.")
        elif how == "accepted by the AI reviewer":
            out += " The AI reviewer accepted " + ("each" if many else "it") + ", not an expert."
        elif how:
            out += " " + e(f"A model labelled {'them' if many else 'it'}; nobody has reviewed it.")
        if verb == "complicates":
            out += " Not dismissed yet."
        if pending == "True":
            out += " It counts once you accept it."
        return out + f" {'Records' if many else 'Record'}: {self.records(rids, most=5)}."


def lines(
    conn: sqlite3.Connection,
    reasons: tuple[str, ...] | list[str],
    assumptions: list[Assumption],
    checks: list[CheckResult],
    evidence: list[EvidenceItem],
    *,
    names: Names | None = None,
    href: Callable[[str], str | None] | None = None,
) -> list[Line]:
    """The verdict's reasons as plain lines, in the rules' order, each with the reasons it
    stands for. `href` maps a record id to the page that shows it (None: no link)."""
    w = _Writer(conn, assumptions, checks, evidence, names or Names(conn), href)
    out: list[Line] = []
    groups: dict[tuple[str, ...], tuple[Line, list[str]]] = {}
    for reason in reasons:
        key, text = w.line(reason)
        if key is None:
            out.append(Line(text, [reason]))
            continue
        if key in groups:
            line, rids = groups[key]
            line.reasons.append(reason)
            rids.append(text)
        else:
            line = Line("", [reason])
            groups[key] = (line, [text])
            out.append(line)
    for key, (line, rids) in groups.items():
        line.html = w.group_line(key, rids)
    return out

"""Expert flags: a wrong label, a record Baker missed, or a verdict the expert disagrees with.

A flag is feedback about Baker, written by the expert on the claim page. It is optional, never
blocks review, and never changes an evidence status, a verdict or anything the rules read.

Storage. Flags live only in the case's append-only, hash-chained audit log (actions
'flag.add' and 'flag.withdraw'), so they need no new table and are tamper-evident like every
other expert action. The current flags are a replay of those entries. Each 'flag.add' keeps a
snapshot of what the expert saw when flagging (the verdict, the item's stance and review
status, the rule and prompt versions), because a later run changes those.

Export. summary() builds a redacted summary for the pilot's error log: kinds, enums, versions
and counts only. It never carries claim text, quotes, notes, names, record references, ids,
file names, hashes of inputs or times other than the export date. Nothing is sent anywhere:
the expert downloads the file and decides whether to share it.

error_log() combines summaries, one per pilot case, into the measured error log. Flagging is
voluntary, so every rate is a lower bound on what experts found wrong, not an error rate.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from core import pipeline
from core.contracts import Stance, Verdict
from core.review import audit_log
from core.review.actions import ReviewError

Clock = Callable[[], datetime]

ADD = "flag.add"
WITHDRAW = "flag.withdraw"
FORMAT = "baker-flag-summary"
FORMAT_VERSION = "1"

WRONG_LABEL = "wrong_label"
MISSED_RECORD = "missed_record"
VERDICT = "verdict"
KINDS = {
    WRONG_LABEL: "Wrong label",
    MISSED_RECORD: "Missed record",
    VERDICT: "Disagree with the verdict",
}
NOT_SURE = "not_sure"
STANCE_CHOICES = (*(s.value for s in Stance), NOT_SURE)
VERDICT_CHOICES = (*(v.value for v in Verdict), NOT_SURE)
NOTE_MAX = 1000
RECORD_MAX = 300


@dataclass
class Flag:
    id: str
    claim_id: str
    kind: str
    actor: str
    at_utc: str
    seq: int
    evidence_id: str | None = None
    should_be: str = NOT_SURE
    record: str = ""  # missed_record: where the expert found it, in their words
    note: str = ""
    at_flag: dict = field(default_factory=dict)  # snapshot: verdict, stance, versions
    withdrawn_by: str | None = None

    @property
    def active(self) -> bool:
        return self.withdrawn_by is None


def _now(clock: Clock | None) -> datetime:
    return (clock or (lambda: datetime.now(UTC)))()


def _expert(actor: str) -> str:
    if not actor.startswith("expert:") or len(actor) <= len("expert:"):
        raise ReviewError("enter your name on the case page before flagging")
    return actor


def _claim_exists(conn: sqlite3.Connection, claim_id: str) -> bool:
    return conn.execute("SELECT 1 FROM claims WHERE id = ?", (claim_id,)).fetchone() is not None


def _evidence_claim(conn: sqlite3.Connection, evidence_id: str) -> str | None:
    r = conn.execute(
        "SELECT a.claim_id FROM evidence_items e JOIN assumptions a ON a.id = e.assumption_id"
        " WHERE e.id = ?",
        (evidence_id,),
    ).fetchone()
    return r[0] if r else None


def _model(conn: sqlite3.Connection, model_run_id: str | None) -> dict | None:
    if not model_run_id:
        return None
    r = conn.execute(
        "SELECT purpose, model_name, prompt_version FROM model_runs WHERE id = ?", (model_run_id,)
    ).fetchone()
    if r is None:
        return None
    # A model name can be a file path on the expert's computer; keep the file name only.
    return {"purpose": r[0], "model": re.split(r"[\\/]", r[1])[-1], "prompt_version": r[2]}


def _snapshot(conn: sqlite3.Connection, claim_id: str, evidence_id: str | None) -> dict:
    """What the expert was looking at: enums and versions only."""
    from core.review.status import claim_state  # status imports pipeline; keep import light

    st = claim_state(conn, claim_id)
    snap: dict = {"claim_type": None, "verdict": None, "rule_version": None, "run_id": None}
    if st is not None:
        snap["claim_type"] = st.claim.claim_type.value
        snap["run_id"] = st.run_id
        if st.decision is not None:
            d = st.decision
            snap["verdict"] = d.verdict.value
            snap["rule_version"] = d.rule_version
            snap["expert_decided_verdict"] = d.confirmed_by is not None
            snap["supported_basis"] = (
                d.supported_basis.value if d.supported_basis is not None else None
            )
    if evidence_id:
        items = pipeline.load_evidence(conn, [evidence_id])
        if items:
            x = items[0]
            last = conn.execute(
                "SELECT reviewer_kind FROM evidence_reviews WHERE evidence_id = ?"
                " ORDER BY seq DESC LIMIT 1",
                (evidence_id,),
            ).fetchone()
            snap["stance"] = x.stance.value
            snap["evidence_status"] = x.status.value
            snap["last_reviewer"] = last[0] if last else None
            snap["record_kind"] = x.record_id.split(":", 1)[0]
            snap["model"] = _model(conn, x.model_run_id)
    return snap


def _next_id(conn: sqlite3.Connection) -> str:
    n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = ?", (ADD,)).fetchone()[0]
    return f"flag:{n + 1}"


def add_flag(
    conn: sqlite3.Connection,
    claim_id: str,
    kind: str,
    actor: str,
    evidence_id: str | None = None,
    should_be: str = NOT_SURE,
    record: str = "",
    note: str = "",
    clock: Clock | None = None,
) -> Flag:
    """Record one flag in the audit log. Changes nothing else in the case."""
    _expert(actor)
    if kind not in KINDS:
        raise ReviewError(f"unknown flag kind {kind!r}")
    if not _claim_exists(conn, claim_id):
        raise ReviewError(f"no claim {claim_id}")
    note, record = note.strip(), record.strip()
    should_be = should_be or NOT_SURE
    if len(note) > NOTE_MAX or len(record) > RECORD_MAX:
        raise ReviewError("the note or record is too long")
    if kind == WRONG_LABEL:
        if not evidence_id:
            raise ReviewError("a wrong-label flag names the evidence item")
        if _evidence_claim(conn, evidence_id) != claim_id:
            raise ReviewError(f"evidence item {evidence_id} is not on claim {claim_id}")
        if should_be not in STANCE_CHOICES:
            raise ReviewError(f"unknown label {should_be!r}")
    else:
        evidence_id = None
        if kind == VERDICT and should_be not in VERDICT_CHOICES:
            raise ReviewError(f"unknown verdict {should_be!r}")
        if kind == MISSED_RECORD:
            should_be = NOT_SURE
    now = _now(clock)
    with conn:
        flag_id = _next_id(conn)
        payload = {
            "flag_id": flag_id,
            "claim_id": claim_id,
            "kind": kind,
            "evidence_id": evidence_id,
            "should_be": should_be,
            "record": record,
            "note": note,
            "at_flag": _snapshot(conn, claim_id, evidence_id),
        }
        entry = audit_log.append(conn, now, actor, ADD, payload)
    return Flag(
        id=flag_id,
        claim_id=claim_id,
        kind=kind,
        actor=actor,
        at_utc=entry.at_utc.isoformat().replace("+00:00", "Z"),
        seq=entry.seq,
        evidence_id=evidence_id,
        should_be=should_be,
        record=record,
        note=note,
        at_flag=payload["at_flag"],
    )


def withdraw_flag(
    conn: sqlite3.Connection, flag_id: str, actor: str, clock: Clock | None = None
) -> None:
    """Take a flag back. The 'flag.add' entry stays in the log; the flag stops counting."""
    _expert(actor)
    current = {f.id: f for f in flags(conn)}
    if flag_id not in current:
        raise ReviewError(f"no flag {flag_id}")
    if not current[flag_id].active:
        raise ReviewError(f"{flag_id} was already withdrawn")
    with conn:
        audit_log.append(conn, _now(clock), actor, WITHDRAW, {"flag_id": flag_id})


def flags(conn: sqlite3.Connection, claim_id: str | None = None) -> list[Flag]:
    """Every flag, withdrawn ones included, in the order they were made."""
    out: dict[str, Flag] = {}
    for seq, at, actor, action, payload_json in conn.execute(
        "SELECT seq, at_utc, actor, action, payload_json FROM audit_log"
        " WHERE action IN (?, ?) ORDER BY seq",
        (ADD, WITHDRAW),
    ):
        p = json.loads(payload_json)
        if action == ADD:
            out[p["flag_id"]] = Flag(
                id=p["flag_id"],
                claim_id=p["claim_id"],
                kind=p["kind"],
                actor=actor,
                at_utc=at,
                seq=seq,
                evidence_id=p.get("evidence_id"),
                should_be=p.get("should_be") or NOT_SURE,
                record=p.get("record", ""),
                note=p.get("note", ""),
                at_flag=p.get("at_flag", {}),
            )
        elif p.get("flag_id") in out:
            out[p["flag_id"]].withdrawn_by = actor
    return [f for f in out.values() if claim_id is None or f.claim_id == claim_id]


def active_flags(conn: sqlite3.Connection, claim_id: str | None = None) -> list[Flag]:
    return [f for f in flags(conn, claim_id) if f.active]


# ---------------------------------------------------------------- redacted summary


def _denominators(conn: sqlite3.Connection) -> dict:
    """What the expert could have flagged, in the run on screen: counts only."""
    from core.review.status import claim_states

    states = claim_states(conn)
    verdicts: Counter[str] = Counter()
    stances: Counter[str] = Counter()
    expert_decisions: Counter[str] = Counter()
    for st in states:
        if st.decision is not None:
            verdicts[st.decision.verdict.value] += 1
        for x in st.evidence:
            if x.stance == Stance.IRRELEVANT:
                continue
            stances[x.stance.value] += 1
            if st.last_reviewer.get(x.id) == "expert":
                expert_decisions[x.status.value] += 1
    return {
        "claims": len(states),
        "claims_with_verdict": sum(verdicts.values()),
        "verdicts": dict(sorted(verdicts.items())),
        "evidence_items_shown": sum(stances.values()),
        "evidence_by_stance": dict(sorted(stances.items())),
        "expert_evidence_decisions": dict(sorted(expert_decisions.items())),
    }


def _redacted(f: Flag) -> dict:
    a = f.at_flag
    model = a.get("model") or {}
    return {
        "kind": f.kind,
        "should_be": f.should_be,
        "claim_type": a.get("claim_type"),
        "verdict_at_flag": a.get("verdict"),
        "verdict_decided_by_expert": bool(a.get("expert_decided_verdict")),
        "rule_version": a.get("rule_version"),
        "stance_at_flag": a.get("stance"),
        "evidence_status_at_flag": a.get("evidence_status"),
        "last_reviewer_at_flag": a.get("last_reviewer"),
        "record_kind": a.get("record_kind"),
        "model": model.get("model"),
        "prompt_version": model.get("prompt_version"),
        "has_note": bool(f.note),
        "names_a_record": bool(f.record),
    }


def summary(conn: sqlite3.Connection, pilot: str = "", clock: Clock | None = None) -> dict:
    """The redacted flag summary for this case: no case content, ready to share by hand."""
    all_flags = flags(conn)
    active = [f for f in all_flags if f.active]
    run = pipeline.view_run(conn)
    models = sorted(
        {
            (r[0], re.split(r"[\\/]", r[1])[-1], r[2])
            for r in conn.execute("SELECT purpose, model_name, prompt_version FROM model_runs")
        }
    )
    pilot = re.sub(r"\s+", " ", pilot).strip()[:60]
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "pilot": pilot,
        "exported_on": _now(clock).astimezone(UTC).date().isoformat(),
        "baker_version": run["baker_version"] if run else None,
        "rule_version": run["rule_version"] if run else None,
        "models": [{"purpose": p, "model": m, "prompt_version": v} for p, m, v in models],
        "audit_log_chain_ok": audit_log.verify_chain(conn),
        "denominators": _denominators(conn),
        "flag_counts": dict(sorted(Counter(f.kind for f in active).items())),
        "withdrawn": len(all_flags) - len(active),
        "flags": [_redacted(f) for f in active],
        "left_out": (
            "claim text, quotes, notes, names, record references, ids, file names, input "
            "hashes and times other than the export date"
        ),
    }


def summary_json(conn: sqlite3.Connection, pilot: str = "", clock: Clock | None = None) -> str:
    return json.dumps(summary(conn, pilot, clock), indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------- the measured error log


@dataclass
class PilotRow:
    pilot: str
    cases: int = 0
    claims_with_verdict: int = 0
    evidence_items_shown: int = 0
    wrong_label: int = 0
    missed_record: int = 0
    verdict: int = 0
    # (label the model gave, label the expert says it should be) -> count
    label_pairs: Counter = field(default_factory=Counter)
    # verdict at flag -> count
    verdict_disagreements: Counter = field(default_factory=Counter)
    versions: set = field(default_factory=set)

    @staticmethod
    def _rate(n: int, d: int) -> str:
        return f"{n}/{d} ({n / d:.1%})" if d else f"{n}/0"

    @property
    def label_rate(self) -> str:
        return self._rate(self.wrong_label, self.evidence_items_shown)

    @property
    def verdict_rate(self) -> str:
        return self._rate(self.verdict, self.claims_with_verdict)


def _check(s: dict) -> None:
    if s.get("format") != FORMAT:
        raise ValueError("not a Baker flag summary")
    if s.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"unsupported flag summary version {s.get('format_version')!r}")


def error_log(summaries: Iterable[dict]) -> list[PilotRow]:
    """One row per pilot: flags against what was there to flag, summed over that pilot's cases."""
    rows: dict[str, PilotRow] = {}
    for s in summaries:
        _check(s)
        name = s.get("pilot") or "(no pilot named)"
        row = rows.setdefault(name, PilotRow(name))
        den = s.get("denominators", {})
        row.cases += 1
        row.claims_with_verdict += int(den.get("claims_with_verdict", 0))
        row.evidence_items_shown += int(den.get("evidence_items_shown", 0))
        row.versions.add((s.get("baker_version"), s.get("rule_version")))
        for f in s.get("flags", []):
            kind = f.get("kind")
            if kind == WRONG_LABEL:
                row.wrong_label += 1
                row.label_pairs[(f.get("stance_at_flag"), f.get("should_be"))] += 1
            elif kind == MISSED_RECORD:
                row.missed_record += 1
            elif kind == VERDICT:
                row.verdict += 1
                row.verdict_disagreements[(f.get("verdict_at_flag"), f.get("should_be"))] += 1
    return [rows[k] for k in sorted(rows)]


def error_log_markdown(rows: list[PilotRow]) -> str:
    out = [
        "# Baker measured error log",
        "",
        "From expert flags in redacted pilot summaries. Flagging is optional, so each rate is a "
        "lower bound on what the expert found wrong, not a measured error rate.",
        "",
        "| Pilot | Cases | Wrong labels / items shown | Verdict disagreements / verdicts "
        "| Missed records |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r.pilot.replace('|', '/')} | {r.cases} | {r.label_rate} | {r.verdict_rate} "
            f"| {r.missed_record} |"
        )
    for r in rows:
        if not (r.label_pairs or r.verdict_disagreements):
            continue
        out += ["", f"## {r.pilot}", ""]
        for (was, should), n in sorted(r.label_pairs.items(), key=lambda kv: (-kv[1], kv[0])):
            out.append(f"- Label {was} flagged, expert says {should}: {n}")
        for (was, should), n in sorted(
            r.verdict_disagreements.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            out.append(f"- Verdict {was} flagged, expert says {should}: {n}")
        versions = ", ".join(f"Baker {b} rules {v}" for b, v in sorted(r.versions, key=str))
        out.append(f"- Versions: {versions}")
    return "\n".join(out) + "\n"

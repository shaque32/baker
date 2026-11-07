"""Plain guidance on each claim's verdict. Read-only.

The examiner hands Mabillon's report to defense counsel, who is not a forensic examiner. For
every claim the claim page and the report say, in the same words:
- what the verdict shown means, and what it does not mean ("not found" never means "did not
  happen");
- the judgment calls in the claim that the records cannot settle, for the examiner to make and
  for counsel to raise with the examiner.

It never changes a verdict, a label or a tier, and it adds no step to the review queue. The
verdict still comes from core/audit/rules.py; this module only reads what is stored.

Judgment calls come from two places:
- the claim's type: identity, role, content meaning, absence and event claims rest on judgment
  the phone records alone cannot settle (the same types rule 3c' never supports by code checks);
- phone ownership: a core assumption names a person whose phone ownership an expert has not
  confirmed (the device_owner stipulation rules.py waits on).
Type lines are left out once an expert decided the verdict (an expert-confirmed support or an
expert override), because the examiner has then made that call. The ownership line stays while
ownership is unconfirmed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from html import escape

from core.contracts import (
    ClaimType,
    EvidenceStatus,
    Stance,
    StipulationKind,
    StipulationStatus,
    SupportedBasis,
    Verdict,
)
from core.review.status import ClaimState

NOT_FOUND = (
    "It does not mean the claim is false. Not finding something in these records never means it "
    "did not happen; the checks and evidence below say what was searched."
)

TYPE_CALLS: dict[ClaimType, str] = {
    ClaimType.IDENTITY: "Who a person or account is. The records alone do not settle identity.",
    ClaimType.ROLE: "A person's role. That is a judgment beyond what the phone records show.",
    ClaimType.CONTENT_MEANING: (
        "What a message means. That is opinion, not something a record shows."
    ),
    ClaimType.ABSENCE: (
        "That something is not there. That depends on what the extraction covered, not only on "
        "what was searched."
    ),
    ClaimType.EVENT: (
        "An event in the world. The phone records alone may not settle whether it took place."
    ),
}


@dataclass(frozen=True)
class Guidance:
    means: str
    not_means: str
    judgment_calls: list[str] = field(default_factory=list)


def _meaning(st: ClaimState) -> tuple[str, str]:
    d = st.decision
    if st.incomplete or d is None:
        return (
            "There is no verdict yet: the audit has not finished this claim.",
            "Nothing can be read into it until the audit finishes.",
        )
    if st.untested:
        return (
            "Mabillon could not test this claim: no part of it could be checked against the "
            "records.",
            NOT_FOUND,
        )
    if d.override_note is not None:
        return (
            "An expert set this verdict by hand, with the note shown.",
            "It is not what the verdict rules decided from the records alone.",
        )
    if d.verdict is Verdict.SUPPORTED:
        if d.supported_basis is SupportedBasis.CONFIRMED:
            return (
                "An expert accepted the evidence for every core part of this claim, and the "
                "verdict rules supported it.",
                "It covers only what this claim says and what these records show.",
            )
        if d.supported_basis is SupportedBasis.CHECKED:
            return (
                "Every core part of this claim passed Mabillon's code checks against the phone "
                "records. No model label and no reviewer were involved.",
                "Nobody has judged what the messages mean, and the checks cover only the records "
                "in this extraction.",
            )
        if d.supported_basis is SupportedBasis.COUNSEL_REVIEWED:
            return (
                "A named defense lawyer accepted evidence for at least one core part of this "
                "claim.",
                "It is not an expert's acceptance.",
            )
        return (
            "The local AI reviewer accepted the evidence; no person has.",
            "It is not confirmed by anyone.",
        )
    if d.verdict is Verdict.CONTRADICTED:
        return (
            "A failed check, or contradicting evidence an expert accepted, goes against a core "
            "part of this claim.",
            "It does not prove the opposite of the claim. It shows these records do not bear the "
            "claim out as worded.",
        )
    if st.contradiction_found:
        return (
            "Mabillon found evidence against a core part of this claim. It counts once an expert "
            "confirms it.",
            NOT_FOUND,
        )
    if st.awaiting_expert:
        return (
            "Mabillon found supporting evidence that no person has accepted yet.",
            "The claim is not supported until an expert accepts that evidence.",
        )
    if _partly_borne_out(st):
        return (
            "Some core parts of this claim have support in these records, but not every core "
            "part, so the claim as a whole is not established.",
            NOT_FOUND,
        )
    return "These records neither support nor contradict this claim.", NOT_FOUND


PERSON_ACCEPTED = (EvidenceStatus.ACCEPTED, EvidenceStatus.COUNSEL_ACCEPTED)


def _partly_borne_out(st: ClaimState) -> bool:
    """A core part has support: the stored verdict found it covered, or a person accepted
    supporting evidence on it (which counts once the verdict is decided again)."""
    d = st.decision
    if d is not None and any(cv.covered for cv in d.coverage):
        return True
    core = {a.id for a in st.assumptions if a.is_core}
    return any(
        e.stance is Stance.SUPPORTS and e.status in PERSON_ACCEPTED and e.assumption_id in core
        for e in st.evidence
    )


def unconfirmed_owners(conn: sqlite3.Connection, st: ClaimState) -> list[str]:
    """Names of people a core assumption of this claim names whose phone ownership is proposed
    but not confirmed by an expert (the same test as rules.py's _unconfirmed_people)."""
    people = sorted({p for a in st.assumptions if a.is_core for p in a.params.person_ids})
    out = []
    for pid in people:
        rows = [
            r[0]
            for r in conn.execute(
                "SELECT status FROM stipulations WHERE kind = ? AND person_id = ?",
                (StipulationKind.DEVICE_OWNER.value, pid),
            )
            if r[0] != StipulationStatus.REJECTED.value
        ]
        if rows and StipulationStatus.CONFIRMED.value not in rows:
            name = conn.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()
            out.append(name[0] if name else pid)
    return out


def _expert_decided(st: ClaimState) -> bool:
    d = st.decision
    if d is None:
        return False
    return d.override_note is not None or (
        d.verdict is Verdict.SUPPORTED and d.supported_basis is SupportedBasis.CONFIRMED
    )


def judgment_calls(conn: sqlite3.Connection, st: ClaimState) -> list[str]:
    """The judgment calls in this claim that the records cannot settle."""
    out = []
    owners = unconfirmed_owners(conn, st)
    if owners:
        out.append(
            f"Phone ownership is not confirmed for {', '.join(owners)}. The verdict waits on an "
            "expert confirming who owns the phone."
        )
    if not _expert_decided(st) and st.claim.claim_type in TYPE_CALLS:
        out.append(TYPE_CALLS[st.claim.claim_type])
    return out


def for_claim(conn: sqlite3.Connection, st: ClaimState) -> Guidance:
    means, not_means = _meaning(st)
    return Guidance(means=means, not_means=not_means, judgment_calls=judgment_calls(conn, st))


def html(g: Guidance) -> str:
    """The same block on the claim page and in the report."""
    out = [
        "<div class='guide'>",
        f"<p><strong>What this means:</strong> {escape(g.means)}</p>",
        f"<p><strong>What it does not mean:</strong> {escape(g.not_means)}</p>",
    ]
    if g.judgment_calls:
        out.append("<p><strong>Judgment calls the records can't settle:</strong></p>")
        out.append("<ul>" + "".join(f"<li>{escape(t)}</li>" for t in g.judgment_calls) + "</ul>")
    out.append("</div>")
    return "".join(out)

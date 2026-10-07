"""Expert review actions. Every action is a human decision and is written to the audit log.

The actor is always 'expert:<name>'. These are the only functions that set an evidence item to
'accepted', confirm or override a verdict, or confirm an identity link. Nothing here is called
by the pipeline on its own.

A human decision always overrides the AI reviewer: an expert decision is a new row in the
append-only evidence_reviews table, the latest row is the item's status, and the pipeline never
asks the AI about an item that already has a decision.

Verdict confirmations and overrides apply to the verdict of the latest completed pipeline run.
A re-run makes new verdicts, which the expert confirms again.

Phone ownership. Every case01 claim rests on "Item 1 is PETROV's phone, Item 2 is REYES's".
Nothing in the extraction data can raise that above inferred, so the expert stipulates it once
per case with stipulate_device_owner. rules.py counts a confirmed stipulation at tier confirmed,
and every report prints each one as a limitation.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from core.contracts import (
    ClaimStatus,
    ClaimType,
    EvidenceStatus,
    IdentityLinkStatus,
    ProvenanceTier,
    ReviewDecision,
    ReviewerKind,
    StipulationKind,
    StipulationStatus,
    SupportedBasis,
    Verdict,
    review_id,
    stipulation_id,
)
from core.review import audit_log

Clock = Callable[[], datetime]


class ReviewError(Exception):
    pass


def _now(clock: Clock | None) -> datetime:
    return (clock or (lambda: datetime.now(UTC)))()


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _expert(actor: str) -> str:
    if not actor.startswith("expert:") or len(actor) <= len("expert:"):
        raise ReviewError(f"actor must be 'expert:<name>', got {actor!r}")
    return actor


# ---------------------------------------------------------------- evidence


def decide_evidence(
    conn: sqlite3.Connection,
    evidence_id: str,
    status: EvidenceStatus,
    actor: str,
    reason: str,
    clock: Clock | None = None,
) -> ReviewDecision:
    """Accept, dismiss or reopen one evidence item. Overrides whatever the AI reviewer decided."""
    _expert(actor)
    if not reason.strip():
        raise ReviewError("say why, in one sentence")
    if conn.execute("SELECT 1 FROM evidence_items WHERE id = ?", (evidence_id,)).fetchone() is None:
        raise ReviewError(f"no evidence item {evidence_id}")
    seq = (
        conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM evidence_reviews WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()[0]
        + 1
    )
    now = _now(clock)
    d = ReviewDecision(
        id=review_id(evidence_id, seq),
        evidence_id=evidence_id,
        seq=seq,
        reviewer_kind=ReviewerKind.EXPERT,
        reviewer=actor,
        status=status,
        reason=reason,
        model_run_id=None,
        decided_at_utc=now,
    )
    with conn:
        conn.execute(
            "INSERT INTO evidence_reviews (id, evidence_id, seq, reviewer_kind, reviewer, status,"
            " reason, model_run_id, model_call_id, decided_at_utc)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)",
            (d.id, evidence_id, seq, d.reviewer_kind.value, actor, status.value, reason, _iso(now)),
        )
        audit_log.append(
            conn,
            now,
            actor,
            "evidence.decide",
            {"evidence_id": evidence_id, "review_id": d.id, "status": status.value},
        )
    return d


# ---------------------------------------------------------------- verdicts


def _current_verdict(conn: sqlite3.Connection, claim_id: str) -> tuple[str, str]:
    """(verdict id, verdict) in the latest completed run."""
    row = conn.execute(
        "SELECT v.id, v.verdict FROM verdicts v JOIN pipeline_runs r ON r.id = v.pipeline_run_id"
        " WHERE v.claim_id = ? AND r.status = 'completed'"
        " ORDER BY r.started_at_utc DESC, r.id DESC LIMIT 1",
        (claim_id,),
    ).fetchone()
    if row is None:
        raise ReviewError(f"no verdict for {claim_id}; run the audit first")
    return row[0], row[1]


def confirm_verdict(
    conn: sqlite3.Connection, claim_id: str, actor: str, note: str = "", clock: Clock | None = None
) -> None:
    _expert(actor)
    vid, verdict = _current_verdict(conn, claim_id)
    with conn:
        conn.execute(
            "UPDATE verdicts SET confirmed_by = ?, override_note = NULL WHERE id = ?", (actor, vid)
        )
        audit_log.append(
            conn,
            _now(clock),
            actor,
            "verdict.confirm",
            {"verdict_id": vid, "verdict": verdict, "note": note},
        )


def override_verdict(
    conn: sqlite3.Connection,
    claim_id: str,
    verdict: Verdict,
    actor: str,
    note: str,
    clock: Clock | None = None,
) -> None:
    """The expert's own verdict. The report shows it as an expert override, with the note."""
    _expert(actor)
    if not note.strip():
        raise ReviewError("an override needs a note saying why")
    vid, was = _current_verdict(conn, claim_id)
    if verdict == Verdict.SUPPORTED:
        # The verdicts table ties SUPPORTED to a supported_basis; an override records the
        # expert as the basis.
        basis = SupportedBasis.CONFIRMED.value
    else:
        basis = None
    with conn:
        conn.execute(
            "UPDATE verdicts SET verdict = ?, supported_basis = ?, confirmed_by = ?,"
            " override_note = ? WHERE id = ?",
            (verdict.value, basis, actor, note, vid),
        )
        audit_log.append(
            conn,
            _now(clock),
            actor,
            "verdict.override",
            {"verdict_id": vid, "verdict": verdict.value, "was": was, "note": note},
        )


# ---------------------------------------------------------------- claims


def add_claim(
    conn: sqlite3.Connection,
    claim_id: str,
    paragraph_id: str,
    text: str,
    claim_type: ClaimType,
    actor: str,
    clock: Clock | None = None,
) -> None:
    """A claim the expert wrote or entered. model_run_id stays NULL."""
    _expert(actor)
    with conn:
        conn.execute(
            "INSERT INTO claims (id, paragraph_id, text, claim_type, status, model_run_id)"
            " VALUES (?, ?, ?, ?, ?, NULL)",
            (claim_id, paragraph_id, text, claim_type.value, ClaimStatus.ACCEPTED.value),
        )
        audit_log.append(
            conn,
            _now(clock),
            actor,
            "claim.add",
            {"claim_id": claim_id, "paragraph_id": paragraph_id, "text": text},
        )


def set_claim_status(
    conn: sqlite3.Connection,
    claim_id: str,
    status: ClaimStatus,
    actor: str,
    text: str | None = None,
    clock: Clock | None = None,
) -> None:
    """Accept, edit (with new text) or remove a claim."""
    _expert(actor)
    if status == ClaimStatus.PROPOSED:
        raise ReviewError("only the claim extractor proposes claims")
    if (status == ClaimStatus.EDITED) != (text is not None):
        raise ReviewError("pass new text exactly when the status is 'edited'")
    row = conn.execute("SELECT status, text FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if row is None:
        raise ReviewError(f"no claim {claim_id}")
    with conn:
        conn.execute(
            "UPDATE claims SET status = ?, text = ? WHERE id = ?",
            (status.value, text if text is not None else row[1], claim_id),
        )
        audit_log.append(
            conn,
            _now(clock),
            actor,
            "claim.status",
            {"claim_id": claim_id, "status": status.value, "was": row[0], "text": text},
        )


# ---------------------------------------------------------------- identity


def decide_identity_link(
    conn: sqlite3.Connection,
    link_id: str,
    status: IdentityLinkStatus,
    actor: str,
    note: str = "",
    clock: Clock | None = None,
) -> None:
    """Confirm or reject a proposed link. Links never merge on their own."""
    _expert(actor)
    if status not in (IdentityLinkStatus.CONFIRMED, IdentityLinkStatus.REJECTED):
        raise ReviewError("an expert decision on a link is 'confirmed' or 'rejected'")
    row = conn.execute("SELECT status FROM identity_links WHERE id = ?", (link_id,)).fetchone()
    if row is None:
        raise ReviewError(f"no identity link {link_id}")
    now = _now(clock)
    tier = ProvenanceTier.CONFIRMED if status == IdentityLinkStatus.CONFIRMED else None
    with conn:
        conn.execute(
            "UPDATE identity_links SET status = ?, tier = COALESCE(?, tier), decided_by = ?,"
            " decided_at_utc = ? WHERE id = ?",
            (status.value, tier, actor, _iso(now), link_id),
        )
        audit_log.append(
            conn,
            now,
            actor,
            "identity.decide",
            {"link_id": link_id, "status": status.value, "was": row[0], "note": note},
        )


def stipulate_device_owner(
    conn: sqlite3.Connection,
    device_id: str,
    person_name: str,
    actor: str,
    clock: Clock | None = None,
) -> str:
    """The expert stipulates who used a device. Returns the stipulation id.

    This is a case-level statement the expert makes, not a finding: Baker never verifies it.
    Reports print every confirmed stipulation as a limitation.
    """
    _expert(actor)
    if not person_name.strip():
        raise ReviewError("person name is empty")
    dev = conn.execute("SELECT label FROM devices WHERE id = ?", (device_id,)).fetchone()
    if dev is None:
        raise ReviewError(f"no device {device_id}")
    now = _now(clock)
    person_id = f"person:{device_id}:owner"
    sid = stipulation_id(StipulationKind.DEVICE_OWNER, device_id)
    statement = f"{person_name} used {dev[0]} ({device_id})."
    with conn:
        conn.execute(
            "INSERT INTO persons (id, name, created_by) VALUES (?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET name = excluded.name, created_by = excluded.created_by",
            (person_id, person_name, actor),
        )
        conn.execute(
            "INSERT INTO stipulations (id, kind, subject_id, person_id, statement, status,"
            " decided_by, decided_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET person_id = excluded.person_id,"
            " statement = excluded.statement, status = excluded.status,"
            " decided_by = excluded.decided_by, decided_at_utc = excluded.decided_at_utc",
            (
                sid,
                StipulationKind.DEVICE_OWNER.value,
                device_id,
                person_id,
                statement,
                StipulationStatus.CONFIRMED.value,
                actor,
                _iso(now),
            ),
        )
        audit_log.append(
            conn,
            now,
            actor,
            "stipulation.confirm",
            {"stipulation_id": sid, "person": person_name, "statement": statement},
        )
    return sid


def withdraw_stipulation(
    conn: sqlite3.Connection, stipulation_id_: str, actor: str, clock: Clock | None = None
) -> None:
    _expert(actor)
    if (
        conn.execute("SELECT 1 FROM stipulations WHERE id = ?", (stipulation_id_,)).fetchone()
        is None
    ):
        raise ReviewError(f"no stipulation {stipulation_id_}")
    now = _now(clock)
    with conn:
        conn.execute(
            "UPDATE stipulations SET status = ?, decided_by = ?, decided_at_utc = ? WHERE id = ?",
            (StipulationStatus.REJECTED.value, actor, _iso(now), stipulation_id_),
        )
        audit_log.append(
            conn, now, actor, "stipulation.withdraw", {"stipulation_id": stipulation_id_}
        )

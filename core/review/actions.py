"""Expert review actions. Every action is a human decision and is written to the audit log.

The actor is always 'expert:<name>'. These are the only functions that set an evidence item to
'accepted', confirm or override a verdict, or confirm an identity link. Nothing here is called
by the pipeline on its own.

A human decision always overrides the AI reviewer: an expert decision is a new row in the
append-only evidence_reviews table, the latest row is the item's status, and the pipeline never
asks the AI about an item that already has a decision.

Verdict confirmations and overrides apply to the verdict of the latest completed pipeline run.
A re-run makes new verdicts, which the expert confirms again. Neither is accepted while a model
rationale on the claim's evidence is withheld for a forbidden word and not yet acknowledged
(core/review/withheld.py).

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
            # the reason too, so editing it in evidence_reviews no longer matches the log
            {
                "evidence_id": evidence_id,
                "review_id": d.id,
                "status": status.value,
                "reason": reason,
            },
        )
    return d


# ---------------------------------------------------------------- agent proposals


def decide_repair(
    conn: sqlite3.Connection,
    claim_id: str,
    run_id: str,
    attempt: int,
    accept: bool,
    actor: str,
    reason: str,
    clock: Clock | None = None,
) -> None:
    """Accept or reject one testability proposal (core/audit/testability.py) from the claim
    page's card: the try the step proposed for this claim in that audit. Only an acceptance puts
    its assumptions in the case, and only from the next audit on, when the step gives the same
    assumptions again for the same claim text. Nothing is used before then, and the claim's text
    is never changed. One proposal at a time; there is no accept-all."""
    import json

    from core.audit import testability

    _expert(actor)
    if not reason.strip():
        raise ReviewError("say why, in one sentence")
    entry = None
    for (payload_json,) in conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq",
        (testability.REPAIR_ACTION,),
    ):
        p = json.loads(payload_json)
        if (
            p.get("run_id") == run_id
            and p.get("claim_id") == claim_id
            and p.get("attempt") == attempt
            and p.get("outcome") == "proposed"
        ):
            entry = p
    if entry is None:
        raise ReviewError(f"no agent proposal for {claim_id} in that audit")
    if entry.get("claim_sha256") != testability.claim_sha256(conn, claim_id):
        raise ReviewError(
            f"{claim_id} changed after the agent proposed this; the next audit proposes again"
        )
    with conn:
        audit_log.append(
            conn,
            _now(clock),
            actor,
            testability.ACCEPT_ACTION if accept else testability.REJECT_ACTION,
            {
                "claim_id": claim_id,
                "claim_sha256": entry["claim_sha256"],
                "testability": entry.get("testability"),
                "run_id": run_id,
                "attempt": attempt,
                "model_call_id": entry.get("model_call_id"),
                "assumption_ids": sorted(entry.get("assumption_ids") or []),
                "reason": reason.strip(),
                "via": "claim page",
            },
        )


# ---------------------------------------------------------------- verdicts


def _current_verdict(conn: sqlite3.Connection, claim_id: str) -> tuple[str, str]:
    """(verdict id, verdict) in the run the screen shows: the latest completed run, or an
    audit that has not finished (pipeline.view_run()), whose finished claims are reviewable."""
    from core import pipeline  # core.pipeline imports this package

    run = pipeline.view_run(conn)
    if run is not None and run.get("partial"):
        row = conn.execute(
            "SELECT id, verdict FROM verdicts WHERE claim_id = ? AND pipeline_run_id = ?",
            (claim_id, run["run_id"]),
        ).fetchone()
        if row is None:
            raise ReviewError(f"labeling of {claim_id} is not finished; no verdict yet")
        return row[0], row[1]
    row = conn.execute(
        "SELECT v.id, v.verdict FROM verdicts v JOIN pipeline_runs r ON r.id = v.pipeline_run_id"
        " WHERE v.claim_id = ? AND r.status = 'completed'"
        " ORDER BY r.started_at_utc DESC, r.id DESC LIMIT 1",
        (claim_id,),
    ).fetchone()
    if row is None:
        raise ReviewError(f"no verdict for {claim_id}; run the audit first")
    return row[0], row[1]


def _withheld_acknowledged(conn: sqlite3.Connection, claim_id: str) -> None:
    """Sign-off waits until the expert has acknowledged every withheld rationale on the claim."""
    from core.review import withheld  # withheld imports this module

    left = withheld.waiting(conn, claim_id)
    if left:
        raise ReviewError(
            f"acknowledge the {len(left)} withheld model rationale(s) on this claim first: "
            + ", ".join(w.evidence_id for w in left)
        )


def confirm_verdict(
    conn: sqlite3.Connection, claim_id: str, actor: str, note: str = "", clock: Clock | None = None
) -> None:
    _expert(actor)
    vid, verdict = _current_verdict(conn, claim_id)
    _withheld_acknowledged(conn, claim_id)
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
    _withheld_acknowledged(conn, claim_id)
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
            {
                "claim_id": claim_id,
                "paragraph_id": paragraph_id,
                "text": text,
                "claim_type": claim_type.value,
            },
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
            {
                "claim_id": claim_id,
                "status": status.value,
                "was": row[0],
                "text": text,
                "was_text": row[1],
            },
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
    """Confirm, reject or leave unresolved a link. Links never merge on their own.

    Only 'confirmed' raises the link to tier confirmed, and only a confirmed link counts in a
    check. Any other decision puts the tier back to inferred. The expert can change a decision
    later; each one is a new audit-log entry.
    """
    _expert(actor)
    decided = (
        IdentityLinkStatus.CONFIRMED,
        IdentityLinkStatus.REJECTED,
        IdentityLinkStatus.UNRESOLVED,
    )
    if status not in decided:
        raise ReviewError("an expert decision on a link is 'confirmed', 'rejected' or 'unresolved'")
    if status is not IdentityLinkStatus.UNRESOLVED and not note.strip():
        raise ReviewError("say why, in one sentence")
    row = conn.execute("SELECT status FROM identity_links WHERE id = ?", (link_id,)).fetchone()
    if row is None:
        raise ReviewError(f"no identity link {link_id}")
    now = _now(clock)
    tier = (
        ProvenanceTier.CONFIRMED
        if status == IdentityLinkStatus.CONFIRMED
        else ProvenanceTier.INFERRED
    )
    with conn:
        conn.execute(
            "UPDATE identity_links SET status = ?, tier = ?, decided_by = ?,"
            " decided_at_utc = ? WHERE id = ?",
            (status.value, tier.value, actor, _iso(now), link_id),
        )
        audit_log.append(
            conn,
            now,
            actor,
            "identity.decide",
            {"link_id": link_id, "status": status.value, "was": row[0], "note": note},
        )


def link_account(
    conn: sqlite3.Connection,
    account_id: str,
    person_id: str,
    actor: str,
    note: str,
    clock: Clock | None = None,
) -> str:
    """The expert links an account to a person themselves (a link code did not propose).
    It is the expert's own decision, so it is confirmed at once. Returns the link id."""
    _expert(actor)
    if not note.strip():
        raise ReviewError("say why, in one sentence")
    if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is None:
        raise ReviewError(f"no account {account_id}")
    if conn.execute("SELECT 1 FROM persons WHERE id = ?", (person_id,)).fetchone() is None:
        raise ReviewError(f"no person {person_id}")
    lid = f"link:{account_id}|{person_id}"
    if conn.execute("SELECT 1 FROM identity_links WHERE id = ?", (lid,)).fetchone():
        decide_identity_link(conn, lid, IdentityLinkStatus.CONFIRMED, actor, note, clock)
        return lid
    now = _now(clock)
    with conn:
        conn.execute(
            "INSERT INTO identity_links (id, account_id, person_id, status, tier, basis,"
            " decided_by, decided_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lid,
                account_id,
                person_id,
                IdentityLinkStatus.CONFIRMED.value,
                ProvenanceTier.CONFIRMED.value,
                f"Linked by {actor}: {note.strip()}",
                actor,
                _iso(now),
            ),
        )
        audit_log.append(
            conn,
            now,
            actor,
            "identity.link",
            {"link_id": lid, "account_id": account_id, "person_id": person_id, "note": note},
        )
    return lid


def add_person(conn: sqlite3.Connection, name: str, actor: str, clock: Clock | None = None) -> str:
    """The expert adds a person the government document names, written as the document writes
    it ("ALEXANDER SOKOLOV"). A person is only a name: nothing ties them to an account until an
    expert confirms a link. Refused when the name would make another person's name ambiguous
    for the assumption filler (same whole name or same surname). Returns the person id."""
    from core.identity.links import person_id_for, tokens

    _expert(actor)
    name = " ".join(name.split())
    words = tokens(name)
    if not words or len(name) > 120:
        raise ReviewError("enter the name as the document writes it (up to 120 characters)")
    rows = list(conn.execute("SELECT id, name FROM persons ORDER BY id"))
    for pid, other in rows:
        theirs = tokens(other)
        if not theirs:
            continue
        mine = {" ".join(words), words[-1]}
        if mine & {" ".join(theirs), theirs[-1]}:
            raise ReviewError(
                f"{name} would also match {other} ({pid}); the audit could not tell them apart"
            )
    pid = person_id_for(name, (r[0] for r in rows))
    now = _now(clock)
    with conn:
        conn.execute(
            "INSERT INTO persons (id, name, created_by) VALUES (?, ?, ?)", (pid, name, actor)
        )
        audit_log.append(conn, now, actor, "person.add", {"person_id": pid, "name": name})
    return pid


def remove_person(
    conn: sqlite3.Connection, person_id: str, actor: str, clock: Clock | None = None
) -> None:
    """Remove a person the expert added, with their undecided and rejected links. Refused for a
    phone owner (withdraw the stipulation instead) and for a person with a confirmed link
    (reject it first), so nothing an expert confirmed disappears silently."""
    _expert(actor)
    row = conn.execute("SELECT name FROM persons WHERE id = ?", (person_id,)).fetchone()
    if row is None:
        raise ReviewError(f"no person {person_id}")
    if conn.execute("SELECT 1 FROM stipulations WHERE person_id = ?", (person_id,)).fetchone():
        raise ReviewError("this person is a phone owner; change the stipulation instead")
    if conn.execute(
        "SELECT 1 FROM identity_links WHERE person_id = ? AND status = 'confirmed'", (person_id,)
    ).fetchone():
        raise ReviewError("reject this person's confirmed links first")
    now = _now(clock)
    with conn:
        gone = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM identity_links WHERE person_id = ? ORDER BY id", (person_id,)
            )
        ]
        conn.execute("DELETE FROM identity_links WHERE person_id = ?", (person_id,))
        conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
        audit_log.append(
            conn,
            now,
            actor,
            "person.remove",
            {"person_id": person_id, "name": row[0], "links_removed": gone},
        )


def stipulate_device_owner(
    conn: sqlite3.Connection,
    device_id: str,
    person_name: str,
    actor: str,
    clock: Clock | None = None,
) -> str:
    """The expert stipulates who used a device. Returns the stipulation id.

    This is a case-level statement the expert makes, not a finding: Mabillon never verifies it.
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


def name_device(
    conn: sqlite3.Connection,
    device_id: str,
    names: list[str],
    actor: str,
    clock: Clock | None = None,
) -> list[str]:
    """The expert records the names the government document uses for a device ("TARGET
    PHONE", "Item 1"), so the assumption filler can tell which phone a claim names. The list
    replaces the device's earlier names; an empty list clears them. It is the expert's
    statement, not a finding: the report lists each name with who gave it and when. Refused
    when a name would also match another device, so a phone name never reaches two devices.
    Returns the names as recorded."""
    from core.review.device_names import ACTION, logged_names, name_key

    _expert(actor)
    dev = conn.execute("SELECT label FROM devices WHERE id = ?", (device_id,)).fetchone()
    if dev is None:
        raise ReviewError(f"no device {device_id}")
    clean: list[str] = []
    for raw in names:
        name = " ".join(raw.split())
        if not name or len(name) > 80:
            raise ReviewError("enter each name as the document writes it (up to 80 characters)")
        if name_key(name) not in {name_key(n) for n in clean}:
            clean.append(name)
    taken = logged_names(conn)
    for did, sid, label in conn.execute("SELECT id, source_id, label FROM devices ORDER BY id"):
        if did == device_id:
            continue
        theirs = {name_key(x) for x in (did, sid, label, *taken.get(did, [])) if x}
        for name in clean:
            if name_key(name) in theirs:
                raise ReviewError(f"{name} already names {label} ({did})")
    now = _now(clock)
    with conn:
        audit_log.append(
            conn, now, actor, ACTION, {"device_id": device_id, "label": dev[0], "names": clean}
        )
    return clean

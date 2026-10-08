"""`baker claims propose`: the local model proposes claims, the expert edits the list.

Proposals go in as status 'proposed' with the model run that made them. Nothing here accepts
a claim: the expert accepts, edits or removes each one (core/review/actions.py). A paragraph
that already has a claim of any status (the expert's own, or an earlier proposal, even a
removed one) is skipped, so proposing again never duplicates or revives a claim.

Everything is stored in one transaction: the ModelRun, every model call (kept or dropped),
the proposed claims and one audit-log entry naming them and the drops.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from core.claims.extract import ClaimDrop, LocalClaimExtractor
from core.contracts import Claim, ClaimStatus, GovDocParagraph, canonical_json
from core.review import audit_log

PROPOSE_ACTION = "claims.proposed"
PROPOSER = "system:claim-extractor"

Clock = Callable[[], datetime]


@dataclass
class ProposeResult:
    model_run_id: str | None
    claims: list[Claim] = field(default_factory=list)
    drops: list[ClaimDrop] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # paragraphs that already had claims


def load_paragraphs(
    conn: sqlite3.Connection, ids: Sequence[str] | None = None
) -> list[GovDocParagraph]:
    """Every government-document paragraph in document order, or just `ids`."""
    rows = conn.execute(
        "SELECT id, govdoc_id, page, para_no, label, char_start, char_end, text, ocr"
        " FROM govdoc_paragraphs ORDER BY govdoc_id, para_no"
    ).fetchall()
    paras = [
        GovDocParagraph(
            id=r[0],
            govdoc_id=r[1],
            page=r[2],
            para_no=r[3],
            label=r[4],
            char_start=r[5],
            char_end=r[6],
            text=r[7],
            ocr=bool(r[8]),
        )
        for r in rows
    ]
    if ids is None:
        return paras
    known = {p.id for p in paras}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ValueError(f"no such paragraph: {', '.join(unknown)}")
    wanted = set(ids)
    return [p for p in paras if p.id in wanted]


def _has_claims(conn: sqlite3.Connection, paragraph_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM claims WHERE paragraph_id = ? LIMIT 1", (paragraph_id,))
    return row.fetchone() is not None


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def propose_claims(
    conn: sqlite3.Connection,
    extractor: LocalClaimExtractor,
    paragraphs: Sequence[GovDocParagraph],
    clock: Clock | None = None,
) -> ProposeResult:
    """Run the extractor on each paragraph that has no claims yet and store what it proposes."""
    now = (clock or (lambda: datetime.now(UTC)))()
    runs = getattr(extractor, "model_runs", ())
    result = ProposeResult(model_run_id=runs[0].id if runs else None)
    todo: list[GovDocParagraph] = []
    for p in paragraphs:
        if _has_claims(conn, p.id):
            result.skipped.append(p.id)
        else:
            todo.append(p)
    before = len(extractor.drops)
    for p in todo:
        result.claims.extend(extractor.extract_paragraph(p))
    result.drops = extractor.drops[before:]

    with conn:
        for m in runs:
            conn.execute(
                "INSERT OR IGNORE INTO model_runs (id, pipeline_run_id, purpose, model_name,"
                " model_sha256, prompt_version, prompt_sha256, params_json, seed,"
                " started_at_utc) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    m.id,
                    m.purpose,
                    m.model_name,
                    m.model_sha256,
                    m.prompt_version,
                    m.prompt_sha256,
                    canonical_json(m.params),
                    m.seed,
                    _iso(m.started_at_utc),
                ),
            )
        for call in extractor.recorder.calls:
            conn.execute(
                "INSERT OR IGNORE INTO model_calls (id, model_run_id, seq, subject_json, prompt,"
                " raw_output, outcome, error, at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    call.id,
                    call.model_run_id,
                    call.seq,
                    canonical_json(list(call.subject_ids)),
                    call.prompt,
                    call.raw_output,
                    call.outcome.value,
                    call.error,
                    _iso(call.at_utc),
                ),
            )
        for c in result.claims:
            if c.status != ClaimStatus.PROPOSED:
                raise ValueError(f"{c.id}: an extractor only proposes claims")
            conn.execute(
                "INSERT INTO claims (id, paragraph_id, text, claim_type, status, model_run_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (c.id, c.paragraph_id, c.text, c.claim_type.value, c.status.value, c.model_run_id),
            )
        audit_log.append(
            conn,
            now,
            PROPOSER,
            PROPOSE_ACTION,
            {
                "model_run_id": result.model_run_id,
                "claims": [c.id for c in result.claims],
                "paragraphs": [p.id for p in todo],
                "skipped_paragraphs": result.skipped,
                "drops": [
                    {"paragraph_id": d.paragraph_id, "index": d.index, "reason": d.reason}
                    for d in result.drops
                ],
            },
        )
    return result

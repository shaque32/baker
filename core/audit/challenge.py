"""The challenge step: code looks for what undercuts a claim close to SUPPORTED. No model of its
own. On by default (`Components.challenge`); `mabillon audit --no-challenge` and the review
screen's "Skip the challenge step" turn it off for one run, and the run's configuration says so.

For a claim whose every core assumption has a passing check or a "supports" label, the step
runs the counter-searches code already has for that claim (core/hypotheses/explain.py: someone
else using the account or phone, another clock, the day boundary, another app, a whole app gone
quiet, a curated report, the same words elsewhere). Each search is a fixed query, not a model's
choice. The records it finds go to the same stance labeler and the same quote check as any
retrieved record, against the assumptions the search is tied to: at most the explain.MAX_FITS
records a search shows; the rest are counted in its total, not labelled.

It can only add doubt. Only a "contradicts" or "complicates" label is stored; a "supports" or
"irrelevant" label from this step is discarded and counted, so the step can never put support in
front of the expert. invariants.check_challenge fails the run if any item it stored says
otherwise. A stored item is an ordinary evidence item: under rules 0.3.0 an open complicating or
contradicting item blocks SUPPORTED until the expert dismisses it, and none decides a verdict on
its own.

Each search is written to the audit log as its own `challenge.query` entry (what was searched,
the records found, what was stored), and `mabillon verify-bundle` runs the same searches again on
the bundle's tables, with no model, and compares the records.

"Nothing found" never means "did not happen": an entry with no records still says what was
searched, in explain.py's words (explain.alternatives with keep_empty), and a claim no search
applies to gets one entry saying nothing was searched.

Whether the claim is close to SUPPORTED is read from labels, never from review status, so the
second pass after an expert's review (eval/simulated_expert.py) asks the same searches.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from core.audit.context import DEFAULT_WINDOW, context_ids
from core.contracts import (
    Assumption,
    CheckOutcome,
    CheckResult,
    EvidenceCandidate,
    EvidenceItem,
    ProvenanceTier,
    Stance,
)
from core.enrich.records import get_record, kind_of
from core.hypotheses import explain

VERSION = "1.0.0"
QUERY_ACTION = "challenge.query"
DOUBT = frozenset({Stance.CONTRADICTS, Stance.COMPLICATES})
LABELABLE = frozenset({"message", "call", "contact"})  # records the stance labeler reads
FOUND_MARK = "found by the challenge step"
NO_SEARCH = (
    "No counter-search in core/hypotheses/explain.py applies to this claim's assumptions, so "
    "nothing was searched."
)


@dataclass(frozen=True)
class Query:
    """One counter-search for one claim: explain.py's alternative, as fixed by code."""

    kind: str
    assumption_ids: tuple[str, ...]
    searched: str
    record_ids: tuple[str, ...]  # the records the search found that a labeler can read
    total: int  # everything the alternative found, shown or not (explain.MAX_FITS)

    def payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "assumption_ids": list(self.assumption_ids),
            "searched": self.searched,
            "record_ids": list(self.record_ids),
            "total": self.total,
        }


def near_supported(
    assumptions: Sequence[Assumption], checks: Iterable[CheckResult], items: Iterable[EvidenceItem]
) -> bool:
    """Every core assumption has a passing check or a "supports" label, whatever its review."""
    core = [a.id for a in assumptions if a.is_core]
    if not core:
        return False
    passed = {r.assumption_id for r in checks if r.outcome is CheckOutcome.PASS}
    supported = {e.assumption_id for e in items if e.stance is Stance.SUPPORTS}
    return all(aid in passed or aid in supported for aid in core)


def queries(case: explain.Case, assumptions: Sequence[Assumption]) -> list[Query]:
    """The counter-searches for one claim, in explain.py's fixed order."""
    core = tuple(a.id for a in assumptions if a.is_core)
    known = {a.id for a in assumptions}
    out = []
    for alt in explain.alternatives(case, list(assumptions), keep_empty=True):
        aids = tuple(a for a in alt.assumption_ids if a in known) or core
        rids = tuple(
            dict.fromkeys(f.record_id for f in alt.fits if kind_of(f.record_id) in LABELABLE)
        )
        out.append(Query(alt.kind, aids, alt.searched, rids, alt.total))
    if not out:  # still logged, so a challenged claim never reads as one nothing was asked of
        out.append(Query("none", core, NO_SEARCH, (), 0))
    return out


def candidate(conn: sqlite3.Connection, record_id: str) -> EvidenceCandidate | None:
    """The record as the retriever would hand it to the labeler, with its surrounding messages."""
    rec = get_record(conn, record_id)
    if rec is None or not rec.text:
        return None
    return EvidenceCandidate(
        record_id=record_id,
        ref=rec.ref,
        text=rec.text,
        tier=ProvenanceTier.OBSERVED,
        context_ids=context_ids(conn, record_id, DEFAULT_WINDOW),
        retrieval_score=0.0,
    )


def keep(item: EvidenceItem) -> bool:
    """Only doubt is stored from this step."""
    return item.stance in DOUBT


def found_items(conn: sqlite3.Connection) -> frozenset[str]:
    """The evidence ids the step stored, read from its own audit entries. The report and the
    review screen mark each one as found by the challenge step."""
    rows = conn.execute("SELECT payload_json FROM audit_log WHERE action = ?", (QUERY_ACTION,))
    return frozenset(i for (payload,) in rows for i in json.loads(payload).get("stored", ()))

"""Stand-in components for the pipeline skeleton. Eval only; never used by the product.

They let the pipeline, invariants, report and eval run end to end before the real modules
land. They are deliberately simple and their numbers mean nothing. Any run that uses one is
marked fake (their module is under eval/), and the report says so in a banner.

- FakeAssumptionBuilder: one core assumption per claim, tier inferred, carrying the first
  phrase the claim puts in quotes as params.quoted_text.
- QuotedPhraseRetriever: messages and contacts whose text contains that phrase.
- PhraseLabeler: 'supports' when the record contains the phrase, else 'irrelevant'.
- FakeReviewer: accepts (or dismisses) every supporting item it is shown.
- InconclusiveCheck: searches nothing and says so.
- exact_substring: the strict quote check (the real one is core/audit/quotes.py).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime

from core.audit.invariants import record_text
from core.contracts import (
    Assumption,
    AssumptionKind,
    AssumptionParams,
    CheckOutcome,
    CheckResult,
    Claim,
    ClaimType,
    EvidenceCandidate,
    EvidenceItem,
    EvidenceStatus,
    ModelRun,
    ProvenanceTier,
    ReviewDecision,
    ReviewerKind,
    SourceRef,
    Stance,
    StanceLabel,
    assumption_id,
    check_id,
    review_id,
)

FAKE_TIME = datetime(2026, 10, 7, tzinfo=UTC)


def _run(purpose: str) -> ModelRun:
    return ModelRun(
        id=f"mr:fake-{purpose}",
        purpose=purpose,
        model_name=f"fake-{purpose}",
        model_sha256="0" * 64,
        prompt_version="none",
        params={"stand_in": True},
        seed=0,
        started_at_utc=FAKE_TIME,
    )


FAKE_STANCE_RUN = _run("stance")
FAKE_REVIEW_RUN = _run("review")

KIND_FOR_TYPE = {
    ClaimType.COMMUNICATION: AssumptionKind.EVENT,
    ClaimType.IDENTITY: AssumptionKind.IDENTITY,
    ClaimType.TIMING: AssumptionKind.TIME,
    ClaimType.CONTENT_MEANING: AssumptionKind.MEANING,
    ClaimType.COUNT: AssumptionKind.COMPLETENESS,
    ClaimType.ABSENCE: AssumptionKind.COMPLETENESS,
    ClaimType.ROLE: AssumptionKind.MEANING,
    ClaimType.EVENT: AssumptionKind.EVENT,
}

_QUOTED = re.compile(r'"([^"]{2,})"')


def exact_substring(quote: str, record_text: str) -> bool:
    return bool(quote.strip()) and quote in record_text


class FakeAssumptionBuilder:
    def build(self, claim: Claim) -> list[Assumption]:
        phrases = _QUOTED.findall(claim.text)
        params = AssumptionParams(quoted_text=phrases[0] if phrases else None)
        return [
            Assumption(
                id=assumption_id(claim.id, "stand_in", params),
                claim_id=claim.id,
                kind=KIND_FOR_TYPE[claim.claim_type],
                template_id="stand_in",
                template_version="0",
                params=params,
                text=f"Stand-in assumption for {claim.id}: a record contains the quoted words.",
                is_core=True,
                tier=ProvenanceTier.INFERRED,
            )
        ]


class QuotedPhraseRetriever:
    def retrieve(
        self, assumption: Assumption, conn: sqlite3.Connection, k: int
    ) -> list[EvidenceCandidate]:
        phrase = assumption.params.quoted_text
        if not phrase:
            return []
        rows = conn.execute(
            "SELECT id, source_id, locator FROM messages"
            " WHERE instr(lower(body), lower(?)) > 0 ORDER BY id LIMIT ?",
            (phrase, k),
        ).fetchall()
        rows += conn.execute(
            "SELECT id, source_id, locator FROM contacts"
            " WHERE instr(lower(name), lower(?)) > 0 ORDER BY id LIMIT ?",
            (phrase, k),
        ).fetchall()
        return [
            EvidenceCandidate(
                record_id=rid,
                ref=SourceRef(source_id=sid, locator=loc),
                text=record_text(conn, rid) or "",
                tier=ProvenanceTier.OBSERVED,
                retrieval_score=1.0,
            )
            for rid, sid, loc in rows[:k]
        ]


class PhraseLabeler:
    def label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceLabel:
        phrase = assumption.params.quoted_text or ""
        i = candidate.text.lower().find(phrase.lower()) if phrase else -1
        if i >= 0:
            return StanceLabel(
                assumption_id=assumption.id,
                record_id=candidate.record_id,
                stance=Stance.SUPPORTS,
                quote=candidate.text[i : i + len(phrase)],
                rationale="Stand-in label: the record contains the quoted words.",
                model_run_id=FAKE_STANCE_RUN.id,
            )
        return StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=Stance.IRRELEVANT,
            quote=candidate.text[:30],
            rationale="Stand-in label: no quoted words found.",
            model_run_id=FAKE_STANCE_RUN.id,
        )


class FakeReviewer:
    model_run_id = FAKE_REVIEW_RUN.id

    def __init__(self, accept: bool = True) -> None:
        self.accept = accept

    def review(self, assumption: Assumption, item: EvidenceItem, context: str) -> ReviewDecision:
        return ReviewDecision(
            id=review_id(item.id, 1),
            evidence_id=item.id,
            seq=1,
            reviewer_kind=ReviewerKind.AI,
            reviewer="ai:fake-review",
            status=EvidenceStatus.AI_ACCEPTED if self.accept else EvidenceStatus.DISMISSED,
            reason="Stand-in reviewer: "
            + ("accepts every item." if self.accept else "dismisses every item."),
            model_run_id=FAKE_REVIEW_RUN.id,
            decided_at_utc=FAKE_TIME,
        )


class InconclusiveCheck:
    name = "stand_in"
    version = "0"

    def run(self, assumption: Assumption, conn: sqlite3.Connection) -> CheckResult:
        return CheckResult(
            id=check_id(assumption.id, self.name, self.version),
            assumption_id=assumption.id,
            check_name=self.name,
            check_version=self.version,
            outcome=CheckOutcome.INCONCLUSIVE,
            searched="Nothing. This is a stand-in check.",
            detail="No check ran.",
        )


def record_context(conn: sqlite3.Connection, assumption: Assumption, item: EvidenceItem) -> str:
    return record_text(conn, item.record_id) or ""


def fake_components(accept: bool = True):  # -> core.pipeline.Components
    from core.pipeline import Components

    return Components(
        assumptions=FakeAssumptionBuilder(),
        retriever=QuotedPhraseRetriever(),
        labeler=PhraseLabeler(),
        verify_quote=exact_substring,
        reviewer=FakeReviewer(accept),
        context=record_context,
        checks=(InconclusiveCheck(),),
        model_runs=(FAKE_STANCE_RUN, FAKE_REVIEW_RUN),
    )

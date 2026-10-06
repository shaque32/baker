"""Baker contracts. HUMAN-OWNED and FROZEN.

Data models and function signatures every module builds against.
Agents: never edit this file. Propose changes in PROPOSED_CHANGES.md.

Enum values must match the CHECK constraints in core/schema.sql (tests enforce this).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------- enums


class ProvenanceTier(StrEnum):
    OBSERVED = "observed"  # directly present in the source
    DERIVED = "derived"  # computed deterministically from observed data
    INFERRED = "inferred"  # produced by a model; always shown with uncertainty
    CONFIRMED = "confirmed"  # an expert explicitly accepted it (logged)


class Verdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNPROVEN = "unproven"


class Stance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    COMPLICATES = "complicates"
    IRRELEVANT = "irrelevant"


class ClaimType(StrEnum):
    COMMUNICATION = "communication"
    IDENTITY = "identity"
    TIMING = "timing"
    CONTENT_MEANING = "content_meaning"
    COUNT = "count"
    ABSENCE = "absence"
    ROLE = "role"
    EVENT = "event"


class AssumptionKind(StrEnum):
    IDENTITY = "identity"
    TIME = "time"
    MEANING = "meaning"
    COMPLETENESS = "completeness"
    EVENT = "event"


class SourceKind(StrEnum):
    UFDR = "ufdr"
    CELLEBRITE_EXCEL = "cellebrite_excel"
    CELLEBRITE_PDF = "cellebrite_pdf"
    CELLEBRITE_HTML = "cellebrite_html"
    AXIOM = "axiom"
    RAW_ZIP = "raw_zip"
    GOVDOC = "govdoc"
    SYNTHETIC = "synthetic"


class Fidelity(StrEnum):
    FULL_EXTRACTION = "full_extraction"
    CURATED_REPORT = "curated_report"  # examiner-filtered; cannot support absence claims
    UNKNOWN = "unknown"


class ExtractionType(StrEnum):
    LOGICAL = "logical"
    FILE_SYSTEM = "file_system"
    PHYSICAL = "physical"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class IdentityLinkStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class ClaimStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REMOVED = "removed"


class EvidenceStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class CheckOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class MessageDirection(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    UNKNOWN = "unknown"


class CallDirection(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    MISSED = "missed"
    UNKNOWN = "unknown"


class DocKind(StrEnum):
    AFFIDAVIT = "affidavit"
    POLICE_REPORT = "police_report"
    FORENSIC_REPORT = "forensic_report"
    OTHER = "other"


# ---------------------------------------------------------------- base


class Model(BaseModel):
    """Immutable, strict base for every contract model."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceRef(Model):
    """Pointer back to the original artifact.

    locator meaning depends on the source kind: an XML path for UFDR,
    'sheet!row' for Excel, 'page:para' for PDF.
    """

    source_id: str
    locator: str


class Timestamp(Model):
    """A time as the source gave it, normalized to UTC."""

    utc: datetime | None  # timezone-aware UTC; None if the source had no usable time
    offset_min: int | None  # original UTC offset in minutes; None if the source did not say
    raw: str | None  # the value exactly as it appeared in the source

    @model_validator(mode="after")
    def _utc_is_aware(self) -> Timestamp:
        if self.utc is not None and self.utc.utcoffset() is None:
            raise ValueError("utc must be timezone-aware")
        return self


# ---------------------------------------------------------------- inputs and evidence


class Source(Model):
    id: str
    kind: SourceKind
    fidelity: Fidelity
    extraction_type: ExtractionType
    file_name: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_name: str | None = None
    tool_version: str | None = None
    extracted_at_utc: datetime | None = None
    imported_at_utc: datetime


class Message(Model):
    id: str
    ref: SourceRef
    thread_id: str
    sender_account_id: str | None
    recipient_account_ids: tuple[str, ...] = ()
    direction: MessageDirection
    ts: Timestamp
    body: str  # original text; the only citable text
    lang: str | None = None
    deleted_flag: bool | None = None  # None = source did not say
    bookmarked: bool | None = None


class IdentityLink(Model):
    id: str
    account_id: str
    person_id: str
    status: IdentityLinkStatus
    tier: ProvenanceTier
    basis: str
    decided_by: str | None = None
    decided_at_utc: datetime | None = None


# ---------------------------------------------------------------- government document


class GovDoc(Model):
    id: str
    source_id: str
    title: str
    doc_kind: DocKind


class GovDocParagraph(Model):
    id: str
    govdoc_id: str
    page: int = Field(ge=1)
    para_no: int = Field(ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    text: str


# ---------------------------------------------------------------- audit


class Claim(Model):
    id: str
    paragraph_id: str
    text: str
    claim_type: ClaimType
    status: ClaimStatus
    model_run_id: str | None = None  # None when the expert wrote it


class Assumption(Model):
    id: str
    claim_id: str
    kind: AssumptionKind
    text: str
    is_core: bool
    tier: ProvenanceTier


class EvidenceCandidate(Model):
    """A retrieved record, before any model has looked at it."""

    record_id: str
    ref: SourceRef
    text: str
    tier: ProvenanceTier
    context_ids: tuple[str, ...] = ()  # surrounding messages shown to the labeler
    retrieval_score: float


class StanceLabel(Model):
    """Raw model output. Untrusted until verify_quote passes."""

    assumption_id: str
    record_id: str
    stance: Stance
    quote: str
    rationale: str
    model_run_id: str


class EvidenceItem(Model):
    """A stance label whose quote was verified verbatim against the record."""

    id: str
    assumption_id: str
    record_id: str
    ref: SourceRef
    stance: Stance
    quote: str
    quote_verified: Literal[True]
    rationale: str
    tier: ProvenanceTier
    status: EvidenceStatus
    model_run_id: str | None


class CheckResult(Model):
    id: str
    assumption_id: str
    check_name: str
    check_version: str
    outcome: CheckOutcome
    detail: str


class VerdictDecision(Model):
    claim_id: str
    verdict: Verdict
    rule_version: str
    reasons: tuple[str, ...]  # human-readable, one per rule that fired
    decided_at_utc: datetime
    confirmed_by: str | None = None
    override_note: str | None = None


class ModelRun(Model):
    id: str
    purpose: str
    model_name: str
    model_sha256: str
    prompt_version: str
    params: dict[str, str | int | float | bool]
    seed: int | None
    started_at_utc: datetime


class AuditLogEntry(Model):
    seq: int = Field(ge=1)
    at_utc: datetime
    actor: str
    action: str
    payload_json: str
    prev_hash: str
    hash: str


# ---------------------------------------------------------------- eval


class GoldClaim(Model):
    """One line of eval/gold/<case>/gold.jsonl. Written and signed off by a human."""

    claim_id: str
    page: int = Field(ge=1)
    para_no: int = Field(ge=1)
    text: str
    claim_type: ClaimType
    cross_device: bool
    gold_verdict: Verdict
    core_assumptions: tuple[str, ...]
    key_evidence: tuple[str, ...]  # stable record ids, e.g. 'msg:src1:00412'
    trap: str | None  # which planted trap this claim tests, if any
    rationale: str
    labeled_by: str
    labeled_at: datetime


class Prediction(Model):
    """One line of a pipeline predictions.jsonl, scored by eval/run_eval.py."""

    claim_id: str
    verdict: Verdict
    cited_record_ids: tuple[str, ...] = ()


# ---------------------------------------------------------------- function signatures
# Implementations live in the modules named in docs/ARCHITECTURE.md.


class EvidenceImporter(Protocol):
    """core/ingest/<format>.py. Streams the input, writes canonical rows, returns the Source."""

    def import_source(self, path: Path, conn: sqlite3.Connection) -> Source: ...


class GovDocIngester(Protocol):
    """core/ingest/govdoc.py. PDF -> paragraphs with page, para_no and char span."""

    def ingest(
        self, path: Path, conn: sqlite3.Connection
    ) -> tuple[GovDoc, list[GovDocParagraph]]: ...


class ClaimExtractor(Protocol):
    """core/claims/. Proposes atomic claims; the expert edits the list."""

    def extract(self, paragraphs: list[GovDocParagraph]) -> list[Claim]: ...


class AssumptionBuilder(Protocol):
    """core/audit/assumptions.py. Fills the fixed template for the claim type."""

    def build(self, claim: Claim) -> list[Assumption]: ...


class Retriever(Protocol):
    """core/audit/retrieval.py. Structured + keyword + semantic, reranked."""

    def retrieve(
        self, assumption: Assumption, conn: sqlite3.Connection, k: int
    ) -> list[EvidenceCandidate]: ...


class StanceLabeler(Protocol):
    """core/audit/stance.py. One label per (assumption, candidate). Never a verdict."""

    def label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceLabel: ...


class QuoteVerifier(Protocol):
    """core/audit/quotes.py. True only if quote appears verbatim in the record's original text."""

    def __call__(self, quote: str, record_text: str) -> bool: ...


class DeterministicCheck(Protocol):
    """core/audit/checks/. Sender, timestamp and timezone, counts, absence vs coverage."""

    name: str
    version: str

    def run(self, assumption: Assumption, conn: sqlite3.Connection) -> CheckResult: ...


class VerdictRule(Protocol):
    """core/audit/rules.py (human-owned). The only thing that sets a verdict."""

    def __call__(
        self,
        claim: Claim,
        assumptions: list[Assumption],
        evidence: list[EvidenceItem],
        checks: list[CheckResult],
    ) -> VerdictDecision: ...

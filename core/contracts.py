"""Baker contracts. HUMAN-OWNED and FROZEN.

Data models and function signatures every module builds against.
Agents: never edit this file. Propose changes in PROPOSED_CHANGES.md.

Enum values must match the CHECK constraints in core/schema.sql (tests enforce this).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Bump on every change to this file or core/schema.sql. pipeline_runs records it.
CONTRACTS_VERSION = "0.2.0"

# ---------------------------------------------------------------- enums


class ProvenanceTier(StrEnum):
    OBSERVED = "observed"  # directly present in the source
    DERIVED = "derived"  # computed deterministically from observed data
    INFERRED = "inferred"  # produced by a model; always shown with uncertainty
    AI_REVIEWED = "ai_reviewed"  # accepted by the local AI reviewer; never shown as confirmed
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
    AI_ACCEPTED = "ai_accepted"  # local AI reviewer accepted; a human decision overrides it
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class ReviewerKind(StrEnum):
    AI = "ai"  # the local AI reviewer (core/audit/review.py)
    EXPERT = "expert"  # a human expert


class SupportedBasis(StrEnum):
    """What a SUPPORTED verdict rests on. Reports show the two differently."""

    AI_REVIEWED = "ai_reviewed"  # at least one supporting item is only AI-accepted
    CONFIRMED = "confirmed"  # every supporting item it cites was accepted by an expert


class StipulationKind(StrEnum):
    DEVICE_OWNER = "device_owner"  # "Item 1 is PETROV's phone"


class StipulationStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ModelCallOutcome(StrEnum):
    OK = "ok"  # parsed and used
    INVALID_OUTPUT = "invalid_output"  # not valid JSON or failed the output schema; dropped
    QUOTE_FAILED = "quote_failed"  # quote not found verbatim in the record; dropped
    ERROR = "error"  # runtime error or timeout; a reviewer error counts as a dismissal


class PipelineRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"  # includes an invariant stop


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


def _aware(dt: datetime | None, name: str) -> None:
    if dt is not None and dt.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


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
        _aware(self.utc, "utc")
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
    sender_raw: str | None = None  # sender text exactly as the source showed it
    recipient_account_ids: tuple[str, ...] = ()
    direction: MessageDirection
    ts: Timestamp
    body: str  # original text; the only citable text
    lang: str | None = None
    deleted_flag: bool | None = None  # None = source did not say
    bookmarked: bool | None = None


class SourceCoverage(Model):
    """What one import covered. Absence checks read this; one row per source."""

    source_id: str
    importer: str  # 'cellebrite_excel', 'cellebrite_pdf', ...
    importer_version: str
    payload: dict[str, object]  # tables read, rows skipped, unknown columns, time-zone
    #                             handling, deleted-flag coverage, notes


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
    para_no: int = Field(ge=1)  # position in the document, counting from 1
    label: str | None = None  # paragraph number as printed ("7"); None if unnumbered
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    text: str
    ocr: bool = False  # text came from OCR, not the PDF text layer; not verbatim


# ---------------------------------------------------------------- audit


class Claim(Model):
    id: str
    paragraph_id: str
    text: str
    claim_type: ClaimType
    status: ClaimStatus
    model_run_id: str | None = None  # None when the expert wrote it


class TimeWindow(Model):
    """A time range a claim states, resolved to UTC. Both ends inclusive."""

    start_utc: datetime
    end_utc: datetime
    tz: str  # IANA zone used to resolve the stated dates, e.g. 'America/New_York'
    raw: str  # the range as the government document wrote it, e.g. 'March 20 to 23'

    @model_validator(mode="after")
    def _ordered_and_aware(self) -> TimeWindow:
        _aware(self.start_utc, "start_utc")
        _aware(self.end_utc, "end_utc")
        if self.end_utc < self.start_utc:
            raise ValueError("end_utc is before start_utc")
        return self


class AssumptionParams(Model):
    """Typed parameters of an assumption. Checks read these, never the free text.

    Which fields a template needs is fixed by the template (core/audit/assumptions.py).
    A field left empty means the claim did not state it, not "any".
    """

    account_ids: tuple[str, ...] = ()  # accounts.id
    person_ids: tuple[str, ...] = ()  # persons.id
    device_ids: tuple[str, ...] = ()  # devices.id
    # handles or display names exactly as the document writes them ('@northstar'); checks
    # resolve them to accounts from the data, so the template filler never decides that
    handles: tuple[str, ...] = ()
    window: TimeWindow | None = None
    expected_count: int | None = Field(default=None, ge=0)
    count_op: Literal["eq", "ge", "le"] | None = None  # how expected_count is compared
    # inclusive range a call's duration must fall in, e.g. (90, 150) for "about two minutes"
    duration_s: tuple[int, int] | None = None
    channels: tuple[str, ...] = ()  # apps as spelled in accounts.app / threads.app, 'sms', 'call'
    quoted_text: str | None = None  # words the document attributes to the evidence

    @model_validator(mode="after")
    def _count_pair(self) -> AssumptionParams:
        if (self.expected_count is None) != (self.count_op is None):
            raise ValueError("expected_count and count_op go together")
        if self.duration_s is not None:
            lo, hi = self.duration_s
            if lo < 0 or hi < lo:
                raise ValueError("duration_s is (min, max) seconds with 0 <= min <= max")
        return self


class Assumption(Model):
    id: str  # assumption_id(claim_id, template_id, params)
    claim_id: str
    kind: AssumptionKind
    template_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    template_version: str
    params: AssumptionParams
    text: str  # human-readable rendering of the template; never parsed
    is_core: bool
    tier: ProvenanceTier  # tier at creation; never raised later (coverage is computed in rules)


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
    model_call_id: str | None = None  # the model_calls row holding the raw output


RECORD_TIERS = frozenset({ProvenanceTier.OBSERVED, ProvenanceTier.DERIVED, ProvenanceTier.INFERRED})


class EvidenceItem(Model):
    """A stance label whose quote was verified verbatim against the record.

    tier is the tier of the record (observed, derived or inferred) and never changes.
    status is the latest row in evidence_reviews ('open' if none). The displayed tier
    comes from display_tier(), never from tier alone.
    """

    id: str  # evidence_id(assumption_id, record_id, stance, quote)
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

    @model_validator(mode="after")
    def _record_tier(self) -> EvidenceItem:
        if self.tier not in RECORD_TIERS:
            raise ValueError("evidence tier is the record's tier: observed, derived or inferred")
        return self


def display_tier(item: EvidenceItem) -> ProvenanceTier:
    """The tier a report shows for an evidence item. The one place this mapping lives."""
    if item.status is EvidenceStatus.ACCEPTED:
        return ProvenanceTier.CONFIRMED
    if item.status is EvidenceStatus.AI_ACCEPTED:
        return ProvenanceTier.AI_REVIEWED
    return item.tier


class ReviewDecision(Model):
    """One review of one evidence item. Append-only: a human override is a new row.

    The latest row for an evidence item sets EvidenceItem.status.
    """

    id: str  # review_id(evidence_id, seq)
    evidence_id: str
    seq: int = Field(ge=1)  # 1 for the first review of this item, then 2, 3, ...
    reviewer_kind: ReviewerKind
    reviewer: str  # 'ai:<model_name>' or 'expert:<name>'
    status: EvidenceStatus
    reason: str = Field(min_length=1)  # one sentence; shown in the report
    model_run_id: str | None  # required for AI, None for an expert
    model_call_id: str | None = None
    decided_at_utc: datetime

    @model_validator(mode="after")
    def _who_may_set_what(self) -> ReviewDecision:
        _aware(self.decided_at_utc, "decided_at_utc")
        if self.reviewer_kind is ReviewerKind.AI:
            if self.status not in (EvidenceStatus.AI_ACCEPTED, EvidenceStatus.DISMISSED):
                raise ValueError("the AI reviewer sets only ai_accepted or dismissed")
            if self.model_run_id is None or not self.reviewer.startswith("ai:"):
                raise ValueError("an AI review needs a model_run_id and an 'ai:' reviewer")
        else:
            if self.status not in (
                EvidenceStatus.ACCEPTED,
                EvidenceStatus.DISMISSED,
                EvidenceStatus.OPEN,
            ):
                raise ValueError("an expert sets accepted, dismissed or open (to undo)")
            if self.model_run_id is not None or not self.reviewer.startswith("expert:"):
                raise ValueError("an expert review has no model_run_id and an 'expert:' reviewer")
        return self


class CheckResult(Model):
    id: str  # check_id(assumption_id, check_name, check_version)
    assumption_id: str
    check_name: str
    check_version: str
    outcome: CheckOutcome
    searched: str  # what was searched (accounts, window, query) and the sources' coverage
    record_ids: tuple[str, ...] = ()  # records the outcome rests on; rules.py cites them
    source_ids: tuple[str, ...] = ()  # sources searched; absence findings name them
    detail: str


class Stipulation(Model):
    """A case-level fact the expert confirms once, e.g. who owns each phone.

    Confirmed stipulations count at tier confirmed in rules.py, and every report lists
    each one as a limitation ("this audit takes as given that ...").
    """

    id: str  # stipulation_id(kind, subject_id)
    kind: StipulationKind
    subject_id: str  # devices.id for device_owner
    person_id: str  # persons.id
    statement: str  # as the report prints it
    status: StipulationStatus
    decided_by: str | None = None  # 'expert:<name>'; required once confirmed or rejected
    decided_at_utc: datetime | None = None

    @model_validator(mode="after")
    def _expert_decides(self) -> Stipulation:
        _aware(self.decided_at_utc, "decided_at_utc")
        if self.status is not StipulationStatus.PROPOSED and not (
            self.decided_by
            and self.decided_by.startswith("expert:")
            and self.decided_at_utc is not None
        ):
            raise ValueError("only an expert confirms or rejects a stipulation, with a time")
        return self


class AssumptionCoverage(Model):
    """rules.py's finding for one core assumption. Computed per verdict; never stored back."""

    assumption_id: str
    covered: bool
    tier: ProvenanceTier | None  # the tier coverage rests on; None if not covered
    cited_ids: tuple[str, ...] = ()  # check, evidence and stipulation ids relied on


class VerdictDecision(Model):
    id: str  # verdict_id(claim_id, pipeline_run_id)
    claim_id: str
    pipeline_run_id: str
    verdict: Verdict
    supported_basis: SupportedBasis | None = None  # set iff verdict is SUPPORTED
    rule_version: str
    reasons: tuple[str, ...]  # human-readable, one per rule that fired
    coverage: tuple[AssumptionCoverage, ...] = ()  # one per core assumption
    cited_evidence_ids: tuple[str, ...] = ()
    cited_check_ids: tuple[str, ...] = ()
    cited_stipulation_ids: tuple[str, ...] = ()
    decided_at_utc: datetime
    confirmed_by: str | None = None
    override_note: str | None = None

    @model_validator(mode="after")
    def _basis_iff_supported(self) -> VerdictDecision:
        _aware(self.decided_at_utc, "decided_at_utc")
        if self.verdict is Verdict.SUPPORTED:
            if self.supported_basis is None or not self.cited_evidence_ids:
                raise ValueError("SUPPORTED needs a supported_basis and cited evidence")
        elif self.supported_basis is not None:
            raise ValueError("supported_basis is only for SUPPORTED")
        return self


class PipelineRun(Model):
    id: str  # 'run:<YYYYMMDDTHHMMSSZ>'
    started_at_utc: datetime
    finished_at_utc: datetime | None = None
    status: PipelineRunStatus
    baker_version: str
    contracts_version: str
    rule_version: str
    config: dict[str, str | int | float | bool | None]  # eval mode, k, flags
    note: str | None = None  # why it failed, e.g. the invariant that stopped it


class ModelRun(Model):
    id: str
    pipeline_run_id: str | None = None
    purpose: str
    model_name: str
    model_sha256: str
    prompt_version: str
    prompt_sha256: str | None = None  # hash of the prompt file the run used
    params: dict[str, str | int | float | bool]
    seed: int | None
    started_at_utc: datetime


class ModelCall(Model):
    """One model call, stored whatever happened to its output, including dropped output."""

    id: str  # model_call_id(model_run_id, seq)
    model_run_id: str
    seq: int = Field(ge=1)
    subject_ids: tuple[str, ...]  # what the call was about: assumption, record, evidence ids
    prompt: str  # the fully rendered prompt sent to the model
    raw_output: str  # exactly what the model returned; '' on error
    outcome: ModelCallOutcome
    error: str | None = None
    at_utc: datetime


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
    supported_basis: SupportedBasis | None = None  # set iff verdict is SUPPORTED
    cited_record_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _basis_iff_supported(self) -> Prediction:
        if (self.verdict is Verdict.SUPPORTED) != (self.supported_basis is not None):
            raise ValueError("supported_basis is set exactly when verdict is SUPPORTED")
        return self


# ---------------------------------------------------------------- ids
# Ids are deterministic, so a re-run on the same inputs gives the same ids and gold labels,
# expert reviews and repeat-run comparisons can point at them. Content that a review depends
# on (params, stance, quote) is hashed into the id, so a changed label is a new item and an
# old review never carries over to it.


def canonical_json(value: object) -> str:
    """Stable JSON for hashing and storage: sorted keys, no spaces, UTF-8 kept."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def short_hash(value: object) -> str:
    """First 12 hex characters of the SHA-256 of canonical_json(value)."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:12]


def assumption_id(claim_id: str, template_id: str, params: AssumptionParams) -> str:
    return f"asm:{claim_id}:{template_id}:{short_hash(params)}"


def evidence_id(assumption_id: str, record_id: str, stance: Stance, quote: str) -> str:
    return f"ev:{assumption_id}|{record_id}|{short_hash([stance.value, quote])}"


def check_id(assumption_id: str, check_name: str, check_version: str) -> str:
    return f"chk:{assumption_id}|{check_name}@{check_version}"


def review_id(evidence_id: str, seq: int) -> str:
    return f"rv:{evidence_id}#{seq}"


def stipulation_id(kind: StipulationKind, subject_id: str) -> str:
    return f"stip:{kind.value}:{subject_id}"


def verdict_id(claim_id: str, pipeline_run_id: str) -> str:
    return f"vd:{claim_id}@{pipeline_run_id}"


def model_call_id(model_run_id: str, seq: int) -> str:
    return f"mc:{model_run_id}#{seq}"


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


class EvidenceReviewer(Protocol):
    """core/audit/review.py. Second local-model pass over one verified evidence item.

    Returns a ReviewDecision with reviewer_kind AI and status AI_ACCEPTED or DISMISSED,
    with the reviewer's reason. Never a verdict, never CONFIRMED, never ACCEPTED.
    Bad output or a runtime error is a DISMISSED decision whose reason says so.
    The reviewer never sees the labeler's rationale.
    """

    def review(
        self, assumption: Assumption, item: EvidenceItem, context: str
    ) -> ReviewDecision: ...


class QuoteVerifier(Protocol):
    """core/audit/quotes.py. True only if quote appears verbatim in the record's original text."""

    def __call__(self, quote: str, record_text: str) -> bool: ...


class DeterministicCheck(Protocol):
    """core/audit/checks/. Sender, timestamp and timezone, counts, absence vs coverage."""

    name: str
    version: str

    def run(self, assumption: Assumption, conn: sqlite3.Connection) -> CheckResult: ...


class VerdictRule(Protocol):
    """core/audit/rules.py (human-owned). The only thing that sets a verdict.

    Pure: reads its arguments only, writes nothing. Coverage is computed here and
    returned on the decision, never written back to assumptions.
    """

    def __call__(
        self,
        claim: Claim,
        assumptions: list[Assumption],
        evidence: list[EvidenceItem],
        checks: list[CheckResult],
        stipulations: list[Stipulation],
        pipeline_run_id: str,
    ) -> VerdictDecision: ...

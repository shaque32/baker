"""The testability agent: a second try at a claim the assumption filler left untested. Eval only
in v1, off by default (`Components.testability`; plans/agentic.md step 3).

When the filler (core/audit/assumption_filler.py) keeps no core assumption for a claim, this
step asks the same local model again, at most `cap` times per claim. Each call is stateless and
carries the claim, its paragraph, the allowed templates, the case's apps, the reasons code
refused the last try, and code's lookups: the people, phones and accounts that the claim's own
words name in the case (`lookups`, read-only queries fixed by code). The answer has the filler's
own shape and goes through the filler's own checks, the same functions and not a copy: every
value verbatim in the claim or its paragraph, names, phones and accounts resolved by code, the
stated time ranges, `coverage_gap`. A try that fails them is refused, with code's reasons, and
the next try (if the cap allows) is told those reasons.

Then code, never the examiner, checks the try against the claim's signed assumption sheet
(`mismatch`): every person, phone and time window the repaired set names must be one the
sheet's core rows for the claim name, and so must every account and handle. A try that names
anything else is rejected whole. A claim the sheet gives no core row is never repaired. With no
signed sheet the step does not run, which keeps it in the eval: the product has no sheet to
check against.

A try that passes is only a proposal. It becomes the claim's assumptions when an examiner
accepts it (`examiner`; in v1 the eval's simulated expert, through no UI). Without one it is
logged and never used. The report shows such an assumption as "Proposed by agent, accepted by
examiner" (`accepted_repairs`). The repair never sees, writes or changes the claim's text: the
output has no field for it, and the claim's stored row is hashed before and after
(`InvariantViolation` otherwise).

Each try is its own `testability.repair` audit entry (what code looked up, the model call, the
reasons, the sheet check and the assumption ids), and each acceptance a `testability.accept`
entry by the examiner's actor. `mabillon verify-bundle` re-runs the lookups and code's checks
on the stored answer with no model (core/bundle/verify.py).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from core.audit._llm_json import (
    PROMPTS_DIR,
    BadModelOutput,
    CallRecorder,
    JsonModel,
    fill_prompt,
    load_prompt,
    model_run_id,
    prompt_version,
    required_placeholders,
    run_json_call,
)
from core.audit._local_model import LocalModel, open_run
from core.audit.assumption_filler import (
    _PHONE_RE,
    TEMPLATE_HELP,
    LocalAssumptionFiller,
    Reject,
    _nfc,
    _ProposalOut,
    _same_number,
    _validate_list,
    coverage_gap,
    fill_schema,
    phone_digits,
)
from core.audit.assumptions import Proposal, instantiate, templates_for
from core.audit.invariants import InvariantViolation
from core.contracts import Assumption, Claim, ModelRun
from core.review.device_names import logged_names, name_key

VERSION = "0.1.0"
PROMPT_FILE = "agent_testability.md"  # signed copy only; the eval may name the draft
PLACEHOLDERS = frozenset({"claim", "paragraph", "templates", "channels", "lookups", "refused"})
REPAIR_ACTION = "testability.repair"
ACCEPT_ACTION = "testability.accept"
MAX_LOOKUPS = 30  # per claim, in code's fixed order: people, phones, accounts
MIN_NAME = 3  # an identifier or display name shorter than this is never looked up ("J")

Outcome = Literal["invalid", "refused", "mismatch", "proposed"]
Answer = list[dict[str, Any]] | str  # the answer's items, or why it was unusable
# The examiner: the assumptions a passing try would give the claim, in; the actor who accepted
# them ("expert:<name>"), or None, out. v1 has only the eval's simulated expert.
Examiner = Callable[[Claim, list[Assumption]], str | None]


# ---------------------------------------------------------------- lookups


@dataclass(frozen=True)
class Lookup:
    """Words of the claim or its paragraph that name something in the case, found by code."""

    kind: Literal["person", "phone", "account"]
    written: str  # exactly as the claim or paragraph writes them
    means: str  # what they name, in plain words

    def payload(self) -> dict[str, str]:
        return {"kind": self.kind, "written": self.written, "means": self.means}

    def line(self) -> str:
        return f'- "{self.written}": {self.means}'


def _written(words: str, texts: Sequence[str]) -> str | None:
    """The words as a text writes them (case and spacing as written), or None. Whole words
    only: "Item 1" is not found in "Item 12"."""
    parts = [re.escape(p) for p in _nfc(words).split()]
    if not parts:
        return None
    pattern = re.compile(r"(?<![\w@+])" + r"\s+".join(parts) + r"(?![\w])", re.IGNORECASE)
    for t in texts:
        m = pattern.search(_nfc(t))
        if m:
            return m.group(0)
    return None


def _phone_written(name: str, texts: Sequence[str]) -> str | None:
    """A phone's name as a text writes it, compared as the filler compares phone names: case
    and spacing do not count ("Item 1" is the phone whose source is "item1")."""
    chars = [re.escape(ch) for ch in name_key(name)]
    if not chars:
        return None
    pattern = re.compile(r"(?<![\w@+])" + r"\s*".join(chars) + r"(?![\w])", re.IGNORECASE)
    for t in texts:
        m = pattern.search(_nfc(t))
        if m:
            return m.group(0)
    return None


def lookups(filler: LocalAssumptionFiller, claim: Claim, para: str) -> list[Lookup]:
    """What the claim's own words name in the case: people the expert created (whole name or
    surname, as the filler resolves them), phones (label or a name the expert gave it) and
    accounts (identifier, the same number written another way, or display name). Read-only,
    in a fixed order, at most MAX_LOOKUPS."""
    conn, texts = filler.conn, (claim.text, para)
    out: list[Lookup] = []
    for _pid, name in conn.execute("SELECT id, name FROM persons ORDER BY id"):
        parts = name.split()
        for words in dict.fromkeys([name, parts[-1]] if parts else []):
            w = _written(words, texts)
            if w is not None:
                out.append(Lookup("person", w, f"a person in the case ({name})"))
                break
    names = logged_names(conn)
    for did, sid, label in conn.execute("SELECT id, source_id, label FROM devices ORDER BY id"):
        for words in dict.fromkeys(x for x in (label, *names.get(did, []), sid, did) if x):
            w = _phone_written(words, texts)
            if w is not None:
                out.append(Lookup("phone", w, f"a phone ({label or did}), not an account"))
                break
    numbers = [
        (m.group(0).strip().rstrip(".-").strip(), d)
        for t in texts
        for m in _PHONE_RE.finditer(_nfc(t))
        if (d := phone_digits(m.group(0))) is not None
    ]
    for a in sorted(filler.data.accounts.values(), key=lambda a: a.id):
        w = _written(a.identifier, texts) if len(a.identifier.strip()) >= MIN_NAME else None
        if w is None:
            w = next((words for words, d in numbers if _same_number(d, a)), None)
        if w is None and a.display_name and len(a.display_name.strip()) >= MIN_NAME:
            w = _written(a.display_name, texts)
        if w is not None:
            out.append(Lookup("account", w, f"an account on {a.app}"))
    return list(dict.fromkeys(out))[:MAX_LOOKUPS]


# ---------------------------------------------------------------- the sheet check


@dataclass(frozen=True)
class Named:
    """Who, which phones and which time windows a set of assumptions names."""

    people: frozenset[str] = frozenset()
    phones: frozenset[str] = frozenset()
    windows: frozenset[tuple[str, str]] = frozenset()  # (start UTC, end UTC), ISO
    accounts: frozenset[str] = frozenset()
    handles: frozenset[str] = frozenset()

    def payload(self) -> dict[str, list[Any]]:
        return {
            "people": sorted(self.people),
            "phones": sorted(self.phones),
            "windows": sorted(list(w) for w in self.windows),
            "accounts": sorted(self.accounts),
            "handles": sorted(self.handles),
        }

    @classmethod
    def from_payload(cls, p: Mapping[str, Any]) -> Named:
        return cls(
            people=frozenset(p.get("people", ())),
            phones=frozenset(p.get("phones", ())),
            windows=frozenset(tuple(w) for w in p.get("windows", ())),  # type: ignore[misc]
            accounts=frozenset(p.get("accounts", ())),
            handles=frozenset(p.get("handles", ())),
        )


def _utc(value: Any) -> str:
    t = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return t.isoformat()


def named(params: Iterable[Mapping[str, Any]]) -> Named:
    """What a set of parameter dicts names (AssumptionParams dumped, or a sheet row's params)."""
    people, phones, accounts, handles = set(), set(), set(), set()
    windows: set[tuple[str, str]] = set()
    for p in params:
        people |= set(p.get("person_ids") or ())
        phones |= set(p.get("device_ids") or ())
        accounts |= set(p.get("account_ids") or ())
        handles |= {_nfc(h).casefold() for h in p.get("handles") or ()}
        w = p.get("window")
        if isinstance(w, Mapping):
            windows.add((_utc(w["start_utc"]), _utc(w["end_utc"])))
    return Named(*(frozenset(x) for x in (people, phones, windows, accounts, handles)))


def sheet_named(
    rows: Iterable[Mapping[str, Any]], people: Mapping[str, str] | None = None
) -> dict[str, Named]:
    """Claim id -> what the signed sheet's core rows for it name. `people` maps the sheet's
    person ids to the case's (eval/run_pipeline.sheet_people)."""
    by_claim: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if not r.get("is_core"):
            continue
        params = dict(r.get("params") or {})
        if people and params.get("person_ids"):
            params["person_ids"] = [people.get(p, p) for p in params["person_ids"]]
        by_claim.setdefault(r["claim_id"], []).append(params)
    return {cid: named(ps) for cid, ps in by_claim.items()}


def mismatch(repair: Named, sheet: Named) -> list[str]:
    """What the repaired set names that the sheet does not. Empty: the same person, phone and
    window as the sheet."""
    out = []
    for what, got, want in (
        ("person", repair.people, sheet.people),
        ("phone", repair.phones, sheet.phones),
        ("time window", repair.windows, sheet.windows),
        ("account", repair.accounts, sheet.accounts),
        ("handle", repair.handles, sheet.handles),
    ):
        for x in sorted(got - want):
            shown = " to ".join(x) if isinstance(x, tuple) else x
            out.append(f"names the {what} {shown}, which the signed sheet does not name")
    return out


# The kinds of mismatch the go/no-go counts (plans/agentic.md: "a different person, phone or
# window than the sheet"); accounts and handles are rejected too and counted beside them.
NO_GO_KINDS = ("the person ", "the phone ", "the time window ")


# ---------------------------------------------------------------- one try


@dataclass
class Attempt:
    n: int
    call_id: str | None
    lookups: list[Lookup]
    refused_before: list[str]  # the reasons this try was told
    outcome: Outcome
    reasons: list[str]  # why it was refused or rejected; empty when proposed
    named: Named = field(default_factory=Named)
    assumption_ids: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {
            "attempt": self.n,
            "model_call_id": self.call_id,
            "lookups": [x.payload() for x in self.lookups],
            "refused_before": list(self.refused_before),
            "outcome": self.outcome,
            "reasons": list(self.reasons),
            "named": self.named.payload(),
            "assumption_ids": list(self.assumption_ids),
        }

    @property
    def no_go(self) -> bool:
        """A mismatch on a person, phone or window: one is a no-go (plans/agentic.md)."""
        return self.outcome == "mismatch" and any(
            r.startswith("names " + k) for r in self.reasons for k in NO_GO_KINDS
        )


@dataclass
class Repair:
    claim_id: str
    claim_sha256: str
    sheet: Named | None
    attempts: list[Attempt] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)  # set only once accepted
    accepted_by: str | None = None
    accepted_before: bool = False  # the acceptance was already in the log (the replay pass)

    def entries(self) -> list[dict[str, Any]]:
        """One testability.repair payload per try."""
        base = {
            "claim_id": self.claim_id,
            "claim_sha256": self.claim_sha256,
            "testability": VERSION,
            "sheet": self.sheet.payload() if self.sheet is not None else None,
        }
        return [{**base, **a.payload()} for a in self.attempts]

    def accept_entry(self) -> dict[str, Any] | None:
        if self.accepted_by is None or self.accepted_before:
            return None
        return {
            "claim_id": self.claim_id,
            "testability": VERSION,
            "assumption_ids": [a.id for a in self.assumptions],
            "attempt": self.attempts[-1].n,
            "model_call_id": self.attempts[-1].call_id,
        }


def claim_sha256(conn: sqlite3.Connection, claim_id: str) -> str:
    """The claim's stored row, hashed: the repair must leave it as it was."""
    row = conn.execute(
        "SELECT id, paragraph_id, text, claim_type, status, model_run_id FROM claims WHERE id = ?",
        (claim_id,),
    ).fetchone()
    return hashlib.sha256(json.dumps(list(row) if row else None).encode("utf-8")).hexdigest()


def check_answer(
    filler: LocalAssumptionFiller,
    claim: Claim,
    items: list[dict[str, Any]],
    sheet: Named | None,
) -> tuple[Outcome, list[str], Named, list[Assumption]]:
    """Code's verdict on one answer: the filler's own checks, then the sheet's. The same code
    runs live and in verify-bundle, so a stored answer gives the same outcome again."""
    para = filler.paragraph_text(claim)
    allowed = {t.id for t in templates_for(claim.claim_type)}
    reasons: list[str] = []
    kept: list[Proposal] = []
    for i, item in enumerate(items):
        try:
            p = _ProposalOut.model_validate(item)
            if p.template_id not in allowed:
                raise Reject(f"template {p.template_id!r} is not allowed for this claim")
            kept.append(filler._resolve(claim, para, p))
        except ValidationError as e:
            reasons.append(f"item {i}: wrong shape: {e.error_count()} errors")
        except Reject as e:
            reasons.append(f"item {i}: {e}")
    before = len(filler.drops)
    kept = filler._add_record_time(claim, para, kept, allowed)
    reasons += [d.reason for d in filler.drops[before:]]
    del filler.drops[before:]  # this try's refusals are the step's, not the first pass's
    gap = coverage_gap(claim, kept)
    if gap:
        return "refused", [*reasons, gap], Named(), []
    out: dict[str, Assumption] = {}
    for p in kept:
        try:
            a = instantiate(claim.id, p.template_id, p.params, p.is_core)
        except (ValidationError, ValueError) as e:
            return "refused", [*reasons, f"template {p.template_id!r}: {e}"], Named(), []
        out.setdefault(a.id, a)
    assumptions = list(out.values())
    got = named(a.params.model_dump() for a in assumptions if a.is_core)
    if sheet is None:
        return "mismatch", ["the signed sheet has no core assumption for this claim"], got, []
    wrong = mismatch(got, sheet)
    if wrong:
        return "mismatch", wrong, got, []
    return "proposed", [], got, assumptions


# ---------------------------------------------------------------- the step


def accepted_repairs(conn: sqlite3.Connection) -> dict[str, str]:
    """Assumption id -> the actor who accepted the repair that proposed it, from the log."""
    out: dict[str, str] = {}
    for actor, payload_json in conn.execute(
        "SELECT actor, payload_json FROM audit_log WHERE action = ? ORDER BY seq",
        (ACCEPT_ACTION,),
    ):
        for aid in json.loads(payload_json).get("assumption_ids", []):
            out[aid] = actor
    return out


class Testability:
    """The step. `filler` is the first pass's LocalAssumptionFiller (its checks are reused),
    `sheet` the signed sheet's facts by claim id (`sheet_named`), `cap` the most calls per claim
    (Arsh sets it; there is no default)."""

    def __init__(
        self,
        model: JsonModel,
        filler: LocalAssumptionFiller,
        sheet: Mapping[str, Named],
        cap: int,
        *,
        template: str | None = None,
        prompts_dir: Path = PROMPTS_DIR,
        examiner: Examiner | None = None,
        recorder: CallRecorder | None = None,
    ) -> None:
        if cap < 1:
            raise ValueError("the testability step needs a cap of at least one call per claim")
        if not sheet:
            raise ValueError("the testability step needs a signed sheet to check against")
        self.model = model
        self.filler = filler
        self.sheet = dict(sheet)
        self.cap = cap
        self.examiner = examiner
        self.template = template if template is not None else load_prompt(PROMPT_FILE, prompts_dir)
        missing = PLACEHOLDERS - required_placeholders(self.template)
        if missing:
            raise ValueError(f"testability prompt lacks placeholders: {sorted(missing)}")
        self.prompt_version = prompt_version(self.template)
        self.recorder = recorder if recorder is not None else CallRecorder()
        self.model_runs: tuple[ModelRun, ...] = ()
        # The replay pass after the expert's review gets each claim's answers back with no call.
        self.replaying = False
        self.seconds = 0.0  # spent in repair(), for the eval's budget (Y)
        self._answers: dict[tuple[str, int], tuple[Answer, str | None]] = {}

    @property
    def conn(self) -> sqlite3.Connection:
        return self.filler.conn

    def prompt(self, claim: Claim, found: list[Lookup], refused: list[str]) -> str:
        allowed = sorted(templates_for(claim.claim_type), key=lambda t: t.id)
        para = self.filler.paragraph_text(claim)
        return fill_prompt(
            self.template,
            {
                "claim": claim.text,
                "paragraph": para or "(paragraph not available)",
                "templates": "\n".join(
                    f"- {t.id}: {TEMPLATE_HELP.get(t.id, t.id)}" for t in allowed
                ),
                "channels": ", ".join(self.filler.channels()),
                "lookups": "\n".join(x.line() for x in found) or "(none)",
                "refused": "\n".join(f"- {r}" for r in refused) or "- (no reason recorded)",
            },
        )

    def _ask(self, claim: Claim, n: int, prompt: str) -> tuple[Answer, str | None]:
        """The answer's items, or why it was unusable, and the call id."""
        if self.replaying and (claim.id, n) in self._answers:
            return self._answers[(claim.id, n)]
        run_id = model_run_id(self.model)
        if run_id is None:
            return "model has no run id", None
        allowed = {t.id for t in templates_for(claim.claim_type)}
        schema = fill_schema(allowed, self.filler.channels())
        try:
            items, call = run_json_call(
                self.model, self.recorder, run_id, (claim.id,), prompt, schema, _validate_list
            )
            got: tuple[Answer, str | None] = (items, call.id)
        except BadModelOutput as e:
            got = (e.reason, e.call.id if e.call else None)
        self._answers[(claim.id, n)] = got
        return got

    def repair(self, claim: Claim, refused: list[str]) -> Repair:
        """Up to `cap` tries at a claim the filler left untested. The first try is told the
        filler's reasons, each later one the reasons code refused the try before it."""
        started = time.perf_counter()
        before = claim_sha256(self.conn, claim.id)
        rep = Repair(claim.id, before, self.sheet.get(claim.id))
        para = self.filler.paragraph_text(claim)
        found = lookups(self.filler, claim, para)
        told = list(refused)
        for n in range(1, self.cap + 1):
            answer, call_id = self._ask(claim, n, self.prompt(claim, found, told))
            if isinstance(answer, str):
                rep.attempts.append(Attempt(n, call_id, found, told, "invalid", [answer]))
                told = [answer]
                continue
            outcome, reasons, got, assumptions = check_answer(self.filler, claim, answer, rep.sheet)
            ids = [a.id for a in assumptions]
            rep.attempts.append(Attempt(n, call_id, found, told, outcome, reasons, got, ids))
            if outcome == "proposed":
                rep.assumptions = assumptions
                break
            told = reasons
        if claim_sha256(self.conn, claim.id) != before:
            raise InvariantViolation(f"{claim.id}: the testability step changed the claim")
        if rep.assumptions:
            self._accept(claim, rep)
        self.seconds += time.perf_counter() - started
        return rep

    def _accept(self, claim: Claim, rep: Repair) -> None:
        """An examiner's acceptance, or none: then the proposal is logged and never used."""
        ids = sorted(a.id for a in rep.assumptions)
        for actor, payload_json in self.conn.execute(
            "SELECT actor, payload_json FROM audit_log WHERE action = ? ORDER BY seq",
            (ACCEPT_ACTION,),
        ):
            p = json.loads(payload_json)
            if p.get("claim_id") == claim.id and sorted(p.get("assumption_ids", [])) == ids:
                rep.accepted_by, rep.accepted_before = actor, True
                return
        actor = self.examiner(claim, rep.assumptions) if self.examiner is not None else None
        if actor is None or not actor.startswith("expert:"):
            rep.assumptions = []  # a proposal nobody accepted is not used
            return
        rep.accepted_by = actor


def create(
    conn: sqlite3.Connection,
    filler: LocalAssumptionFiller,
    sheet: Mapping[str, Named],
    cap: int,
    *,
    model: LocalModel | None = None,
    template: str | None = None,
    examiner: Examiner | None = None,
) -> Testability:
    """The step on the local model (never a cloud one: it fills assumptions), with its own
    model run. The signed prompt (core/audit/prompts/agent_testability.md) unless the eval
    passes a template."""
    text = template if template is not None else load_prompt(PROMPT_FILE)
    # The per-call schema is the filler's, so the empty one records its shape (as the filler).
    opened = open_run(conn, "testability", text, model=model, schema=fill_schema((), ()))
    step = Testability(
        opened.port, filler, sheet, cap, template=text, examiner=examiner, recorder=opened.recorder
    )
    step.model_runs = (opened.run,)
    return step

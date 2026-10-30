"""The testability agent: a second try at a claim the assumption filler left untested. Off by
default (`Components.testability`; plans/agentic.md step 3): only the eval and the scripted demo
(eval/demo.py) turn it on. A review screen's audit or `mabillon audit` never does; turning it on
for pilots is a later, signed step (plans/agents-on-by-default.md).

When the filler (core/audit/assumption_filler.py) keeps no core assumption for a claim, this
step asks the same local model again, at most `cap` times per claim. Each call is stateless and
carries the claim, its paragraph, the allowed templates, the case's apps, the reasons code
refused the last try, and code's lookups: the people, phones and accounts that the claim's own
words name in the case (`lookups`, read-only queries fixed by code). The answer has the filler's
own shape and goes through the filler's own checks, the same functions and not a copy: every
value verbatim in the claim or its paragraph, names, phones and accounts resolved by code, the
stated time ranges, `coverage_gap`. A try that fails them is refused, with code's reasons, and
the next try (if the cap allows) is told those reasons.

Then code, never the examiner, checks that the try names only what the claim's own words name
(`outside_claim`, the check a case without a signed sheet gets): every person, phone and
account must be one code's lookups find in the claim's text, not its paragraph, and every handle
must be written there. The filler's own checks already read apps, quoted words, durations and
time ranges from the claim's text. A try that names anything else is rejected whole
("outside").

In the eval, code then checks the try against the claim's signed assumption sheet too
(`mismatch`): every person, phone and time window the repaired set names must be one the
sheet's core rows for the claim name, and so must every account, handle, app, template and
quoted words. A claim the sheet gives no core row is never repaired there. That makes what the
eval counts as converted an upper bound filtered by gold, so the tries the sheet check rejects
after the claim-only check passed them are reported beside it (eval/run_pipeline.py): how often
the claim-only check alone would let a wrong person, phone or window through.

A try that passes is only a proposal. It becomes the claim's assumptions only once an examiner
accepts it: the eval's simulated expert (`examiner`), or the examiner on the claim page's card
(core/review/actions.decide_repair, logged under the expert's actor). The next audit uses that
acceptance when the step gives the same assumptions again for the same claim text. Without an
acceptance a try is logged and never used, and an examiner's rejection keeps it out. The report
shows such an assumption as "Proposed by agent, accepted by examiner" (`used_repairs`, for the
audit shown only, the same reading the claim page and verify-bundle use). The
repair never sees, writes or changes the claim's text: the output has no field for it, and the
claim's stored row is hashed before and after (`InvariantViolation` otherwise).

A check that fails on an assumption the step proposed does not contradict the claim by itself
(rules 0.4.0, rule 1a, Arsh, 2026-10-28): an examiner may have accepted a wrong phone or time
window. The claim stays unproven, and the claim page shows "Contradiction found, confirm to
finalize" with the failed check. The expert confirms that failure (`testability.confirm`, with a
reason; core/review/actions.confirm_agent_fail), and it counts from the next verdict run, for as
long as the check fails exactly that way (`confirmed_fails`). Or the expert rejects the
proposal, and the next audit does not use it. rules.decide_verdict gets both sets from
`verdict_inputs`, the same reading in the audit, a verdict re-run and verify-bundle.

Each try is its own `testability.repair` audit entry (what code looked up, the model call, the
reasons, which checks ran, and the proposed assumptions with their texts), each decision a
`testability.accept` or `testability.reject` entry by the examiner's actor, and each confirmed
failure a `testability.confirm` entry. `mabillon verify-bundle` re-runs the lookups and code's
checks on the stored answer with no model (core/bundle/verify.py).
"""

from __future__ import annotations

import dataclasses
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
from core.audit.assumptions import Proposal, from_proposal, templates_for
from core.audit.invariants import InvariantViolation
from core.contracts import (
    Assumption,
    CheckOutcome,
    CheckResult,
    Claim,
    ModelRun,
    canonical_json,
)
from core.identity.aliases import person_names, written
from core.review.device_names import logged_names, name_key

# 0.2.0: the claim-only check (outcome "outside"), the checks each try ran ("check"), the
# proposed assumptions' texts in each entry, and the examiner's decisions from the claim page.
VERSION = "0.2.0"
PROMPT_FILE = "agent_testability.md"  # signed copy only; the eval may name the draft
PLACEHOLDERS = frozenset({"claim", "paragraph", "templates", "channels", "lookups", "refused"})
REPAIR_ACTION = "testability.repair"
ACCEPT_ACTION = "testability.accept"
REJECT_ACTION = "testability.reject"
# an expert confirms a failed check on an assumption the step proposed (rules 0.4.0, rule 1a)
CONFIRM_ACTION = "testability.confirm"
PROPOSED_MARK = "Proposed by agent"
CLAIM_CHECK = "claim"  # the claim-only check, all a case without a signed sheet gets
SHEET_CHECK = "claim and sheet"  # the eval's: the claim-only check, then the signed sheet
MAX_LOOKUPS = 30  # per claim, in code's fixed order: people, phones, accounts
MIN_NAME = 3  # an identifier or display name shorter than this is never looked up ("J")

Outcome = Literal["invalid", "refused", "outside", "mismatch", "proposed"]
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


def _alias_written(alias: str, texts: Sequence[str]) -> str | None:
    """An alias as a text writes it, or None (core/identity/aliases.written: whole, in any
    case, "SUBJECT 1" for "SUBJECT-1", never "SUBJECT-12")."""
    return next((w for t in texts if (w := written(alias, t)) is not None), None)


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


def _found(filler: LocalAssumptionFiller, texts: Sequence[str]) -> list[tuple[Lookup, str]]:
    """Each lookup the texts give, with the person, device or account id it names."""
    conn = filler.conn
    out: list[tuple[Lookup, str]] = []
    # A person's name, its surname, then each alias the expert gave them, whole only and
    # compared as the Identities page compares it (core/identity/aliases.py: an alias two
    # persons share is in neither list).
    for pid, (name, aliases) in person_names(conn).items():
        parts = name.split()
        tries = [(_written, w) for w in dict.fromkeys([name, parts[-1]] if parts else [])]
        tries += [(_alias_written, a) for a in aliases]
        for match, words in tries:
            w = match(words, texts)
            if w is not None:
                out.append((Lookup("person", w, f"a person in the case ({name})"), pid))
                break
    names = logged_names(conn)
    for did, sid, label in conn.execute("SELECT id, source_id, label FROM devices ORDER BY id"):
        for words in dict.fromkeys(x for x in (label, *names.get(did, []), sid, did) if x):
            w = _phone_written(words, texts)
            if w is not None:
                out.append((Lookup("phone", w, f"a phone ({label or did}), not an account"), did))
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
            out.append((Lookup("account", w, f"an account on {a.app}"), a.id))
    return out


def lookups(filler: LocalAssumptionFiller, claim: Claim, para: str) -> list[Lookup]:
    """What the claim's own words name in the case: people the expert created (whole name or
    surname, as the filler resolves them, or an alias the expert gave them, whole), phones
    (label or a name the expert gave it) and accounts (identifier, the same number written
    another way, or display name). Read-only, in a fixed order, at most MAX_LOOKUPS."""
    found = [x for x, _id in _found(filler, (claim.text, para))]
    return list(dict.fromkeys(found))[:MAX_LOOKUPS]


# ---------------------------------------------------------------- the sheet check


@dataclass(frozen=True)
class Named:
    """Who, which phones and time windows, and which apps, templates and quoted words a set of
    assumptions names."""

    people: frozenset[str] = frozenset()
    phones: frozenset[str] = frozenset()
    windows: frozenset[tuple[str, str]] = frozenset()  # (start UTC, end UTC), ISO
    accounts: frozenset[str] = frozenset()
    handles: frozenset[str] = frozenset()  # casefolded
    apps: frozenset[str] = frozenset()  # channels, casefolded
    templates: frozenset[str] = frozenset()
    quotes: frozenset[str] = frozenset()  # casefolded, whitespace folded

    def payload(self) -> dict[str, list[Any]]:
        return {
            "people": sorted(self.people),
            "phones": sorted(self.phones),
            "windows": sorted(list(w) for w in self.windows),
            "accounts": sorted(self.accounts),
            "handles": sorted(self.handles),
            "apps": sorted(self.apps),
            "templates": sorted(self.templates),
            "quotes": sorted(self.quotes),
        }

    @classmethod
    def from_payload(cls, p: Mapping[str, Any]) -> Named:
        return cls(
            people=frozenset(p.get("people", ())),
            phones=frozenset(p.get("phones", ())),
            windows=frozenset(tuple(w) for w in p.get("windows", ())),  # type: ignore[misc]
            accounts=frozenset(p.get("accounts", ())),
            handles=frozenset(p.get("handles", ())),
            apps=frozenset(p.get("apps", ())),
            templates=frozenset(p.get("templates", ())),
            quotes=frozenset(p.get("quotes", ())),
        )


def _utc(value: Any) -> str:
    t = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return t.isoformat()


def _fold(words: str) -> str:
    return " ".join(_nfc(words).casefold().split())


def named(rows: Iterable[tuple[str, Mapping[str, Any]]]) -> Named:
    """What a set of (template id, parameters) names: AssumptionParams dumped, or a sheet
    row's params."""
    people, phones, accounts, handles = set(), set(), set(), set()
    apps, templates, quotes = set(), set(), set()
    windows: set[tuple[str, str]] = set()
    for template_id, p in rows:
        templates.add(template_id)
        people |= set(p.get("person_ids") or ())
        phones |= set(p.get("device_ids") or ())
        accounts |= set(p.get("account_ids") or ())
        handles |= {_nfc(h).casefold() for h in p.get("handles") or ()}
        apps |= {_nfc(c).casefold() for c in p.get("channels") or ()}
        if p.get("quoted_text"):
            quotes.add(_fold(p["quoted_text"]))
        w = p.get("window")
        if isinstance(w, Mapping):
            windows.add((_utc(w["start_utc"]), _utc(w["end_utc"])))
    return Named(
        *(
            frozenset(x)
            for x in (people, phones, windows, accounts, handles, apps, templates, quotes)
        )
    )


def sheet_named(
    rows: Iterable[Mapping[str, Any]], people: Mapping[str, str] | None = None
) -> dict[str, Named]:
    """Claim id -> what the signed sheet's core rows for it name. `people` maps the sheet's
    person ids to the case's (eval/run_pipeline.sheet_people)."""
    by_claim: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for r in rows:
        if not r.get("is_core"):
            continue
        params = dict(r.get("params") or {})
        if people and params.get("person_ids"):
            params["person_ids"] = [people.get(p, p) for p in params["person_ids"]]
        by_claim.setdefault(r["claim_id"], []).append((r["template_id"], params))
    return {cid: named(ps) for cid, ps in by_claim.items()}


def mismatch(repair: Named, sheet: Named) -> list[str]:
    """What the repaired set names that the sheet does not. Empty: the same people, phones,
    windows, accounts, handles, apps, templates and quoted words as the sheet, or fewer."""
    out = []
    for what, got, want in (
        ("person", repair.people, sheet.people),
        ("phone", repair.phones, sheet.phones),
        ("time window", repair.windows, sheet.windows),
        ("account", repair.accounts, sheet.accounts),
        ("handle", repair.handles, sheet.handles),
        ("app", repair.apps, sheet.apps),
        ("template", repair.templates, sheet.templates),
        ("quoted words", repair.quotes, sheet.quotes),
    ):
        for x in sorted(got - want):
            shown = " to ".join(x) if isinstance(x, tuple) else repr(x)
            out.append(f"names the {what} {shown}, which the signed sheet does not name")
    return out


def outside_claim(filler: LocalAssumptionFiller, claim: Claim, got: Named) -> list[str]:
    """What the repaired set names that the claim's own words do not: a person, phone or
    account code's lookups do not find in the claim's text (its paragraph does not count), or a
    handle not written there. Empty: everything it names is the claim's own. Apps, quoted
    words, durations and time ranges need no second look: the filler reads them from the
    claim's text already."""
    own: dict[str, set[str]] = {"person": set(), "phone": set(), "account": set()}
    for x, xid in _found(filler, (claim.text,)):
        own[x.kind].add(xid)
    out = []
    for what, ids in (("person", got.people), ("phone", got.phones), ("account", got.accounts)):
        for x in sorted(ids - own[what]):
            out.append(f"names the {what} {x!r}, which the claim's own words do not name")
    for h in sorted(got.handles):
        if _written(h, (claim.text,)) is None:
            out.append(f"names the handle {h!r}, which the claim's own words do not write")
    return out


# The kinds of mismatch the go/no-go counts (plans/agentic.md: "a different person, phone or
# window than the sheet"); the other kinds are rejected too and counted beside them.
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
    proposed: list[dict[str, str]] = field(default_factory=list)  # `shown`, what a card shows

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
            "proposed": list(self.proposed),
        }

    @property
    def no_go(self) -> bool:
        """A mismatch on a person, phone or window: one is a no-go (plans/agentic.md)."""
        return self.outcome == "mismatch" and any(
            r.startswith("names " + k) for r in self.reasons for k in NO_GO_KINDS
        )


def shown(assumptions: Iterable[Assumption]) -> list[dict[str, str]]:
    """The proposed assumptions as the examiner's card shows them, in the repair's log entry."""
    return [{"id": a.id, "template_id": a.template_id, "text": a.text} for a in assumptions]


@dataclass
class Repair:
    claim_id: str
    claim_sha256: str
    sheet: Named | None
    check: str = CLAIM_CHECK
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
            "check": self.check,
            "sheet": self.sheet.payload() if self.sheet is not None else None,
        }
        return [{**base, **a.payload()} for a in self.attempts]

    def accept_entry(self) -> dict[str, Any] | None:
        if self.accepted_by is None or self.accepted_before:
            return None
        return {
            "claim_id": self.claim_id,
            "claim_sha256": self.claim_sha256,
            "testability": VERSION,
            "assumption_ids": sorted(a.id for a in self.assumptions),
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


def row_sha256(claim: Claim) -> str:
    """claim_sha256 of a claim as given, not as stored: verify-bundle's check that the claim it
    rebuilt from the log is the one a try was made on."""
    row = [
        claim.id,
        claim.paragraph_id,
        claim.text,
        claim.claim_type.value,
        claim.status.value,
        claim.model_run_id,
    ]
    return hashlib.sha256(json.dumps(row).encode("utf-8")).hexdigest()


def check_answer(
    filler: LocalAssumptionFiller,
    claim: Claim,
    items: list[dict[str, Any]],
    sheet: Named | None,
    check: str = SHEET_CHECK,
) -> tuple[Outcome, list[str], Named, list[Assumption]]:
    """Code's verdict on one answer: the filler's own checks, the claim-only check, then (with
    check SHEET_CHECK, the eval's) the signed sheet's. The same code runs live and in
    verify-bundle, so a stored answer gives the same outcome again."""
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
    # The filler's own steps after its items, in its order (LocalAssumptionFiller.__call__):
    # the template shape check, code's sender, time range and meaning fills, then the gate.
    before = len(filler.drops)
    kept = filler._shaped(claim, kept, None)
    kept = filler.code_fills(claim, para, kept, allowed, None)
    reasons += [d.reason for d in filler.drops[before:]]
    del filler.drops[before:]  # this try's refusals are the step's, not the first pass's
    gap = coverage_gap(claim, kept, frozenset(filler._names()))
    if gap:
        return "refused", [*reasons, gap], Named(), []
    out: dict[str, Assumption] = {}
    for p in kept:
        try:
            a = from_proposal(claim.id, p)  # keeps the code-made note (Codex on #169)
        except (ValidationError, ValueError) as e:
            return "refused", [*reasons, f"template {p.template_id!r}: {e}"], Named(), []
        out.setdefault(a.id, a)
    assumptions = list(out.values())
    got = named((a.template_id, a.params.model_dump()) for a in assumptions if a.is_core)
    outside = outside_claim(filler, claim, got)
    if outside:
        return "outside", outside, got, []
    if check == CLAIM_CHECK:
        return "proposed", [], got, assumptions
    if sheet is None:
        return "mismatch", ["the signed sheet has no core assumption for this claim"], got, []
    wrong = mismatch(got, sheet)
    if wrong:
        return "mismatch", wrong, got, []
    return "proposed", [], got, assumptions


# ---------------------------------------------------------------- the step


def decision(
    conn: sqlite3.Connection,
    claim_id: str,
    assumption_ids: Iterable[str],
    claim_sha: str,
    before: int | None = None,
) -> tuple[str, str] | None:
    """An expert's latest decision on this exact proposal, (action, actor): the same claim, the
    same claim text and the same assumptions. None when no expert decided it. With before, only
    log entries before that seq count: what was in force when an audit used the proposal."""
    ids = sorted(assumption_ids)
    got = None
    for actor, action, payload_json in conn.execute(
        "SELECT actor, action, payload_json FROM audit_log WHERE action IN (?, ?) AND seq < ?"
        " ORDER BY seq",
        (ACCEPT_ACTION, REJECT_ACTION, before if before is not None else 2**62),
    ):
        p = json.loads(payload_json)
        if (
            actor.startswith("expert:")
            and p.get("claim_id") == claim_id
            and p.get("claim_sha256") == claim_sha
            and sorted(p.get("assumption_ids", [])) == ids
        ):
            got = (action, actor)
    return got


@dataclass(frozen=True)
class Proposed:
    """A try the step proposed in an audit, as the claim page's card shows it."""

    claim_id: str
    run_id: str
    attempt: int
    model_call_id: str | None
    claim_sha256: str
    assumptions: tuple[Mapping[str, str], ...]  # id, template_id, text (`shown`)
    lookups: tuple[Mapping[str, str], ...]
    check: str
    decided: tuple[str, str] | None  # the expert's latest (action, actor), or None

    @property
    def assumption_ids(self) -> list[str]:
        return sorted(a["id"] for a in self.assumptions)


def proposals(conn: sqlite3.Connection, run: Mapping[str, Any] | None) -> dict[str, Proposed]:
    """Claim id -> the try the step proposed for it in the audit whose evidence `run` shows (a
    verdict re-run shows its source audit's), with the expert's latest decision on it."""
    if run is None:
        return {}
    source = run.get("evidence_from_run", run["run_id"])
    out: dict[str, Proposed] = {}
    for (payload_json,) in conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq", (REPAIR_ACTION,)
    ):
        p = json.loads(payload_json)
        if p.get("run_id") != source or p.get("outcome") != "proposed":
            continue
        cid = str(p.get("claim_id"))
        out[cid] = Proposed(
            claim_id=cid,
            run_id=source,
            attempt=int(p.get("attempt", 0)),
            model_call_id=p.get("model_call_id"),
            claim_sha256=str(p.get("claim_sha256", "")),
            assumptions=tuple(p.get("proposed") or ()),
            lookups=tuple(p.get("lookups") or ()),
            check=str(p.get("check", SHEET_CHECK)),
            decided=None,
        )
    return {
        cid: dataclasses.replace(x, decided=decision(conn, cid, x.assumption_ids, x.claim_sha256))
        for cid, x in out.items()
    }


def in_force(
    conn: sqlite3.Connection, run_id: str
) -> dict[str, tuple[list[str], str, tuple[str, str] | None]]:
    """Claim id -> (assumption ids, claim hash, decision) for each try the audit run_id's step
    proposed: the expert's latest decision on it when that audit used it, read as the step read
    it (`decision`, before the claim's pipeline.claim entry closed its work). None when no
    expert had decided it."""
    from core import pipeline

    done: dict[str, int] = {}
    tried: dict[str, tuple[list[str], str]] = {}
    for seq, action, payload_json in conn.execute(
        "SELECT seq, action, payload_json FROM audit_log WHERE action IN (?, ?) ORDER BY seq",
        (REPAIR_ACTION, pipeline.CLAIM_ACTION),
    ):
        p = json.loads(payload_json)
        if p.get("run_id") != run_id:
            continue
        cid = str(p.get("claim_id"))
        if action == pipeline.CLAIM_ACTION:
            done.setdefault(cid, seq)
        elif p.get("outcome") == "proposed":
            tried[cid] = (sorted(p.get("assumption_ids") or []), str(p.get("claim_sha256")))
    return {
        cid: (ids, sha, decision(conn, cid, ids, sha, before=done.get(cid)))
        for cid, (ids, sha) in tried.items()
    }


@dataclasses.dataclass(frozen=True)
class Used:
    """An agent proposal the shown audit used: the examiner whose acceptance it used, and why
    that acceptance no longer holds for the next audit, if it does not."""

    by: str
    lapsed: str | None = None

    def mark(self) -> str:
        """The line the claim page and the report show beside the assumption."""
        line = f"{PROPOSED_MARK}, accepted by examiner ({self.by.removeprefix('expert:')})"
        return f"{line}; {self.lapsed}, so the next audit does not use it" if self.lapsed else line


def used_repairs(conn: sqlite3.Connection, run: dict[str, Any] | None) -> dict[str, Used]:
    """Assumption id -> how the shown audit used it, for the step's proposals that audit (or the
    audit a verdict re-run took its evidence from) used under an expert's acceptance in force
    then. One reading for the claim page and the report; verify-bundle checks the same rule
    (`in_force`). Another audit's acceptance, a rejected proposal, and an assumption the filler
    made itself are not marked."""
    if run is None:
        return {}
    out: dict[str, Used] = {}
    for cid, (ids, _sha, d) in in_force(conn, run.get("evidence_from_run", run["run_id"])).items():
        if d is None or d[0] != ACCEPT_ACTION:
            continue
        now = decision(conn, cid, ids, claim_sha256(conn, cid))
        lapsed = (
            "the claim was edited or removed after the acceptance"
            if now is None
            else f"later rejected by {now[1].removeprefix('expert:')}"
            if now[0] == REJECT_ACTION
            else None
        )
        out.update(dict.fromkeys(ids, Used(d[1], lapsed)))
    return out


def accepted_in(
    conn: sqlite3.Connection, run: Mapping[str, Any] | None
) -> dict[str, tuple[list[str], str]]:
    """Claim id -> (assumption ids, claim hash) of the proposal the audit `run` (or the audit a
    verdict re-run took its evidence from) used under an expert's acceptance in force then
    (`in_force`): the assumptions rules.decide_verdict gets as agent_proposed."""
    if run is None:
        return {}
    source = str(run.get("evidence_from_run", run["run_id"]))
    return {
        cid: (ids, sha)
        for cid, (ids, sha, d) in in_force(conn, source).items()
        if d is not None and d[0] == ACCEPT_ACTION
    }


def check_sha256(check: CheckResult) -> str:
    """A check result as it failed, hashed: an expert's confirm holds for that failure only."""
    return hashlib.sha256(canonical_json(check).encode("utf-8")).hexdigest()


def seen_sha256(accepted: tuple[list[str], str], check: CheckResult) -> str:
    """What the claim page's confirm form carries: the failure as shown, with the proposal it
    failed on and the claim text that proposal was accepted for (`accepted`, from accepted_in).
    A page left open across a later audit or a claim edit confirms nothing it did not show
    (Codex on #166 and #168)."""
    ids, claim_sha = accepted
    shown = {"assumption_ids": sorted(ids), "check": check_sha256(check), "claim": claim_sha}
    return hashlib.sha256(canonical_json(shown).encode("utf-8")).hexdigest()


def confirmed_fails(
    conn: sqlite3.Connection,
    claim_id: str,
    assumption_ids: Iterable[str],
    claim_sha: str,
    checks: Iterable[CheckResult],
    before: int | None = None,
) -> frozenset[str]:
    """Ids of the failed checks among `checks` an expert confirmed exactly as they failed: the
    same claim, claim text, proposal and check result. An expert's rejection of the proposal
    logged after a confirm undoes it. With before, only log entries before that seq count."""
    ids = sorted(assumption_ids)
    got: dict[str, str] = {}
    for actor, action, payload_json in conn.execute(
        "SELECT actor, action, payload_json FROM audit_log WHERE action IN (?, ?) AND seq < ?"
        " ORDER BY seq",
        (CONFIRM_ACTION, REJECT_ACTION, before if before is not None else 2**62),
    ):
        p = json.loads(payload_json)
        if not (
            actor.startswith("expert:")
            and p.get("claim_id") == claim_id
            and p.get("claim_sha256") == claim_sha
            and sorted(p.get("assumption_ids", [])) == ids
        ):
            continue
        if action == REJECT_ACTION:
            got.clear()
        else:
            got[str(p.get("check_id"))] = str(p.get("check_sha256"))
    return frozenset(
        c.id for c in checks if c.outcome is CheckOutcome.FAIL and got.get(c.id) == check_sha256(c)
    )


def verdict_inputs(
    conn: sqlite3.Connection,
    accepted: Mapping[str, tuple[list[str], str]],
    claim_id: str,
    checks: Sequence[CheckResult],
    before: int | None = None,
) -> dict[str, frozenset[str]]:
    """rules.decide_verdict's agent_proposed and confirmed_fails for one claim (rules 0.4.0):
    the assumptions the audit took from the step (`accepted`, from `accepted_in` or the run's
    own repair) and the failures of them an expert confirmed. Empty for a claim the step did not
    change, whose call then is the one rules 0.3.0 got."""
    got = accepted.get(claim_id)
    if got is None:
        return {}
    ids, sha = got
    return {
        "agent_proposed": frozenset(ids),
        "confirmed_fails": confirmed_fails(conn, claim_id, ids, sha, checks, before),
    }


def awaiting(
    conn: sqlite3.Connection,
    accepted: Mapping[str, tuple[list[str], str]],
    claim_id: str,
    assumptions: Sequence[Assumption],
    checks: Sequence[CheckResult],
) -> list[CheckResult]:
    """The failed checks on a core assumption the shown audit took from the step that no expert
    has confirmed, while the acceptance still holds (no later rejection, no claim edit): what
    the claim page asks the expert to confirm. Each keeps the claim unproven (rules 0.4.0)."""
    got = accepted.get(claim_id)
    if got is None:
        return []
    ids, sha = got
    now = decision(conn, claim_id, ids, claim_sha256(conn, claim_id))
    if now is None or now[0] != ACCEPT_ACTION:
        return []  # lapsed: the next audit does not use the proposal
    core = {a.id for a in assumptions if a.is_core and a.id in set(ids)}
    done = confirmed_fails(conn, claim_id, ids, sha, checks)
    return [
        c
        for c in checks
        if c.outcome is CheckOutcome.FAIL and c.assumption_id in core and c.id not in done
    ]


class Testability:
    """The step. `filler` is the first pass's LocalAssumptionFiller (its checks are reused),
    `sheet` the signed sheet's facts by claim id (`sheet_named`; the eval's), or None for a case
    without one, which gets the claim-only check alone. `cap` is the most calls per claim (Arsh
    sets it; there is no default)."""

    def __init__(
        self,
        model: JsonModel,
        filler: LocalAssumptionFiller,
        sheet: Mapping[str, Named] | None,
        cap: int,
        *,
        template: str | None = None,
        prompts_dir: Path = PROMPTS_DIR,
        examiner: Examiner | None = None,
        recorder: CallRecorder | None = None,
    ) -> None:
        if cap < 1:
            raise ValueError("the testability step needs a cap of at least one call per claim")
        if sheet is not None and not sheet:
            raise ValueError("a signed sheet to check against has no rows")
        self.model = model
        self.filler = filler
        self.sheet = dict(sheet) if sheet is not None else None
        self.check = CLAIM_CHECK if sheet is None else SHEET_CHECK
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
        sheet = self.sheet.get(claim.id) if self.sheet is not None else None
        rep = Repair(claim.id, before, sheet, self.check)
        para = self.filler.paragraph_text(claim)
        found = lookups(self.filler, claim, para)
        told = list(refused)
        for n in range(1, self.cap + 1):
            answer, call_id = self._ask(claim, n, self.prompt(claim, found, told))
            if isinstance(answer, str):
                rep.attempts.append(Attempt(n, call_id, found, told, "invalid", [answer]))
                told = [answer]
                continue
            outcome, reasons, got, assumptions = check_answer(
                self.filler, claim, answer, rep.sheet, self.check
            )
            ids = [a.id for a in assumptions]
            rep.attempts.append(
                Attempt(n, call_id, found, told, outcome, reasons, got, ids, shown(assumptions))
            )
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
        """An examiner's acceptance, or none: then the proposal is logged and never used. An
        expert's earlier decision on this exact proposal (the claim page's card, or the eval's
        first pass) stands: an acceptance is used, a rejection keeps it out."""
        done = decision(self.conn, claim.id, (a.id for a in rep.assumptions), rep.claim_sha256)
        if done is not None:
            action, actor = done
            if action == ACCEPT_ACTION:
                rep.accepted_by, rep.accepted_before = actor, True
            else:
                rep.assumptions = []
            return
        actor = self.examiner(claim, rep.assumptions) if self.examiner is not None else None
        if actor is None or not actor.startswith("expert:"):
            rep.assumptions = []  # a proposal nobody accepted is not used
            return
        rep.accepted_by = actor


def create(
    conn: sqlite3.Connection,
    filler: LocalAssumptionFiller,
    sheet: Mapping[str, Named] | None,
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

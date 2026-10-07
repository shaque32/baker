"""Red-team scenarios for the verdict rules. SYNTHETIC.

Each scenario is one claim with its assumptions, evidence items and check results, built from
the frozen contracts, that tries to get core/audit/rules.py to say SUPPORTED when it must not.
tests/adversarial/test_rules_red_team.py runs every scenario through decide_verdict once the
rules exist (it skips while rules.py is a stub).

Controls are the opposite: clean cases the rules must call SUPPORTED, so rules that answer
UNPROVEN to everything cannot pass the red team by doing nothing.

The scenarios follow the rules as written in the rules.py docstring and the consensus plan
(/mnt/project-files/baker/roadmap/wave2-consensus.md, sections 1 and 4):
- rules.py works out coverage of each core assumption from check results and accepted evidence;
  it never trusts a tier written back by another component.
- SUPPORTED needs at least one verified, observed SUPPORTS item accepted by the AI reviewer
  ('ai_accepted') or an expert ('accepted'), and no open contradicting or complicating item.
- A failed deterministic check on a core assumption makes the claim CONTRADICTED.
- The per-case phone-ownership stipulation is an assumption at tier confirmed (expert, once).

The controls also rest on two defaults Arsh approved with the plan ("okay run it",
2026-10-07): coverage is computed in rules.py, and phone ownership is a confirmed stipulation.

Scenarios marked `decision` rest on a rule Arsh has not signed yet; the test reports them
separately so a disagreement shows up as a question, not a silent pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from core.contracts import (
    Assumption,
    AssumptionKind,
    CheckOutcome,
    CheckResult,
    Claim,
    ClaimStatus,
    ClaimType,
    EvidenceItem,
    EvidenceStatus,
    ProvenanceTier,
    SourceRef,
    Stance,
    Verdict,
)

T = ProvenanceTier
S = EvidenceStatus
CLAIM_ID = "claim:redteam:1"
OTHER_CLAIM_ID = "claim:redteam:2"
DECIDED_AT = datetime(2026, 10, 7, tzinfo=UTC)
PIPELINE_RUN_ID = "run:redteam"

# Contracts v0.2 (PR #15) adds typed assumption params, check coverage text and case-level
# stipulations. Build for whichever contracts are on the branch; drop the v0.1 path once
# v0.2 is on main.
V02 = "template_id" in Assumption.model_fields

# ---------------------------------------------------------------- builders
# Every contract object is built here, so a contracts change is a one-place fix.


def claim(text: str, claim_type: ClaimType = ClaimType.COMMUNICATION) -> Claim:
    return Claim(
        id=CLAIM_ID,
        paragraph_id="para:govdoc1:6",
        text=text,
        claim_type=claim_type,
        status=ClaimStatus.ACCEPTED,
    )


def assumption(
    n: int,
    kind: AssumptionKind,
    text: str,
    *,
    core: bool = True,
    tier: ProvenanceTier = T.INFERRED,
    claim_id: str = CLAIM_ID,
) -> Assumption:
    extra: dict[str, object] = {}
    if V02:
        from core.contracts import AssumptionParams

        extra = {
            "template_id": f"redteam_{kind.value}",
            "template_version": "redteam",
            "params": AssumptionParams(),
        }
    return Assumption(
        id=f"asm:{claim_id}:{n}",
        claim_id=claim_id,
        kind=kind,
        text=text,
        is_core=core,
        tier=tier,
        **extra,  # type: ignore[arg-type]
    )


def ownership() -> tuple[list[Assumption], tuple[object, ...]]:
    """The per-case stipulation the expert confirms once: Item 1 speaks for PETROV.

    v0.1 has no stipulations, so it is an identity assumption at tier confirmed there.
    Returns (assumptions to add to every claim, stipulations to pass to the rules).
    """
    if not V02:
        own = assumption(
            0,
            AssumptionKind.IDENTITY,
            "Item 1's owner accounts are used by PETROV (case stipulation)",
            tier=T.CONFIRMED,
        )
        return [own], ()
    from core.contracts import Stipulation, StipulationKind, StipulationStatus

    stip = Stipulation(
        id="stip:device_owner:dev:item1",
        kind=StipulationKind.DEVICE_OWNER,
        subject_id="dev:item1",
        person_id="person:petrov",
        statement="Item 1 is used by PETROV",
        status=StipulationStatus.CONFIRMED,
        decided_by="expert:redteam",
        decided_at_utc=DECIDED_AT,
    )
    return [], (stip,)


def item(
    n: int,
    asm: Assumption,
    stance: Stance,
    status: EvidenceStatus,
    *,
    quote: str = "need 2 more by friday",
    record_id: str = "msg:item1:Chats!948",
    tier: ProvenanceTier = T.OBSERVED,
) -> EvidenceItem:
    return EvidenceItem(
        id=f"ev:{asm.id}:{n}",
        assumption_id=asm.id,
        record_id=record_id,
        ref=SourceRef(source_id="item1", locator=record_id.split(":", 2)[2]),
        stance=stance,
        quote=quote,
        quote_verified=True,
        rationale="red-team fixture",
        tier=tier,
        status=status,
        model_run_id="run:redteam",
    )


def check(n: int, asm: Assumption, outcome: CheckOutcome, name: str = "time_window") -> CheckResult:
    return CheckResult(
        id=f"chk:{asm.id}:{n}",
        assumption_id=asm.id,
        check_name=name,
        check_version="redteam",
        outcome=outcome,
        detail=f"red-team fixture: {name} {outcome.value}",
        **({"searched": "red-team fixture"} if V02 else {}),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- scenario type


@dataclass(frozen=True)
class Scenario:
    sid: str
    title: str
    trap: str
    claim: Claim
    assumptions: list[Assumption]
    evidence: list[EvidenceItem]
    checks: list[CheckResult]
    # Only set when the rules as written leave no doubt; otherwise the test asserts
    # "not SUPPORTED" and nothing more.
    expected: Verdict | None = None
    decision: str | None = None  # the unsigned rule this scenario rests on, if any
    tags: tuple[str, ...] = field(default=())
    stipulations: tuple[object, ...] = field(default=())


# Shared pieces for a communication claim: "On March 12, PETROV wrote 'need 2 more by friday'."
COMM = claim('On March 12, 2026, PETROV wrote to @northstar: "need 2 more by friday".')
OWN, STIPS = ownership()
MSG = assumption(1, AssumptionKind.EVENT, "Item 1 has an outgoing message with that exact text")
WHEN = assumption(2, AssumptionKind.TIME, "The message was sent on March 12, 2026, local time")
# Rules 0.1.0 (rule 3e): a communication claim needs an identity assumption among its core
# ones. Here the sender check covers it, so each attack fails for its own reason.
WHO = assumption(5, AssumptionKind.IDENTITY, "PETROV's Telegram account sent the message")
ok_when = check(1, WHEN, CheckOutcome.PASS)
ok_who = check(1, WHO, CheckOutcome.PASS, "sender")


Parts = tuple[Claim, list[Assumption], list[EvidenceItem], list[CheckResult]]


def comm(
    evidence: list[EvidenceItem],
    checks: list[CheckResult] | None = None,
    assumptions: list[Assumption] | None = None,
) -> Parts:
    return (
        COMM,
        assumptions if assumptions is not None else [*OWN, WHO, MSG, WHEN],
        evidence,
        checks if checks is not None else [ok_when, ok_who],
    )


def _s(
    sid: str,
    title: str,
    trap: str,
    parts: Parts,
    *,
    expected: Verdict | None = None,
    decision: str | None = None,
    tags: tuple[str, ...] = (),
) -> Scenario:
    c, a, e, k = parts
    return Scenario(sid, title, trap, c, a, e, k, expected, decision, tags, STIPS)


# ---------------------------------------------------------------- controls (must be SUPPORTED)

CONTROLS: tuple[Scenario, ...] = (
    _s(
        "K01",
        "Clean communication claim, support accepted by the AI reviewer",
        "control",
        comm([item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED)]),
        expected=Verdict.SUPPORTED,
        tags=("ai_reviewed",),
    ),
    _s(
        "K02",
        "Clean communication claim, support accepted by an expert",
        "control",
        comm([item(1, MSG, Stance.SUPPORTS, S.ACCEPTED)]),
        expected=Verdict.SUPPORTED,
        tags=("confirmed",),
    ),
    _s(
        "K03",
        "Clean claim with an irrelevant open item alongside the accepted support",
        "control",
        comm(
            [
                item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED),
                item(
                    2, MSG, Stance.IRRELEVANT, S.OPEN, quote="ok", record_id="msg:item1:Chats!947"
                ),
            ]
        ),
        expected=Verdict.SUPPORTED,
        tags=("ai_reviewed",),
    ),
)

# ---------------------------------------------------------------- red team (never SUPPORTED)

_ANSWER = assumption(1, AssumptionKind.EVENT, "Item 1 has an outgoing message with that text")
_HANDLE = assumption(
    3, AssumptionKind.IDENTITY, "Telegram user 5551234 (@northstar) is ALEXANDER SOKOLOV"
)
_MEANING = assumption(4, AssumptionKind.MEANING, "'the package' refers to narcotics")
_ABSENT = assumption(
    1, AssumptionKind.COMPLETENESS, "No messages or calls between them from March 20 to 23"
)
_AUTHOR = assumption(
    3, AssumptionKind.IDENTITY, "PETROV personally wrote the dp_garage Instagram message"
)
_FOREIGN = assumption(
    1, AssumptionKind.EVENT, "A message exists on Item 2", claim_id=OTHER_CLAIM_ID
)
_TRANSLATED = assumption(
    1, AssumptionKind.MEANING, "The Russian message says he is worried about Marcus"
)

RED_TEAM: tuple[Scenario, ...] = (
    _s(
        "R01",
        "Supporting label never reviewed (status open)",
        "unreviewed",
        comm([item(1, MSG, Stance.SUPPORTS, S.OPEN)]),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R02",
        "Supporting label dismissed by the reviewer",
        "dismissed",
        comm([item(1, MSG, Stance.SUPPORTS, S.DISMISSED)]),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R03",
        "Only support is an inferred record (machine translation), even though accepted",
        "inferred_record",
        (
            claim("PETROV wrote that he was worried about Marcus.", ClaimType.CONTENT_MEANING),
            [*OWN, _TRANSLATED],
            [
                item(
                    1,
                    _TRANSLATED,
                    Stance.SUPPORTS,
                    S.AI_ACCEPTED,
                    quote="I am worried about Marcus",
                    record_id="tr:item1:Chats!1201",
                    tier=T.INFERRED,
                )
            ],
            [],
        ),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R04",
        "No assumptions at all: 'every core assumption is covered' is vacuously true",
        "vacuous_no_assumptions",
        comm([item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED)], checks=[], assumptions=[]),
    ),
    _s(
        "R05",
        "Only non-core assumptions, all covered: nothing core was ever tested",
        "vacuous_no_core",
        comm(
            [
                item(
                    1,
                    assumption(1, AssumptionKind.EVENT, "x", core=False),
                    Stance.SUPPORTS,
                    S.AI_ACCEPTED,
                )
            ],
            checks=[],
            assumptions=[assumption(1, AssumptionKind.EVENT, "x", core=False)],
        ),
    ),
    _s(
        "R06",
        "Handle owner still inferred: nothing covers who @northstar is",
        "handle_owner",
        (
            claim('PETROV wrote to ALEXANDER SOKOLOV: "need 2 more by friday".'),
            [*OWN, WHO, MSG, WHEN, _HANDLE],
            [item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED)],
            [ok_when, ok_who],
        ),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R07",
        "Time check fails (UTC date printed, local date differs) despite accepted support",
        "timezone",
        comm(
            [item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED)],
            checks=[check(1, WHEN, CheckOutcome.FAIL), ok_who],
        ),
        expected=Verdict.CONTRADICTED,
    ),
    _s(
        "R08",
        "Time check inconclusive and nothing else covers the time assumption",
        "time_inconclusive",
        comm(
            [item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED)],
            checks=[check(1, WHEN, CheckOutcome.INCONCLUSIVE), ok_who],
        ),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R09",
        "Absence claim on a curated report: coverage check inconclusive, model 'supports' silence",
        "absence_curated",
        (
            claim("PETROV and REYES had no contact from March 20 to 23, 2026.", ClaimType.ABSENCE),
            [*OWN, _ABSENT],
            [
                item(
                    1,
                    _ABSENT,
                    Stance.SUPPORTS,
                    S.AI_ACCEPTED,
                    quote="night",
                    record_id="msg:item1:Chats!1310",
                )
            ],
            [check(1, _ABSENT, CheckOutcome.INCONCLUSIVE, "absence_vs_coverage")],
        ),
        decision="A completeness (absence) assumption is covered only by a passing coverage "
        "check, never by a model label: silence has no quote to verify.",
    ),
    _s(
        "R10",
        "Open complicating item (sarcasm flagged) next to an accepted support",
        "open_complicates",
        comm(
            [
                item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED),
                item(
                    2,
                    MSG,
                    Stance.COMPLICATES,
                    S.OPEN,
                    quote="fine",
                    record_id="msg:item1:Chats!950",
                ),
            ]
        ),
    ),
    _s(
        "R11",
        "Open model-only 'contradicts' on an observed record next to an accepted support",
        "open_contradicts",
        comm(
            [
                item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED),
                item(
                    2,
                    WHEN,
                    Stance.CONTRADICTS,
                    S.OPEN,
                    quote="friday hard. saturday",
                    record_id="msg:item1:Chats!949",
                ),
            ]
        ),
    ),
    _s(
        "R12",
        "Accepted item whose stance is 'complicates', not 'supports'",
        "accepted_not_support",
        comm([item(1, MSG, Stance.COMPLICATES, S.AI_ACCEPTED)]),
    ),
    _s(
        "R13",
        "Accepted item whose stance is 'irrelevant'",
        "accepted_irrelevant",
        comm([item(1, MSG, Stance.IRRELEVANT, S.ACCEPTED)]),
    ),
    _s(
        "R14",
        "Accepted support belongs to another claim's assumption; this claim's is uncovered",
        "foreign_evidence",
        comm([item(1, _FOREIGN, Stance.SUPPORTS, S.AI_ACCEPTED)]),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R15",
        "Passing check points at an assumption id that is not in the claim",
        "foreign_check",
        comm(
            [item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED)],
            checks=[check(1, _FOREIGN, CheckOutcome.PASS), ok_who],
        ),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R16",
        "Two core assumptions; accepted support covers only the first",
        "partial",
        comm([item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED)], checks=[ok_who]),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R17",
        "Sender check fails (group chat: someone else sent it) despite accepted support",
        "group_sender",
        comm(
            [item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED)],
            checks=[ok_when, ok_who, check(2, MSG, CheckOutcome.FAIL, "sender")],
        ),
        expected=Verdict.CONTRADICTED,
    ),
    _s(
        "R18",
        "Identity assumption covered only by an AI-reviewed item (reviewer must not confirm "
        "identity)",
        "ai_identity",
        (
            claim("The Telegram user @northstar is ALEXANDER SOKOLOV.", ClaimType.IDENTITY),
            [_HANDLE],
            [
                item(
                    1,
                    _HANDLE,
                    Stance.SUPPORTS,
                    S.AI_ACCEPTED,
                    quote="ok sasha",
                    record_id="msg:item2:Chats!1102",
                )
            ],
            [],
        ),
        decision="An identity assumption is never covered by AI-reviewed evidence alone; it "
        "needs a passing deterministic check or expert acceptance (CLAUDE.md: the AI reviewer "
        "never confirms identity links).",
    ),
    _s(
        "R19",
        "Shared account: authorship assumption covered only by an AI-reviewed item",
        "shared_account",
        (
            claim('On March 18, PETROV, using dp_garage, told REYES "got the money".'),
            [*OWN, _ANSWER, _AUTHOR],
            [
                item(
                    1,
                    _ANSWER,
                    Stance.SUPPORTS,
                    S.AI_ACCEPTED,
                    quote="got the money",
                    record_id="msg:item1:Chats!1405",
                ),
                item(
                    2,
                    _AUTHOR,
                    Stance.SUPPORTS,
                    S.AI_ACCEPTED,
                    quote="got the money",
                    record_id="msg:item1:Chats!1405",
                ),
            ],
            [],
        ),
        decision="Same rule as R18.",
    ),
    _s(
        "R22",
        "Meaning assumption with no evidence, while the event and time are fully covered",
        "meaning_uncovered",
        (
            claim(
                "The package @northstar mentioned on March 12 contained narcotics.",
                ClaimType.CONTENT_MEANING,
            ),
            [*OWN, WHO, MSG, WHEN, _MEANING],
            [item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED)],
            [ok_when, ok_who],
        ),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R23",
        "Expert dismissed both copies of the support (a human decision overrides the AI)",
        "human_override",
        comm(
            [
                item(1, MSG, Stance.SUPPORTS, S.DISMISSED),
                item(2, MSG, Stance.SUPPORTS, S.DISMISSED, record_id="msg:item2:Chats!301"),
            ]
        ),
        expected=Verdict.UNPROVEN,
    ),
    _s(
        "R24",
        "Model 'contradicts' on a meaning assumption plus accepted support elsewhere",
        "meaning_contradicts",
        (
            claim(
                "The package @northstar mentioned on March 12 contained narcotics.",
                ClaimType.CONTENT_MEANING,
            ),
            [*OWN, MSG, _MEANING],
            [
                item(1, MSG, Stance.SUPPORTS, S.AI_ACCEPTED),
                item(
                    2,
                    _MEANING,
                    Stance.CONTRADICTS,
                    S.OPEN,
                    quote="the package will be at marcs",
                    record_id="msg:item1:Chats!951",
                ),
            ],
            [],
        ),
    ),
)

# Tier smuggling: an item whose tier claims a review its status does not show. Contracts v0.2
# refuses to build such an item at all (EvidenceItem.tier is the record's tier), which
# tests/adversarial/test_rules_red_team.py checks instead.
if not V02:
    RED_TEAM += (
        _s(
            "R20",
            "Item tier says ai_reviewed but its status is open (tier smuggling)",
            "tier_smuggling",
            comm([item(1, MSG, Stance.SUPPORTS, S.OPEN, tier=T.AI_REVIEWED)]),
            expected=Verdict.UNPROVEN,
        ),
        _s(
            "R21",
            "Item tier says confirmed but its status is open (tier smuggling)",
            "tier_smuggling",
            comm([item(1, MSG, Stance.SUPPORTS, S.OPEN, tier=T.CONFIRMED)]),
            expected=Verdict.UNPROVEN,
        ),
    )

ALL: tuple[Scenario, ...] = CONTROLS + RED_TEAM

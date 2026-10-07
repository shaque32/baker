"""case01 assumption spec for the gold-claims eval mode. SYNTHETIC. DRAFT until Arsh signs.

For each of case01's 20 gold claims: the assumptions the claim rests on, written as the fixed
templates of core/audit/assumptions.py (TEMPLATES_VERSION 1.0.0, PR #16) with typed
AssumptionParams (contracts v0.2, PR #15). In gold-claims mode the pipeline uses these in
place of a model filling the templates, so the eval measures checks, stance, review and rules
on assumptions a human signed. The .jsonl has one assumption per line, in the format
eval/run_pipeline.py --assumption-spec reads; gaps live in this file and the signing sheet.

Each assumption also records what its deterministic check should find on case01
(pass, fail, inconclusive), or None for model-only templates. Those expectations come from
the gold rationale, never from running the checks, and a test runs the checks against them.

Gaps are parts of a claim no template can express yet. They are listed per claim so Arsh can
see what the engine cannot test; nothing is invented to paper over them.

Usage: python -m eval.probe_draft.case01_assumptions   (writes the .jsonl and the signing sheet)
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

DRAFT_LABEL = "DRAFT (agent proposal, not approved by Arsh)"
TEMPLATES_VERSION = "1.0.0"
NY = "America/New_York"
HERE = Path(__file__).resolve().parent
JSONL = HERE / "case01_assumptions.jsonl"
SHEET = HERE / "CASE01_ASSUMPTIONS_REVIEW.md"

PETROV, REYES, SOKOLOV = "person:petrov", "person:reyes", "person:sokolov"
NORTHSTAR = ("acct:item1:Telegram:5551234", "acct:item2:Telegram:5551234")
MARC_0122 = ("acct:item1:Phone:+12125550122",)
DP_GARAGE = ("acct:item1:Instagram:dp_garage", "acct:item2:Instagram:dp_garage")
ITEM1, ITEM2 = "dev:item1", "dev:item2"

Expect = Literal["pass", "fail", "inconclusive"] | None


def window(start: str, end_exclusive: str, raw: str, tz: str = NY) -> dict[str, str]:
    """Wall-clock [start, end_exclusive) in tz -> the contract's inclusive UTC TimeWindow.

    Same arithmetic as core.audit.assumptions.local_window; kept here so the spec builds
    without that module.
    """
    zone = ZoneInfo(tz)
    s = datetime.fromisoformat(start).replace(tzinfo=zone).astimezone(UTC)
    e = datetime.fromisoformat(end_exclusive).replace(tzinfo=zone).astimezone(UTC)
    e -= timedelta(microseconds=1)
    return {
        "start_utc": s.isoformat().replace("+00:00", "Z"),
        "end_utc": e.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "tz": tz,
        "raw": raw,
    }


@dataclass(frozen=True)
class A:
    template_id: str
    params: dict[str, object]
    expect: Expect
    note: str
    is_core: bool = True


@dataclass(frozen=True)
class ClaimSpec:
    claim_id: str
    assumptions: tuple[A, ...]
    gaps: tuple[str, ...] = field(default=())


def P(**kw: object) -> dict[str, object]:
    """AssumptionParams as JSON: tuples become lists, empty fields are left out."""
    return {k: list(v) if isinstance(v, tuple | list) else v for k, v in kw.items()}


SPEC: tuple[ClaimSpec, ...] = (
    ClaimSpec(
        "C01",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM1], quoted_text="Marc Garage", account_ids=MARC_0122),
                "pass",
                "The contact row is observed on Item 1.",
            ),
        ),
    ),
    ClaimSpec(
        "C02",
        (
            A(
                "same_account",
                P(channels=["Telegram"], handles=["@alex92", "@northstar"]),
                "pass",
                "Both handles resolve to Telegram user id 5551234.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="hey its sasha. marc gave me ur name",
                    account_ids=NORTHSTAR,
                    window=window("2026-02-20", "2026-02-21", "February 20, 2026"),
                ),
                "pass",
                "The first message: 7:02 PM EST Feb 20, printed 2/21 in UTC.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="not now",
                    person_ids=[PETROV],
                    window=window("2026-03-28", "2026-03-29", "March 28, 2026"),
                ),
                "pass",
                "The last message: 6:01 PM EDT Mar 28.",
            ),
        ),
        gaps=(
            "The affidavit quotes no words; quoted_text picks the first and last messages the "
            "expert would point to. That none came before or after can't be shown on a curated "
            "report and isn't needed for 'exchanged messages between'.",
        ),
    ),
    ClaimSpec(
        "C03",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM1],
                    person_ids=[PETROV],
                    account_ids=NORTHSTAR,
                    channels=["Telegram"],
                    expected_count=13,
                    count_op="eq",
                    window=window(
                        "2026-03-10", "2026-04-01", "From March 10 through March 31, 2026"
                    ),
                ),
                "pass",
                "13 rows by user id 5551234, local dates.",
            ),
        ),
    ),
    ClaimSpec(
        "C04",
        (
            A(
                "no_contact",
                P(
                    person_ids=[PETROV],
                    account_ids=NORTHSTAR,
                    window=window("2026-01-01", "2026-03-12", "before March 12, 2026"),
                ),
                "fail",
                "User id 5551234 wrote to PETROV from Feb 20 (as @alex92).",
            ),
        ),
        gaps=(
            "The seizure date ('two days after the seizure') comes from the affidavit, not the "
            "phones, and is not tested.",
        ),
    ),
    ClaimSpec(
        "C05",
        (
            A(
                "sender",
                P(quoted_text="need 2 more by friday", person_ids=[PETROV]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="need 2 more by friday",
                    person_ids=[PETROV],
                    window=window("2026-03-12", "2026-03-13", "On March 12, 2026"),
                ),
                "pass",
                "8:03 PM EDT Mar 12, printed 3/13 in UTC.",
            ),
        ),
        gaps=(
            "The recipient (@northstar) is not a separate assumption: the sender template names "
            "one party.",
        ),
    ),
    ClaimSpec(
        "C06",
        (
            A(
                "sender",
                P(quoted_text="the package will be at marcs", account_ids=NORTHSTAR),
                "pass",
                "Sent by user id 5551234.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="the package will be at marcs",
                    account_ids=NORTHSTAR,
                    window=window("2026-03-12", "2026-03-13", "on March 12, 2026"),
                ),
                "pass",
                "8:11 PM EDT Mar 12, printed 3/13 in UTC.",
            ),
            A(
                "meaning",
                P(quoted_text="the package will be at marcs"),
                None,
                "That 'the package' held narcotics. Nothing on either phone says so (rule 1).",
            ),
        ),
    ),
    ClaimSpec(
        "C07",
        (
            A(
                "sender",
                P(quoted_text="lets meet monday 8pm. lot behind kings plaza", person_ids=[REYES]),
                "pass",
                "REYES proposed it.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="lets meet monday 8pm. lot behind kings plaza",
                    person_ids=[REYES],
                    window=window("2026-03-06", "2026-03-07", "On March 6, 2026"),
                ),
                "pass",
                "6:12 PM EST Mar 6.",
            ),
            A("sender", P(quoted_text="ok works", person_ids=[PETROV]), "pass", "PETROV's reply."),
            A(
                "meaning",
                P(quoted_text="ok works", person_ids=[PETROV, REYES]),
                None,
                "'ok works' accepts the proposal, and 'monday' sent on Friday Mar 6 means Mar 9.",
            ),
        ),
        gaps=(
            "The affidavit quotes no words; quoted_text here identifies the messages the expert "
            "would point to. Only 'monday' = Mar 9 is derived; no template computes weekdays.",
        ),
    ),
    ClaimSpec(
        "C08",
        (
            A("role", P(person_ids=[PETROV]), None, "That PETROV chose the location."),
            A(
                "sender",
                P(quoted_text="lets meet monday 8pm. lot behind kings plaza", person_ids=[PETROV]),
                "fail",
                "The only message naming the place was sent by REYES.",
            ),
        ),
        gaps=(
            "Reads the written record only; an off-phone conversation cannot be excluded, so "
            "the report should say 'the written record shows'.",
        ),
    ),
    ClaimSpec(
        "C09",
        (
            A(
                "record_time",
                P(
                    channels=["call"],
                    person_ids=[PETROV],
                    account_ids=MARC_0122,
                    device_ids=[ITEM1],
                    window=window(
                        "2026-03-09T19:50",
                        "2026-03-09T20:06",
                        "At about 7:58 p.m. on March 9, 2026",
                    ),
                ),
                "pass",
                "Outgoing call 7:58:02 PM EDT, printed 11:58 PM UTC.",
            ),
        ),
        gaps=(
            "Call duration ('about two minutes', 00:02:03) has no template or AssumptionParams "
            "field, and calls are not quotable, so nothing tests it. Under rules that need "
            "every core part covered, C09 cannot reach SUPPORTED until a duration check "
            "exists. Proposed fix: a call_duration template with min/max seconds (contracts "
            "and thread 4).",
        ),
    ),
    ClaimSpec(
        "C10",
        (
            A("sender", P(quoted_text="its done", person_ids=[PETROV]), "pass", "PETROV sent it."),
            A(
                "record_time",
                P(
                    quoted_text="its done",
                    person_ids=[PETROV, REYES],
                    window=window(
                        "2026-03-05T02:31", "2026-03-05T02:32", "At 2:31 a.m. on March 5, 2026"
                    ),
                ),
                "fail",
                "Printed 2:31 AM UTC; on the phone it was 9:31 PM EST Mar 4.",
            ),
        ),
    ),
    ClaimSpec(
        "C11",
        (
            A(
                "record_time",
                P(
                    channels=["call"],
                    person_ids=[REYES],
                    window=window(
                        "2026-03-14T22:05", "2026-03-14T22:06", "At 10:05 p.m. on March 14, 2026"
                    ),
                ),
                "pass",
                "The Luis call on Item 2, 10:05:44 PM EDT.",
                is_core=False,
            ),
            A(
                "record_time",
                P(
                    quoted_text="move it tonight",
                    person_ids=[PETROV],
                    window=window(
                        "2026-03-14T22:05", "2026-03-15T06:00", "after the 10:05 p.m. call"
                    ),
                ),
                "fail",
                "Sent 9:50:20 PM EDT, 15 minutes before the call. Needs both phones.",
            ),
        ),
        gaps=(
            "That the call warned him about police is inferred from REYES's later SMS and is "
            "not needed: the order alone contradicts the claim.",
        ),
    ),
    ClaimSpec(
        "C12",
        (
            A(
                "sender",
                P(quoted_text="dont text me about it, use telegram", person_ids=[PETROV]),
                "pass",
                "Outgoing SMS on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="dont text me about it, use telegram",
                    person_ids=[PETROV],
                    window=window("2026-03-19", "2026-03-20", "On March 19, 2026"),
                ),
                "pass",
                "2:22 PM EDT Mar 19.",
            ),
        ),
        gaps=("The recipient (REYES) is not a separate assumption.",),
    ),
    ClaimSpec(
        "C13",
        (
            A(
                "role",
                P(person_ids=[PETROV, REYES]),
                None,
                "That PETROV directed REYES's handling and movement.",
            ),
            A(
                "meaning",
                P(quoted_text="dont text me about it, use telegram"),
                None,
                "That 'it' is narcotics; not established (as C06).",
            ),
        ),
    ),
    ClaimSpec(
        "C14",
        (
            A(
                "no_contact",
                P(
                    person_ids=[PETROV, REYES],
                    window=window(
                        "2026-03-20", "2026-03-24", "between March 20 and March 23, 2026"
                    ),
                ),
                "fail",
                "SMS, Telegram and an unanswered call fall inside the window.",
            ),
        ),
    ),
    ClaimSpec(
        "C15",
        (
            A(
                "event",
                P(
                    person_ids=[PETROV],
                    channels=["WhatsApp"],
                    window=window(
                        "2026-03-20", "2026-03-24", "between March 20 and March 23, 2026"
                    ),
                ),
                None,
                "That PETROV deleted WhatsApp messages in the window. No WhatsApp row exists "
                "there and none is flagged deleted.",
            ),
        ),
        gaps=(
            "No template lets an event claim assert that messages existed in a window "
            "(message_count serves count and communication claims only), so the existence "
            "half is folded into the model-only event assumption.",
        ),
    ),
    ClaimSpec(
        "C16",
        (
            A(
                "sender",
                P(quoted_text="got the money, come get it", account_ids=DP_GARAGE),
                "pass",
                "The account dp_garage sent it.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="got the money, come get it",
                    account_ids=DP_GARAGE,
                    window=window("2026-03-18", "2026-03-19", "On March 18, 2026"),
                ),
                "pass",
                "5:40 PM EDT Mar 18.",
            ),
            A(
                "authorship",
                P(person_ids=[PETROV], account_ids=DP_GARAGE),
                None,
                "That PETROV personally wrote it. The same account wrote 'its ilya btw' that day.",
            ),
        ),
    ),
    ClaimSpec(
        "C17",
        (
            A(
                "sender",
                P(quoted_text="я волнуюсь за Маркуса", person_ids=[PETROV]),
                "pass",
                "Outgoing WhatsApp on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="я волнуюсь за Маркуса",
                    person_ids=[PETROV],
                    window=window("2026-03-11", "2026-03-12", "On March 11, 2026"),
                ),
                "pass",
                "10:15 PM EDT Mar 11, printed 3/12 in UTC.",
            ),
            A(
                "meaning",
                P(quoted_text="я волнуюсь за Маркуса"),
                None,
                "That it says he is worried about Marcus. Needs a human-confirmed translation "
                "(rule 3).",
            ),
        ),
        gaps=("The recipient (the contact saved as Катя) is not a separate assumption.",),
    ),
    ClaimSpec(
        "C18",
        (
            A(
                "person_identity",
                P(person_ids=[SOKOLOV], account_ids=NORTHSTAR, handles=["@northstar"]),
                None,
                "That Telegram user 5551234 is ALEXANDER SOKOLOV. Nothing names a surname.",
            ),
        ),
    ),
    ClaimSpec(
        "C19",
        (
            A(
                "person_identity",
                P(
                    person_ids=["person:alex_0182"],
                    account_ids=(*NORTHSTAR, "acct:item1:SMS:+12125550182"),
                ),
                None,
                "That Telegram user 5551234 and the 'Alex' at +12125550182 on Item 1 are one "
                "person. Contradicted only by a stance label on 'who is alex turner?' (rule 2).",
            ),
        ),
        gaps=(
            "Code cannot prove two accounts are one person, and a different identifier is not "
            "a fail (rule 2), so this rests on the model. 'Alex' is a saved phone number, not a "
            "Telegram handle, so same_account does not apply. person:alex_0182 is a placeholder "
            "for the person the affidavit says both accounts belong to.",
        ),
    ),
    ClaimSpec(
        "C20",
        (
            A(
                "sender",
                P(quoted_text="got the tickets. 4 of them", person_ids=[PETROV]),
                "pass",
                "Outgoing SMS on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="got the tickets. 4 of them",
                    person_ids=[PETROV],
                    window=window("2026-03-25", "2026-03-26", "On March 25, 2026"),
                ),
                "pass",
                "12:42 PM EDT Mar 25.",
            ),
            A(
                "meaning",
                P(quoted_text="got the tickets. 4 of them"),
                None,
                "That 'tickets' means narcotics. The thread is about concert tickets (rule 1).",
            ),
        ),
    ),
)


# ---------------------------------------------------------------- build


def gold_by_id() -> dict[str, dict]:
    path = HERE.parents[1] / "eval/gold/case01/gold.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {r["claim_id"]: r for r in rows}


def records() -> list[dict]:
    gold = gold_by_id()
    out = []
    for c in SPEC:
        out.append(
            {
                "claim_id": c.claim_id,
                "claim_type": gold[c.claim_id]["claim_type"],
                "gold_verdict": gold[c.claim_id]["gold_verdict"],
                "assumptions": [
                    {
                        "template_id": a.template_id,
                        "template_version": TEMPLATES_VERSION,
                        "is_core": a.is_core,
                        "params": a.params,
                        "expected_check": a.expect,
                        "note": a.note,
                    }
                    for a in c.assumptions
                ],
                "gaps": list(c.gaps),
                "labeled_by": DRAFT_LABEL,
            }
        )
    return out


def render_jsonl(recs: list[dict]) -> str:
    """One assumption per line, the format eval/run_pipeline.py --assumption-spec reads:
    claim_id, template_id, params, is_core; the other keys are for review and tests."""
    rows = [
        {"claim_id": r["claim_id"], **a, "labeled_by": r["labeled_by"]}
        for r in recs
        for a in r["assumptions"]
    ]
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def _params_text(p: dict) -> str:
    parts = []
    for k, v in p.items():
        if k == "window":
            parts.append(f'window: "{v["raw"]}" ({v["tz"]}, local wall clock)')
        elif isinstance(v, list):
            parts.append(f"{k}: {', '.join(str(x) for x in v)}")
        else:
            parts.append(f"{k}: {v}")
    return "<br>".join(parts).replace("|", "\\|")


def render_sheet(recs: list[dict]) -> str:
    gold = gold_by_id()
    lines = [
        "# case01 assumptions: DRAFT for Arsh's line-by-line review",
        "",
        "**Not gold.** In the gold-claims eval mode the pipeline uses these assumptions instead "
        "of a model filling the templates, so they are signed like gold. Thread 1 copies the "
        "signed file into `eval/gold/case01/`.",
        "",
        "How to read it:",
        "",
        "- Each claim is broken into the fixed templates the engine can test "
        "(`core/audit/assumptions.py`). Parameters are typed; checks never read the sentence.",
        "- **Check** is what the deterministic check should find on case01: pass, fail or "
        "inconclusive. A dash means no check exists for that template, so only an accepted "
        "stance label can cover it.",
        "- Phone ownership (Item 1 PETROV, Item 2 REYES) is the confirmed case stipulation, not "
        "an assumption here.",
        "- **Gaps** are parts of the claim no template can express yet. They are listed, not "
        "papered over.",
        "- Windows are the document's dates as wall-clock time in America/New_York; the "
        "`.jsonl` holds their UTC form.",
        "",
        "| Claim | Gold | Assumptions | Core checks expected | Gaps | Approve? |",
        "|---|---|---|---|---|---|",
    ]
    for r in recs:
        exp = [a["expected_check"] or "-" for a in r["assumptions"] if a["is_core"]]
        lines.append(
            f"| {r['claim_id']} | {r['gold_verdict']} | {len(r['assumptions'])} | "
            f"{', '.join(exp)} | {len(r['gaps']) or ''} | [ ] |"
        )
    for r in recs:
        lines += [
            "",
            f"## {r['claim_id']}: gold {r['gold_verdict']}",
            "",
            f"> {gold[r['claim_id']]['text']}",
            "",
            "| # | Template | Core | Parameters | Check | Why |",
            "|---|---|---|---|---|---|",
        ]
        for i, a in enumerate(r["assumptions"], start=1):
            lines.append(
                f"| {i} | `{a['template_id']}` | {'yes' if a['is_core'] else 'no'} | "
                f"{_params_text(a['params'])} | {a['expected_check'] or '-'} | "
                f"{a['note'].replace('|', '/')} |"
            )
        for g in r["gaps"]:
            lines += ["", f"Gap: {g}"]
        lines += ["", "Arsh: [ ] agree  [ ] change ______  Note:"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    recs = records()
    JSONL.write_text(render_jsonl(recs), encoding="utf-8")
    SHEET.write_text(render_sheet(recs), encoding="utf-8")
    print(f"wrote {JSONL.name} and {SHEET.name}: {len(recs)} claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())

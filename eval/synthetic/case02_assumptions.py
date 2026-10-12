"""case02 assumption spec for the gold-claims eval mode. SYNTHETIC. DRAFT until Arsh signs.

HIDDEN: builder threads must not read this file (eval/synthetic/case02*). It names case02's
claims, records and expected check results.

Same format and method as eval/probe_draft/case01_assumptions.py: for each of case02's 20 draft
gold claims, the assumptions it rests on, written as the fixed templates of
core/audit/assumptions.py with typed AssumptionParams. In gold-claims mode the pipeline fills
assumptions from this sheet instead of a model, so it is signed like gold. The .jsonl has one
assumption per line, in the format eval/run_pipeline.py --assumption-spec reads.

Expected check results come from the draft answer key's reasoning
(eval/synthetic/case02/ANSWER_KEY_DRAFT.md), never from running the checks; a test runs the
checks against them. Gaps are parts of a claim no template can express; where a gap means the
engine cannot reach the draft gold verdict, the claim is marked a known miss, never papered
over with a template that tests something else.

The affidavit states its times in Central Time (paragraph 23), so every window is wall-clock
America/Chicago (draft labeling rule 5). People: person:brandt (Item 1's owner) and
person:quintero (Item 2's owner) map to the case's device-owner stipulations; everyone else is
named by account, as the affidavit names them by number (paragraph 24).

Usage: python -m eval.synthetic.case02_assumptions   (writes the .jsonl and the signing sheet)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from eval.probe_draft.case01_assumptions import A, ClaimSpec, P, _params_text, window

DRAFT_LABEL = "DRAFT (agent proposal, not approved by Arsh)"
TEMPLATES_VERSION = "1.0.0"
CT = "America/Chicago"
HERE = Path(__file__).resolve().parent / "case02"
JSONL = HERE / "case02_assumptions.jsonl"
SHEET = HERE / "CASE02_ASSUMPTIONS_REVIEW.md"
GOLD_DRAFT = HERE / "draft_gold.jsonl"

BRANDT, QUINTERO = "person:brandt", "person:quintero"
ITEM1, ITEM2 = "dev:item1", "dev:item2"
WA = "@s.whatsapp.net"
HALE_WA = (f"acct:item1:WhatsApp:13125550131{WA}", f"acct:item2:WhatsApp:13125550131{WA}")
CHINO1 = ("acct:item1:Phone:+13125550143", f"acct:item1:WhatsApp:13125550143{WA}")
CHINO2 = ("acct:item2:Phone:+13125550158", f"acct:item2:WhatsApp:13125550158{WA}")
KYLE_SMS = ("acct:item1:SMS:+13125550150",)
MAMA_WA = (f"acct:item2:WhatsApp:13125550173{WA}",)
MARISOL_WA = (f"acct:item2:WhatsApp:13125550136{WA}",)

# Known misses: claims whose draft gold verdict the engine cannot reach with today's templates.
# Listed on the signing sheet so a lower case02 score is read for what it is.
KNOWN_MISSES = {
    "C10": "supported in the draft key; the engine can only reach unproven (no template "
    "counts records by the report's deleted flag).",
}


def day(date: str, next_day: str, raw: str) -> dict[str, str]:
    return window(date, next_day, raw, tz=CT)


SPEC: tuple[ClaimSpec, ...] = (
    ClaimSpec(
        "C01",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM1], quoted_text="Chino", account_ids=[CHINO1[0]]),
                "pass",
                "Item 1's Contacts sheet has 'Chino' with +13125550143.",
            ),
        ),
    ),
    ClaimSpec(
        "C02",
        (
            A(
                "contact_entry",
                P(
                    device_ids=[ITEM1],
                    quoted_text="Rafa",
                    account_ids=["acct:item1:Phone:+13125550125"],
                ),
                "pass",
                "Item 1 saves +13125550125 as 'Rafa', the name its WhatsApp rows show.",
            ),
            A(
                "sender",
                P(quoted_text="where we meeting", person_ids=[QUINTERO], channels=["WhatsApp"]),
                "pass",
                f"On Item 1 the group message is from 13125550125{WA} Rafa; Item 2 lists that "
                "identifier as its own WhatsApp account, so the sender is Item 2's account.",
            ),
        ),
        gaps=(
            "The claim is about accounts. The sender check matches the account identifier "
            "across the two phones; QUINTERO enters only through the Item 2 ownership "
            "stipulation, which the key also takes as given.",
        ),
    ),
    ClaimSpec(
        "C03",
        (
            A(
                "sender",
                P(quoted_text="unit 112 at the storage on 4th. code 0419", person_ids=[BRANDT]),
                "pass",
                "Outgoing SMS from +13125550119 on Item 1; Item 2's copy is from the same number.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="unit 112 at the storage on 4th. code 0419",
                    person_ids=[BRANDT, QUINTERO],
                    window=window(
                        "2026-03-09T20:05",
                        "2026-03-09T20:26",
                        "At about 8:15 p.m. on March 9, 2026",
                        tz=CT,
                    ),
                ),
                "pass",
                "Printed 3/10 1:15:33 AM UTC on Item 1: 8:15:33 PM CDT Mar 9 (DST began Mar 8). "
                "'About 8:15' read as 8:05 to 8:25.",
            ),
        ),
    ),
    ClaimSpec(
        "C04",
        (
            A(
                "sender",
                P(
                    quoted_text="drop is at the storage on 4th, bring the van at 6",
                    person_ids=[BRANDT],
                    channels=["WhatsApp"],
                ),
                "fail",
                f"Sent by 13125550131{WA} Devon (HALE's number, paragraph 24), incoming on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="drop is at the storage on 4th, bring the van at 6",
                    window=day("2026-03-13", "2026-03-14", "On March 13, 2026"),
                ),
                "pass",
                "3:04:51 PM CDT Mar 13. The date is right; the sender is not.",
                is_core=False,
            ),
        ),
        gaps=(
            "The group name 'Westside Flips' is not a template parameter; the quoted words "
            "pick the message.",
        ),
    ),
    ClaimSpec(
        "C05",
        (
            A(
                "sender",
                P(quoted_text="yeah im the kingpin lol", person_ids=[BRANDT]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="yeah im the kingpin lol",
                    person_ids=[BRANDT],
                    window=day("2026-03-06", "2026-03-07", "On March 6, 2026"),
                ),
                "pass",
                "Printed 3/7 3:40:12 AM UTC: 9:40:12 PM CST Mar 6 (before DST).",
            ),
            A(
                "meaning",
                P(quoted_text="yeah im the kingpin lol", person_ids=[BRANDT]),
                None,
                "That it admits running a theft operation. It answers a joke and ends in 'lol' "
                "(rule 1: complicates, not ruled out).",
            ),
        ),
    ),
    ClaimSpec(
        "C06",
        (
            A(
                "sender",
                P(quoted_text="bring the cash friday", person_ids=[BRANDT]),
                "pass",
                "Both copies (Item 1 and Item 2) are from +13125550119.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="bring the cash friday",
                    person_ids=[BRANDT, QUINTERO],
                    window=day("2026-03-11", "2026-03-12", "On March 11, 2026"),
                ),
                "pass",
                "1:02:48 PM CDT Mar 11.",
            ),
            A(
                "meaning",
                P(quoted_text="bring the cash friday", person_ids=[BRANDT]),
                None,
                "That the demand was BRANDT's own. The message reads 'wade said \"bring the cash "
                "friday\"': he reports Wade's words (rule 1).",
            ),
        ),
    ),
    ClaimSpec(
        "C07",
        (
            A(
                "sender",
                P(quoted_text="no. i never sold chino anything. drop it", person_ids=[BRANDT]),
                "pass",
                "Outgoing SMS on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="no. i never sold chino anything. drop it",
                    person_ids=[BRANDT],
                    account_ids=KYLE_SMS,
                    window=day("2026-03-24", "2026-03-25", "On March 24, 2026"),
                ),
                "pass",
                "To +13125550150 Kyle (MERCER, paragraph 24); printed 3/25 12:09:44 AM UTC, "
                "7:09:44 PM CDT Mar 24.",
            ),
            A(
                "meaning",
                P(quoted_text="no. i never sold chino anything. drop it", person_ids=[BRANDT]),
                None,
                "That it admits selling tools to Chino. Its words deny it, which rules the "
                "admission out (rule 1); only an expert-accepted item can contradict a meaning.",
            ),
        ),
    ),
    ClaimSpec(
        "C08",
        (
            A(
                "event",
                P(
                    person_ids=[BRANDT, QUINTERO],
                    channels=["call"],
                    device_ids=[ITEM1],
                    window=day("2026-03-10", "2026-03-15", "between March 10 and March 14, 2026"),
                ),
                None,
                "That they spoke five times. Item 1 has five call records with +13125550125, but "
                "only two connected; two are Missed and one is 00:00:00 (rule 8).",
            ),
            A(
                "record_time",
                P(
                    channels=["call"],
                    person_ids=[BRANDT, QUINTERO],
                    device_ids=[ITEM1],
                    duration_s=[480, 720],
                    window=window(
                        "2026-03-12T21:04",
                        "2026-03-12T21:25",
                        "a call of about ten minutes at 9:14 p.m. on March 12",
                        tz=CT,
                    ),
                ),
                "inconclusive",
                "The 9:14:05 PM CDT call lasted 00:01:02, so no call of 8 to 12 minutes is found. "
                "Calls are matched by parties, so a time check never fails on a call.",
            ),
        ),
        gaps=(
            "No template counts calls or tells a connected call from an attempt (message_count "
            "counts messages). 'Spoke five times' and the duration both rest on the expert "
            "accepting the call records as contradicting.",
        ),
    ),
    ClaimSpec(
        "C09",
        (
            A(
                "event",
                P(
                    person_ids=[QUINTERO],
                    channels=["Telegram"],
                    device_ids=[ITEM2],
                    window=day("2026-03-27", "2026-04-01", "After his arrest on March 27, 2026"),
                ),
                None,
                "That QUINTERO deleted the Telegram messages after Mar 27. The Deleted flag "
                "carries no time and no actor (rule 6).",
            ),
        ),
        gaps=(
            "The window ends when Item 2 was seized (Mar 31, paragraph 22). The arrest time of "
            "day is not stated, so the window starts at the start of Mar 27.",
        ),
    ),
    ClaimSpec(
        "C10",
        (
            A(
                "event",
                P(
                    person_ids=[QUINTERO, BRANDT],
                    channels=["Telegram"],
                    device_ids=[ITEM2],
                ),
                None,
                "That Item 2's report marks six Telegram messages between them Deleted. Six of "
                "the fourteen rows with user 8100219 read Deleted (rule 6).",
            ),
        ),
        gaps=(
            "KNOWN MISS. No template counts records by the report's deleted flag: message_count "
            "counts every message (14 here) and would fail an 'exactly 6'. A count claim needs a "
            "core completeness assumption to be supported (rules 3e), so the engine can reach "
            "only unproven. Fix: a 'flagged_count' template and check in core/audit/.",
        ),
    ),
    ClaimSpec(
        "C11",
        (
            A(
                "no_contact",
                P(
                    person_ids=[QUINTERO],
                    account_ids=HALE_WA,
                    window=day("2026-03-22", "2026-04-01", "from March 22, 2026 onward"),
                ),
                "fail",
                "On Item 1, Item 2's WhatsApp account writes to the group with HALE on Mar 24 and "
                "HALE replies. Item 2's report leaves the group out.",
            ),
        ),
        gaps=(
            "'Onward' is read up to Item 2's seizure on Mar 31. HALE is named by his WhatsApp "
            "account, the only identifier with +13125550131 on either phone.",
        ),
    ),
    ClaimSpec(
        "C12",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM1], quoted_text="Chino", account_ids=[CHINO1[0]]),
                "pass",
                "The contact the claim names: 'Chino', +13125550143.",
            ),
            A(
                "no_contact",
                P(
                    person_ids=[BRANDT],
                    account_ids=CHINO1,
                    window=day("2026-03-17", "2026-04-01", "After March 16, 2026"),
                ),
                "inconclusive",
                "Nothing found after Mar 14, but both reports are curated, so silence cannot "
                "show absence (rule 7).",
            ),
        ),
    ),
    ClaimSpec(
        "C13",
        (
            A(
                "sender",
                P(quoted_text="IMG_4471.jpg", person_ids=[BRANDT], channels=["WhatsApp"]),
                "inconclusive",
                "The message body is empty; the file name is on its attachment row, which the "
                "sender check does not read.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="IMG_4471.jpg",
                    person_ids=[BRANDT],
                    account_ids=[CHINO1[1]],
                    window=day("2026-03-11", "2026-03-12", "On March 11, 2026"),
                ),
                "inconclusive",
                "Same: 2:22:09 PM CDT Mar 11 is on the message, the name on the attachment.",
            ),
        ),
        gaps=(
            "Checks read message bodies only, so an attachment-only message is covered only "
            "when the expert accepts the attachment record (att:item1:Chats!645:1).",
        ),
    ),
    ClaimSpec(
        "C14",
        (
            A(
                "meaning",
                P(quoted_text="IMG_4471.jpg", person_ids=[BRANDT], account_ids=[CHINO1[1]]),
                None,
                "That the file shows the stolen generators. The report has its name only: no "
                "image, hash or type.",
            ),
        ),
    ),
    ClaimSpec(
        "C15",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM1], quoted_text="Chino", account_ids=[CHINO1[0]]),
                "pass",
                "Item 1: 'Chino' is +13125550143.",
            ),
            A(
                "contact_entry",
                P(device_ids=[ITEM2], quoted_text="Chino", account_ids=[CHINO2[0]]),
                "pass",
                "Item 2: 'Chino' is +13125550158.",
            ),
            A(
                "person_identity",
                P(person_ids=["person:chino"], account_ids=(*CHINO1, *CHINO2)),
                None,
                "That both numbers are one person. Different numbers alone do not contradict it "
                "(rule 2); nothing ties them together.",
            ),
        ),
        gaps=(
            "person:chino is a placeholder for the one person the affidavit says both entries "
            "are. That each owner was in contact with his 'Chino' is not a separate assumption.",
        ),
    ),
    ClaimSpec(
        "C16",
        (
            A(
                "sender",
                P(
                    quoted_text="el miércoles me voy a Los Ángeles unos días. te llamo de allá",
                    person_ids=[QUINTERO],
                ),
                "pass",
                "Outgoing WhatsApp on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="el miércoles me voy a Los Ángeles unos días. te llamo de allá",
                    person_ids=[QUINTERO],
                    account_ids=MAMA_WA,
                    window=day("2026-03-15", "2026-03-16", "On March 15, 2026"),
                ),
                "pass",
                "To Mamá, 7:20:31 PM CDT Mar 15.",
            ),
            A(
                "meaning",
                P(quoted_text="el miércoles me voy a Los Ángeles unos días. te llamo de allá"),
                None,
                "That it says he is going to Los Angeles on Wednesday. Needs a human-confirmed "
                "translation (rule 3).",
            ),
        ),
    ),
    ClaimSpec(
        "C17",
        (
            A(
                "sender",
                P(quoted_text="van stays at ur place til i get back", person_ids=[QUINTERO]),
                "pass",
                "Outgoing WhatsApp on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="van stays at ur place til i get back",
                    person_ids=[QUINTERO],
                    account_ids=HALE_WA,
                    window=window(
                        "2026-03-20T00:30",
                        "2026-03-20T00:31",
                        "At 12:30 a.m. on March 20, 2026",
                        tz=CT,
                    ),
                ),
                "pass",
                "Printed 3/19 10:30:15 PM (UTC-7) while he was in Los Angeles: 05:30:15 UTC, "
                "12:30:15 AM CDT Mar 20 (rule 5).",
            ),
        ),
    ),
    ClaimSpec(
        "C18",
        (
            A(
                "sender",
                P(quoted_text="all 6 at devons. done for the week", person_ids=[QUINTERO]),
                "pass",
                "From +13125550125 on both phones.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="all 6 at devons. done for the week",
                    person_ids=[QUINTERO, BRANDT],
                    window=day("2026-03-20", "2026-03-21", "Before midnight on March 20, 2026"),
                ),
                "fail",
                "06:41:10 UTC Mar 21 is 1:41:10 AM CDT Mar 21, after midnight Central. Item 2 "
                "prints 3/20 11:41 PM (UTC-7), the Pacific clock (rule 5).",
            ),
        ),
        gaps=(
            "'Before midnight on March 20' is read as the day of March 20, Central. A reader "
            "who meant only 'not after midnight' gets the same fail.",
        ),
    ),
    ClaimSpec(
        "C19",
        (
            A(
                "sender",
                P(
                    quoted_text="dile a tu hermano que no venga por ahora, la cosa está caliente",
                    person_ids=[QUINTERO],
                ),
                "pass",
                "Outgoing WhatsApp on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text="dile a tu hermano que no venga por ahora, la cosa está caliente",
                    person_ids=[QUINTERO],
                    account_ids=MARISOL_WA,
                    window=day("2026-03-25", "2026-03-26", "On March 25, 2026"),
                ),
                "pass",
                "To Marisol (FUENTES, paragraph 24), 4:05:27 PM CDT Mar 25.",
            ),
            A(
                "meaning",
                P(quoted_text="dile a tu hermano que no venga por ahora, la cosa está caliente"),
                None,
                "That it warns police were watching the storage unit. It names neither; slang "
                "for a tense situation (rules 1 and 3).",
            ),
        ),
    ),
    ClaimSpec(
        "C20",
        (
            A(
                "event",
                P(
                    person_ids=[BRANDT],
                    handles=["Vic Tools"],
                    channels=["Telegram"],
                    device_ids=[ITEM1],
                    window=day(
                        "2026-02-24", "2026-03-26", "From February 24 through March 25, 2026"
                    ),
                ),
                None,
                "That one Telegram account used the name 'Vic Tools'. Two user ids show it: "
                "8200417 to Mar 10, 8200952 from Mar 17.",
            ),
        ),
        gaps=(
            "No template says 'one display name is one account': same_account needs two handles "
            "and the claim names one. So the contradiction rests on the expert accepting the "
            "rows from the two user ids. Fix: let same_account take one handle and fail when it "
            "resolves to more than one account.",
        ),
    ),
)


# ---------------------------------------------------------------- build


def gold_by_id() -> dict[str, dict]:
    rows = [
        json.loads(line) for line in GOLD_DRAFT.read_text(encoding="utf-8").splitlines() if line
    ]
    return {r["claim_id"]: r for r in rows}


def records() -> list[dict]:
    gold = gold_by_id()
    return [
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
        for c in SPEC
    ]


def render_jsonl(recs: list[dict]) -> str:
    rows = [
        {"claim_id": r["claim_id"], **a, "labeled_by": r["labeled_by"]}
        for r in recs
        for a in r["assumptions"]
    ]
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def render_sheet(recs: list[dict]) -> str:
    gold = gold_by_id()
    lines = [
        "# case02 assumptions: DRAFT for Arsh's line-by-line review",
        "",
        "**Hidden eval case. Builder threads must not read this file.**",
        "",
        "**Not gold.** In the gold-claims eval mode the pipeline uses these assumptions instead "
        "of a model filling the templates, so they are signed like gold. Thread 'Frozen files' "
        "copies the signed file into `eval/gold/case02/`.",
        "",
        "How to read it:",
        "",
        "- Each claim is broken into the fixed templates the engine can test "
        "(`core/audit/assumptions.py`). Parameters are typed; checks never read the sentence.",
        "- **Check** is what the deterministic check should find on case02: pass, fail or "
        "inconclusive. A dash means no check exists for that template, so only an accepted "
        "stance label can cover it.",
        "- Phone ownership (Item 1 BRANDT, Item 2 QUINTERO) is the confirmed case stipulation, "
        "not an assumption here. Other people are named by their accounts, as paragraph 24 "
        "names them by number.",
        "- **Gaps** are parts of the claim no template can express yet. A **known miss** is a "
        "claim whose draft gold verdict the engine cannot reach because of a gap.",
        "- Windows are the affidavit's dates as wall-clock time in America/Chicago (paragraph "
        "23); the `.jsonl` holds their UTC form.",
        "",
        "| Claim | Draft gold | Assumptions | Core checks expected | Gaps | Approve? |",
        "|---|---|---|---|---|---|",
    ]
    for r in recs:
        exp = [a["expected_check"] or "-" for a in r["assumptions"] if a["is_core"]]
        gaps = "**known miss**" if r["claim_id"] in KNOWN_MISSES else (len(r["gaps"]) or "")
        lines.append(
            f"| {r['claim_id']} | {r['gold_verdict']} | {len(r['assumptions'])} | "
            f"{', '.join(exp)} | {gaps} | [ ] |"
        )
    for r in recs:
        lines += [
            "",
            f"## {r['claim_id']}: draft gold {r['gold_verdict']}",
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
    JSONL.write_text(render_jsonl(recs), encoding="utf-8", newline="\n")
    SHEET.write_text(render_sheet(recs), encoding="utf-8", newline="\n")
    print(f"wrote {JSONL.name} and {SHEET.name}: {len(recs)} claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Case06 mock affidavit, DRAFT answer key and DRAFT assumption sheet. SYNTHETIC.

DRAFT ONLY. Every verdict and every assumption row below is the builder's proposal. Arsh reviews
and decides each one; nothing here is gold until a human copies it into eval/gold/. The
affidavit text is generated from this file so claim wording stays verbatim.

case06 is the held-out set for the testability step's go/no-go of record, built to case05's
design so the runs compare, in a new world. Its builder did not read the measured step's
prompt, code, tests or demo claims, or any run result. The design was fixed claim by claim
before any of the story was written, and is recorded here:

- 48 claims, 6 of each claim type in core/contracts.py. Draft verdicts: 24 supported, 12
  contradicted, 12 unproven, spread as each type allows (no absence claim can be supported on a
  curated report):
    communication 4/1/1, identity 3/2/1, timing 3/2/1, content_meaning 3/1/2, count 4/1/1,
    absence 0/3/3, role 3/1/2, event 4/1/1 (supported/contradicted/unproven).
- Wording: per type, 3 claims "plain" (names, dates and quotes stated outright) and 3
  "affidavit" (defined terms and designations, aliases, relative or approximate times, indirect
  speech, references back, roles, numbers in words).
- Hazard: a wrong reading the data holds a candidate for (a second person with the same first
  name or nickname, a second number or account for the same person, a second phone that could
  be meant, a near-miss window, one contact name on two phones for two people, similar words in
  another thread). 47 of the 48 claims carry one: near_window 12, second_number 8,
  second_phone 8, similar_quote 8, same_name 6, contact_name 5; C02 carries none. The sheet
  names only the right person, account, phone and window.
- A sheet for every claim (draft_assumptions.jsonl). One role claim (C39) has only a role row,
  which no check tests; every other claim has a core row a check tests.
- Three phones set to America/Los_Angeles; the case runs from February 10 to March 31, 2025
  and crosses the start of daylight saving (2 a.m. on March 9, 2025, the night of the
  TRANSFER, when the clocks jumped to 3 a.m. and 2 to 3 a.m. never came). Item 1 prints UTC+0,
  Item 2 prints local time with each row's offset, Item 3 prints every row at a fixed UTC-8.
- Every window follows the brief's conventions ("at about" is 8 minutes either side, "at" is
  that minute, "between" runs through the whole last minute, a date or a day set by an event
  is midnight to midnight, a date range runs to the midnight after its last day), except the
  six in NON_CONVENTION, which carry the examiner's reasoning and are listed in
  SIGNING_SHEET.md.

Evidence is referenced as (device, story key); the generator resolves keys to record ids such as
'msg:item1:Chats!412'. 'contact:<name>' is a saved contact. `wrong` lists the records a wrong
reading would rest on or misread (they may also be key evidence, as when the hazard is the
printed time of the key record itself).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

DRAFT_LABEL = "DRAFT (case06 builder, not signed by Arsh)"
TEMPLATES_VERSION = "1.0.0"
TZ = "America/Los_Angeles"

CLAIM_TYPES = (
    "communication",
    "identity",
    "timing",
    "content_meaning",
    "count",
    "absence",
    "role",
    "event",
)

HAZARDS = {
    "same_name": "a second person with the same first name or nickname",
    "second_number": "a second number or account for the same person",
    "second_phone": "a second phone that could be meant",
    "near_window": "a near-miss window: UTC against local time across midnight, the hour that "
    "never came when the clocks went forward, an adjacent day, or Item 3's fixed UTC-8 print",
    "contact_name": "one contact name saved on two phones for two people",
    "similar_quote": "similar words in another thread",
    "none": "no wrong reading planted",
}

READING_RULES = (
    "Times are the phones' own clock, America/Los_Angeles (paragraph 8), never a printed value. "
    "Item 1 prints UTC+0. Item 2 prints each row's own offset. Item 3 prints every row at "
    "UTC-8, so from 3 a.m. on March 9 (when the clocks went forward) its printed times are an "
    "hour behind the phone.",
    "Windows follow the conventions: 'at about H:MM' is 8 minutes before to 8 minutes after, end "
    "exclusive; 'at H:MM' is that minute; 'between H1 and H2' runs from H1:00 through the whole "
    "H2:00 minute; a date is midnight to the next midnight; a date range runs from midnight on "
    "its first day to the midnight after its last; a day set by an event is that whole day.",
    "'About four minutes' is 180 to 300 s, 'about two minutes' 90 to 150 s, 'about a minute' 45 "
    "to 75 s, 'about ten minutes' 540 to 660 s.",
    "Windows no convention covers (each listed in SIGNING_SHEET.md): 'within an hour after' the "
    "KITTIWAKE THEFT (about 11:15 p.m., March 13) is 11:15 p.m. to 12:15 a.m.; 'within half an "
    "hour after' the RECOVERY (10:40 a.m., March 25) is 10:40 to 11:10 a.m.; 'the next morning' "
    "is 5 a.m. to noon; 'the night of' the KITTIWAKE THEFT is 6 p.m. on March 13 to 6 a.m. on "
    "March 14; 'the hour before the clocks went forward' is 1 to 2 a.m. PST on March 9 (09:00 to "
    "10:00 UTC); 'after the SURVEILLANCE ended ... until the RECOVERY' is midnight starting "
    "March 20 to 10:40 a.m. on March 25.",
    "The night of the TRANSFER: 'between 11 p.m. and 4 a.m.' is four real hours and a minute "
    "(07:00:00 to 11:00:59.999999 UTC), because 2 to 3 a.m. never came.",
    "'After' an event counts from its last day and 'before' from its first: the day after the "
    "TRANSFER (March 8 into 9) is Monday, March 10; two days before the HARBOR THEFT (February "
    "28 into March 1) is Wednesday, February 26, and the Monday after it is March 3; two days "
    "after the KITTIWAKE THEFT is March 15; two days before the SURVEILLANCE (March 17 to 19) "
    "began is March 15; three days before the RECOVERY is March 22, and the two days after it "
    "are March 26 and 27. Relative dates count from the sentence before them: 'the next "
    "morning' after March 3 is March 4; 'that night' after the night of the TRANSFER is that "
    "night; 'that morning' after March 9 is March 9.",
    "Defined terms are read as the affidavit defines them (paragraphs 2 and 3): SKIP = CC-1 = "
    "VARLOW, whose phone is Item 1, the GALAXY; CC-2 = COYLE, whose phone is Item 2; "
    "DUKE = the HAULER = CC-3 = PELLOQUIN, whose phone is Item 3, the KYOCERA; the SPARE "
    "LINE is +13605550163, VARLOW's second number; the WORK NUMBER is +13605550192, "
    "PELLOQUIN's work number; the BROKER used +12535550148 and the KELPWISE ACCOUNT, Telegram "
    "user id 8820450.",
    "A claim is contradicted only when observed data rules it out: the quoted words came from "
    "another account, or at another time; a phone holds more messages than an exact count; "
    "handles resolve to two accounts; contact is found where the claim says there was none.",
    "A curated report cannot show an absence, so an absence claim is never supported here: it is "
    "contradicted if contact is found and unproven otherwise. Not found never means did not "
    "happen.",
    "A meaning or role is supported only when the conversation itself fixes it; an agent's "
    "reading of slang, of a nickname or of who directed whom is interpretation.",
)

DEVICE_ATTRIBUTION = (
    "Item 1 is used by VARLOW, Item 2 by COYLE and Item 3 by PELLOQUIN, so each phone's own "
    "accounts speak for its owner. The key treats this as given, as the affidavit does; it is "
    "not proven by the data. Paragraph 3 says the SPARE LINE is VARLOW's second number, and a "
    "record from his own phone ties him to it: on February 20 VARLOW's own number texts the "
    "HAULER 'new number for boat stuff is 360 555 0163. this one stays personal' (on Items 1 "
    "and 3), and fifteen minutes later the SPARE LINE writes 'its skip. new number for boat "
    "stuff' to COYLE, who saves it as 'Captain'. C05 rests on that tie, in an authorship row "
    "the expert decides. Paragraph 3 says the WORK NUMBER is PELLOQUIN's; it writes 'on shift "
    "till 11, this is the work line' to VARLOW, and Item 1 saves it as 'Duke work'. C16 and C08 "
    "are about the number, not about who held it."
)

Ref = tuple[str, str]  # (device, story key)
Wording = Literal["plain", "affidavit"]


@dataclass(frozen=True)
class DraftClaim:
    claim_id: str
    claim_type: str
    wording: Wording
    verdict: str
    hazard: str  # a key of HAZARDS
    text: str
    core_assumptions: tuple[str, ...]
    evidence: tuple[Ref, ...]  # key evidence
    rationale: str
    hazard_detail: str = ""  # the wrong reading, and what the sheet names instead
    wrong: tuple[Ref, ...] = ()  # the records a wrong reading rests on or misreads
    style: str = ""  # affidavit wording: which devices it uses
    cross_device: bool = False


C = DraftClaim

CLAIMS: tuple[DraftClaim, ...] = (
    # ------------------------------------------------------------ communication
    C(
        "C01",
        "communication",
        "plain",
        "supported",
        "near_window",
        'On February 19, 2025, VARLOW texted COYLE "check the dinghy dock after 9, its quiet".',
        ("VARLOW's SMS account sent the message to COYLE on Feb 19, Pacific time",),
        (("item1", "vc_dinghy"), ("item2", "vc_dinghy")),
        "Outgoing SMS on Item 1 at 8:15 p.m. PST on Feb 19, incoming on Item 2.",
        "Item 1 prints its copy as 2/20/2025 4:15:40 AM(UTC+0); a window on that printed date "
        "misses it. The sheet names Feb 19, Pacific time.",
        (("item1", "vc_dinghy"),),
    ),
    C(
        "C02",
        "communication",
        "plain",
        "supported",
        "none",
        'On March 4, 2025, COYLE sent PELLOQUIN a WhatsApp message reading "boathouse key is on '
        'the nail in the shed".',
        ("COYLE's WhatsApp account sent the message to PELLOQUIN on Mar 4",),
        (("item2", "cp_key"), ("item3", "cp_key")),
        "Outgoing on Item 2 at 4:10 p.m. PST on Mar 4, incoming on Item 3. A clean claim.",
    ),
    C(
        "C03",
        "communication",
        "plain",
        "contradicted",
        "similar_quote",
        'On March 6, 2025, COYLE texted VARLOW "the white cowls are off, come see tonight".',
        ("COYLE's SMS account sent the message to VARLOW on Mar 6",),
        (("item1", "vc_cowl"), ("item2", "vc_cowl"), ("item2", "vc_cowl2")),
        "Both copies (Items 1 and 2) were sent by VARLOW's number, +13605550114, at 11:45 a.m. "
        "PST on Mar 6; COYLE answered 'after 8'. Observed data rules out the stated sender.",
        "COYLE did write 'the white cowls are off the skiff, come look' that day, to Item 2's "
        "'Duke' (+12535550151, the mechanic who wrote 'this is duke at marchetti marine'), about "
        "her skiff. A loose match on those words passes the sender; the sheet tests the claim's "
        "exact words.",
        (("item2", "cm_cowl"),),
    ),
    C(
        "C04",
        "communication",
        "affidavit",
        "unproven",
        "similar_quote",
        'The day after the TRANSFER, SKIP told the HAULER by text that "the motors stay wrapped '
        'till the heat dies down".',
        ("VARLOW's SMS account sent the words to PELLOQUIN on Mar 10",),
        (("item1", "vg_wrap"),),
        "No message with these words is on any phone. On Mar 10 VARLOW texted Item 1's "
        "'Hollis' (+13605550120) 'keep the motors wrapped till the paint cures', which is not "
        "the claim. The reports are curated, so not shown, not ruled out.",
        "A loose match takes the text to 'Hollis' for the quote and passes the sender (VARLOW "
        "wrote it). The sheet tests the claim's exact words, to the HAULER.",
        (("item1", "vg_wrap"),),
        "defined terms (TRANSFER, the HAULER), an alias (SKIP), a day set by an event, indirect "
        "speech",
    ),
    C(
        "C05",
        "communication",
        "affidavit",
        "supported",
        "second_number",
        "Two days before the HARBOR THEFT, CC-1 texted the HAULER from the SPARE LINE: "
        '"bring the long straps and the dolly".',
        (
            "The SPARE LINE sent the message to PELLOQUIN on Feb 26",
            "VARLOW wrote what the SPARE LINE sent",
        ),
        (
            ("item3", "sp_straps"),
            ("item1", "vp_new"),
            ("item3", "vp_new"),
            ("item3", "sp_new"),
            ("item1", "vp_s4"),
            ("item3", "vp_s4"),
            ("item2", "sc_new"),
        ),
        "Incoming on Item 3 from +13605550163 at 7:15 p.m. PST on Wednesday, Feb 26. VARLOW's "
        "own number gave the HAULER that number on Feb 20 ('new number for boat stuff is 360 555 "
        "0163. this one stays personal', on Items 1 and 3), a record from his own phone; twenty "
        "minutes later 0163 wrote to the HAULER 'this is the other number', and on Mar 19 "
        "VARLOW's own number told him 'use the other number'. Not relied on: 0163's 'its skip' "
        "to COYLE, because Item 3 also saves another number as 'Skip' (+13605550184) beside "
        "0163 as 'Skip 2', so a nickname alone does not tie the number to VARLOW.",
        "VARLOW's own number also texted the HAULER that afternoon ('u around tmrw?'). A "
        "reading that takes CC-1's own number for the sender finds the quote came from "
        "elsewhere and fails it. The sheet names the SPARE LINE.",
        (("item3", "vp_tmrw"),),
        "defined terms (HARBOR THEFT, SPARE LINE, the HAULER), a designation, a day set by an "
        "event",
        cross_device=True,
    ),
    C(
        "C06",
        "communication",
        "affidavit",
        "supported",
        "second_phone",
        "At about 3:40 a.m. on March 9, 2025, CC-2 sent the KYOCERA a Telegram message that "
        'read "leave the trailer at the barn, not the boathouse".',
        ("COYLE's Telegram account sent the message to Item 3 at about 3:40 a.m. on Mar 9",),
        (("item3", "cp_barn"),),
        "Incoming on Item 3 from Telegram user id 8820422 (COYLE's own account on Item 2) at "
        "3:41 a.m. PDT on Mar 9, forty minutes after the clocks went forward.",
        "CC-2's own phone (Item 2) does not hold the message; a reading of Item 2 finds "
        "only her 3:05 a.m. WhatsApp to the HAULER and leaves the claim unproven. Item 3 prints "
        "it as 2:41:30 AM(UTC-8). The sheet names Item 3 and the PDT window.",
        (("item3", "cp_barn"), ("item2", "cp_hill")),
        "a designation (CC-2), a phone by its defined name (the KYOCERA), an approximate "
        "time in the hour after the clocks went forward",
    ),
    # ------------------------------------------------------------ identity
    C(
        "C07",
        "identity",
        "plain",
        "supported",
        "contact_name",
        'Item 1 contains a contact saved as "Lars" with the number +1 (253) 555-0148.',
        ("Item 1 has a contact 'Lars' holding +12535550148",),
        (("item1", "contact:Lars"),),
        "Item 1's Contacts sheet holds 'Lars' with +12535550148.",
        "Item 3 also saves a 'Lars', with +13605550173. A reading on Item 3 finds another "
        "number. The sheet names Item 1.",
        (("item3", "contact:Lars"),),
    ),
    C(
        "C08",
        "identity",
        "plain",
        "unproven",
        "second_number",
        'Item 1 contains a contact saved as "Duke" with the number +1 (360) 555-0192.',
        ("Item 1 has a contact 'Duke' holding +13605550192",),
        (("item1", "contact:Duke"), ("item1", "contact:Duke work")),
        "Item 1's 'Duke' holds +13605550138, PELLOQUIN's own number; +13605550192 (the WORK "
        "NUMBER) is saved as 'Duke work'. A missing entry is never a fail (contact lists are "
        "edited, and the report is curated), so not shown, not ruled out.",
        "Taking 'Duke work' for 'Duke' passes the claim; the check reads the name exactly. The "
        "sheet names 'Duke' and +13605550192.",
        (("item1", "contact:Duke work"),),
    ),
    C(
        "C09",
        "identity",
        "plain",
        "contradicted",
        "same_name",
        'On Item 3, the Telegram names "Skip" and "Em V" belong to one account.',
        ("On Item 3's Telegram, 'Skip' and 'Em V' are one account",),
        (("item3", "ts_dock"), ("item3", "vt_tanks2")),
        "'Skip' is Telegram user id 8820484, who writes 'dock 4 needs a hand sat morning'; 'Em "
        "V' is 8820411 (VARLOW). Two accounts.",
        "SKIP is VARLOW's nickname (paragraph 2), and 'Em V' is his Telegram account. A reading "
        "that takes Item 3's 'Skip' for VARLOW calls them one account. The sheet tests the two "
        "names as written.",
        (("item3", "ts_dock"),),
    ),
    C(
        "C10",
        "identity",
        "affidavit",
        "supported",
        "contact_name",
        'CC-2 saved the SPARE LINE in her phone as "Captain".',
        ("Item 2 has a contact 'Captain' holding +13605550163",),
        (("item2", "contact:Captain"), ("item2", "sc_new2")),
        "Item 2's 'Captain' holds +13605550163; she wrote 'saved u as captain lol' to the "
        "number on Feb 20.",
        "Item 3 also saves a 'Captain', with +13605550109. A reading on Item 3 finds another "
        "number. The sheet names Item 2.",
        (("item3", "contact:Captain"),),
        "a designation (CC-2), a number by its defined name (SPARE LINE), 'her phone' for Item 2",
    ),
    C(
        "C11",
        "identity",
        "affidavit",
        "supported",
        "second_number",
        'CC-2 used the Telegram account "harborlights", which the KYOCERA showed as "Ren C" '
        "until March 12, 2025.",
        (
            "On Telegram, 'Ren C' and 'harborlights' are one account",
            "That account is COYLE's",
        ),
        (("item3", "ct_a"), ("item3", "ct_b"), ("item2", "ct_b")),
        "Both names resolve to Telegram user id 8820422, Item 2's own Telegram account (its "
        "User Accounts sheet, and the outgoing copies on Item 2). Item 3 shows 'Ren C' through "
        "8:41 p.m. PDT Mar 11 (printed 7:41:05 PM(UTC-8)) and 'harborlights' from 4:45 p.m. "
        "Mar 12.",
        "Item 3 also saves COYLE's phone number as the contact 'Ren C' (+12535550127). A "
        "reading that takes the contact for the Telegram name finds a phone number and a "
        "Telegram id, two accounts. The sheet names the Telegram account on Item 3.",
        (("item3", "contact:Ren C"),),
        "a designation (CC-2), a phone by its defined name (the KYOCERA), a display-name change",
        cross_device=True,
    ),
    C(
        "C12",
        "identity",
        "affidavit",
        "contradicted",
        "contact_name",
        'The text message "the lower unit is shot" that CC-2 received from "Duke" on March '
        "11, 2025 was sent by the HAULER.",
        ("PELLOQUIN's SMS account sent the message Item 2 received on Mar 11",),
        (("item2", "mc_lower"), ("item2", "contact:Duke"), ("item2", "mc_intro")),
        "The only copy is on Item 2, from +12535550151, the number Item 2 saves as 'Duke'. That "
        "number introduced itself to her on Feb 12 as 'duke at marchetti marine' with her skiff "
        "in its shop, and its every message is about her skiff or the shop; Item 2 saves "
        "PELLOQUIN separately, as 'Duncan P' (+13605550138), which did not send it.",
        "DUKE is PELLOQUIN's nickname (paragraph 2), and Item 1 saves PELLOQUIN as 'Duke'; "
        "Item 2's 'Duke' is another person. A reading that takes Item 2's 'Duke' for the HAULER "
        "passes the sender. The sheet names PELLOQUIN.",
        (("item2", "contact:Duke"), ("item1", "contact:Duke")),
        "a designation (CC-2), a role (the HAULER), a contact name in quotes",
    ),
    # ------------------------------------------------------------ timing
    C(
        "C13",
        "timing",
        "plain",
        "supported",
        "near_window",
        "At about 9:10 p.m. on February 21, 2025, VARLOW called PELLOQUIN; the call lasted about "
        "four minutes.",
        ("A call between VARLOW and PELLOQUIN at about 9:10 p.m. Feb 21, 180 to 300 s",),
        (("item1", "cl_0221b"), ("item3", "cl_0221b")),
        "Outgoing on Item 1 at 9:12:40 p.m. PST, 236 s (3:56).",
        "Item 1 prints UTC: the 9:12 p.m. call shows as 2/22/2025 5:12:40 AM(UTC+0), and a 38 s "
        "call at 1:09 p.m. PST shows as 2/21/2025 9:09:30 PM(UTC+0). Reading the printed time "
        "picks the short call. The sheet names 9:02 to 9:18 p.m. PST.",
        (("item1", "cl_0221a"),),
    ),
    C(
        "C14",
        "timing",
        "plain",
        "supported",
        "near_window",
        "At about 3:15 a.m. on March 9, 2025, VARLOW called PELLOQUIN; the call lasted about two "
        "minutes.",
        ("A call between VARLOW and PELLOQUIN at about 3:15 a.m. PDT Mar 9, 90 to 150 s",),
        (("item1", "cl_0309a"), ("item3", "cl_0309a")),
        "Outgoing on Item 1 at 3:14:20 a.m. PDT, 118 s, fourteen minutes after the clocks went "
        "forward.",
        "Item 3 prints the call as 2:14:20 AM(UTC-8), a time the phone never showed, and prints "
        "a 31 s call at 4:12 a.m. PDT as 3:12:05 AM(UTC-8). A window built at UTC-8 for 3:15 "
        "a.m. holds only the short call. The sheet names 3:07 to 3:23 a.m. PDT.",
        (("item3", "cl_0309a"), ("item3", "cl_0309b")),
    ),
    C(
        "C15",
        "timing",
        "plain",
        "contradicted",
        "near_window",
        'At 8:40 p.m. on March 12, 2025, PELLOQUIN texted VARLOW "barn code is 4417 now, dont '
        'lose it".',
        (
            "PELLOQUIN's SMS account sent the message",
            "It was sent at 8:40 p.m. PDT on Mar 12",
        ),
        (("item1", "pv_code"), ("item3", "pv_code")),
        "Sent at 9:40:15 p.m. PDT on Mar 12 (both copies). Observed data puts it an hour after "
        "the stated minute.",
        "Item 3 prints it as 3/12/2025 8:40:15 PM(UTC-8), an hour behind the phone since the "
        "clocks went forward. Reading the printed time passes it. The sheet names 8:40 p.m. "
        "PDT.",
        (("item3", "pv_code"),),
    ),
    C(
        "C16",
        "timing",
        "affidavit",
        "supported",
        "second_number",
        "Within an hour after the KITTIWAKE THEFT, the WORK NUMBER called SKIP; they spoke for "
        "about a minute.",
        (
            "A call between the WORK NUMBER and VARLOW from 11:15 p.m. Mar 13 to 12:15 a.m. "
            "Mar 14, 45 to 75 s",
        ),
        (("item1", "cl_wrk"), ("item1", "contact:Duke work")),
        "Incoming on Item 1 from +13605550192 at 11:48:10 p.m. PDT on Mar 13, 68 s.",
        "PELLOQUIN's own number also called VARLOW in that hour (12:06 a.m., 22 s). A reading "
        "that takes the HAULER's own number for the WORK NUMBER finds a call too short. The "
        "sheet names +13605550192.",
        (("item1", "cl_pel0314"),),
        "defined terms (KITTIWAKE THEFT, WORK NUMBER), an alias (SKIP), a window relative to an "
        "event, a duration in words",
    ),
    C(
        "C17",
        "timing",
        "affidavit",
        "contradicted",
        "near_window",
        "Two days before the SURVEILLANCE began, at about 11:30 p.m., CC-1 sent the HAULER a "
        'WhatsApp message reading "move the trailer behind the barn tonight".',
        (
            "VARLOW's WhatsApp account sent the message",
            "It was sent at about 11:30 p.m. PDT on Mar 15",
        ),
        (("item1", "vw_move"), ("item3", "vw_move")),
        "Sent at 4:31:20 p.m. PDT on Mar 15 (both copies), seven hours before the stated time.",
        "Item 1 prints it as 3/15/2025 11:31:20 PM(UTC+0). Reading the printed time passes it. "
        "The sheet names 11:22 to 11:38 p.m. PDT on Mar 15.",
        (("item1", "vw_move"),),
        "defined terms (SURVEILLANCE, the HAULER), a designation, a day set by an event, an "
        "approximate time",
    ),
    C(
        "C18",
        "timing",
        "affidavit",
        "unproven",
        "second_phone",
        "Within half an hour after the RECOVERY, the GALAXY logged a call between CC-1 and "
        "the HAULER.",
        ("Item 1 logged a call between VARLOW and PELLOQUIN from 10:40 to 11:10 a.m. Mar 25",),
        (("item3", "cl_rec"),),
        "Item 1's call log holds no such call. Item 3's does: PELLOQUIN called VARLOW at 10:55 "
        "a.m. PDT on Mar 25, 95 s. The claim is about what the GALAXY logged, and the report is "
        "curated, so not shown, not ruled out.",
        "A reading that drops 'the GALAXY' finds the call on Item 3 and supports the claim. The "
        "sheet names Item 1.",
        (("item3", "cl_rec"),),
        "defined terms (RECOVERY, the GALAXY, the HAULER), a designation, a window relative to an "
        "event",
    ),
    # ------------------------------------------------------------ content meaning
    C(
        "C19",
        "content_meaning",
        "plain",
        "supported",
        "similar_quote",
        'On February 24, 2025, VARLOW texted COYLE "spotted 4 big fish on the north float"; "big '
        'fish" meant outboard motors.',
        (
            "VARLOW sent the message to COYLE on Feb 24",
            "'big fish' meant outboard motors",
        ),
        (
            ("item1", "vc_fish"),
            ("item1", "vc_fish2"),
            ("item1", "vc_fish3"),
            ("item2", "vc_fish"),
        ),
        "COYLE asked 'the outboards?' and VARLOW answered 'ya 4 outboards, two are 150s': the "
        "exchange fixes the meaning.",
        "Item 3's 'Rafe' (+13605550178) wrote '4 big fish off the north jetty today' to "
        "PELLOQUIN that evening, about fish. A reading that mixes the threads finds 'big fish' "
        "meaning fish. The sheet names VARLOW and COYLE.",
        (("item3", "rf_fish"),),
    ),
    C(
        "C20",
        "content_meaning",
        "plain",
        "unproven",
        "similar_quote",
        'On March 3, 2025, COYLE texted VARLOW "keep the sleeping bags dry", meaning the stolen '
        "chartplotters wrapped in plastic.",
        (
            "COYLE sent the message to VARLOW on Mar 3",
            "'the sleeping bags' meant the chartplotters",
        ),
        (("item1", "cv_bags"), ("item2", "cv_bags")),
        "Observed; VARLOW answered only 'will do'. Nothing in the exchange fixes 'the sleeping "
        "bags', and two days earlier COYLE wrote the same words to her mother about real "
        "sleeping bags.",
        "The message to her mother ('keep the sleeping bags dry, rain all week at the lake') "
        "shows the words in plain use; a reading that leans on it contradicts the meaning, one "
        "that ignores it supports it. Neither is fixed. The sheet names COYLE and VARLOW.",
        (("item2", "cm_bags"),),
    ),
    C(
        "C21",
        "content_meaning",
        "plain",
        "contradicted",
        "near_window",
        'On March 19, 2025, COYLE texted VARLOW "the guard naps after 2, every night", telling '
        "him when the yard would be unwatched.",
        (
            "COYLE sent the message to VARLOW on Mar 19",
            "the message told him when the yard would be unwatched",
        ),
        (("item1", "cv_guard"), ("item2", "cv_guard")),
        "Sent at 6:05 p.m. PDT on Mar 18 (both copies). Observed data puts it on another day.",
        "Item 1 prints it as 3/19/2025 1:05:20 AM(UTC+0). Reading the printed date passes it. "
        "The sheet names Mar 19, Pacific time.",
        (("item1", "cv_guard"),),
    ),
    C(
        "C22",
        "content_meaning",
        "affidavit",
        "supported",
        "similar_quote",
        'The next morning, SKIP asked the HAULER on Telegram to "bring the soup cans to the '
        'boathouse", by which he meant the fuel tanks.',
        (
            "VARLOW sent the message to PELLOQUIN on the morning of Mar 4",
            "'the soup cans' meant the fuel tanks",
        ),
        (
            ("item1", "vt_soup"),
            ("item3", "vt_soup"),
            ("item3", "vt_tanks"),
            ("item3", "vt_tanks2"),
            ("item3", "vt_soup2"),
            ("item3", "vt_soup3"),
        ),
        "Sent at 9:20 a.m. PST on Mar 4. The thread fixes it: 'u want the red tanks too?' / 'ya "
        "the soup cans. all 6 fuel tanks' the evening before, and 'all 6?' / 'all 6 tanks ya' "
        "after.",
        "That morning Item 3's 'Odile' (WhatsApp 13605550156) wrote 'bring the soup cans to "
        "moms, she needs them for the drive' to PELLOQUIN, about soup. A reading that mixes the "
        "threads finds soup. The sheet names VARLOW and PELLOQUIN.",
        (("item3", "od_soup"),),
        "an alias (SKIP), a role (the HAULER), 'the next morning' referring back, indirect speech",
    ),
    C(
        "C23",
        "content_meaning",
        "affidavit",
        "supported",
        "second_number",
        'Three days before the RECOVERY, the SPARE LINE told CC-2 that "the twins are in '
        '17", which in that exchange meant the two 150-horsepower motors.',
        (
            "The SPARE LINE sent the message to COYLE on Mar 22",
            "'the twins' meant the two 150-horsepower motors",
        ),
        (
            ("item2", "sc_twins"),
            ("item2", "sc_twins2"),
            ("item2", "sc_twins3"),
            ("item2", "vc_fish3"),
        ),
        "Incoming on Item 2 from +13605550163 at 11:40 a.m. PDT on Mar 22; 'the 150s?' / 'ya "
        "both 150 outboards, locked up' fix the meaning in the exchange itself. '150' on an "
        "outboard is its horsepower, and the Feb 24 thread on the same phone ('ya 4 outboards, "
        "two are 150s') uses it the same way.",
        "VARLOW's own number also texted her that morning ('call me tonight'). A reading that "
        "takes CC-1's own number for the SPARE LINE finds the quote came from elsewhere. "
        "The sheet names the SPARE LINE.",
        (("item2", "vc_tonight"),),
        "defined terms (RECOVERY, SPARE LINE), a designation, a day set by an event, indirect "
        "speech, a number in words",
    ),
    C(
        "C24",
        "content_meaning",
        "affidavit",
        "unproven",
        "same_name",
        'Two days after the KITTIWAKE THEFT, CC-2 told CC-1 that "duke wants out", '
        "referring to the HAULER.",
        (
            "COYLE sent the message to VARLOW on Mar 15",
            "'duke' meant PELLOQUIN",
        ),
        (("item1", "cv_duke"), ("item2", "cv_duke")),
        "Observed at 7:10 p.m. PDT on Mar 15; VARLOW answered 'ok'. Which Duke is not fixed. "
        "COYLE's own phone saves PELLOQUIN as 'Duncan P' and saves another number, "
        "+12535550151, as 'Duke' (it introduced itself as 'duke at marchetti marine'); that "
        "morning that 'Duke' wrote to her 'i want out of the boat show booth this year, too "
        "much hassle'. Nothing in the exchange says which one she meant, or out of what.",
        "A reading that takes DUKE (paragraph 2) as fixing the quote supports the meaning; one "
        "that takes her own phone's 'Duke' contradicts it. Neither is fixed. The sheet names "
        "COYLE and VARLOW.",
        (("item2", "mc_out"),),
        "defined terms (KITTIWAKE THEFT, the HAULER), designations, a day set by an event, "
        "indirect speech",
    ),
    # ------------------------------------------------------------ count
    C(
        "C25",
        "count",
        "plain",
        "supported",
        "near_window",
        "Between February 17 and February 23, 2025, Item 1 recorded 8 Signal messages exchanged "
        "between VARLOW and COYLE.",
        ("Item 1 holds exactly 8 Signal messages between VARLOW and COYLE, Feb 17 to 23",),
        (
            ("item1", "sg_17"),
            ("item1", "sg_18"),
            ("item1", "sg_19a"),
            ("item1", "sg_19b"),
            ("item1", "sg_20"),
            ("item1", "sg_21"),
            ("item1", "sg_23a"),
            ("item1", "sg_23b"),
        ),
        "Eight on Pacific dates Feb 17 to 23, both ways.",
        "Item 1 prints UTC: the three of the evening of Feb 16 print on Feb 17, and the two of "
        "the afternoon of Feb 23 print on Feb 24. Printed dates give nine. The sheet names "
        "Pacific dates.",
        (
            ("item1", "sg_16a"),
            ("item1", "sg_16b"),
            ("item1", "sg_16c"),
            ("item1", "sg_23a"),
            ("item1", "sg_23b"),
        ),
    ),
    C(
        "C26",
        "count",
        "plain",
        "supported",
        "second_phone",
        "From March 10 through March 14, 2025, Item 3 recorded 6 WhatsApp messages exchanged "
        "between PELLOQUIN and COYLE.",
        ("Item 3 holds exactly 6 WhatsApp messages between PELLOQUIN and COYLE, Mar 10 to 14",),
        (
            ("item3", "cw10a"),
            ("item3", "cw10b"),
            ("item3", "cw13"),
            ("item3", "cp_ask"),
            ("item3", "cp_price"),
            ("item3", "cp_price2"),
        ),
        "Six on Item 3, both ways.",
        "Item 2 holds a seventh (COYLE's '?' at 7:05 p.m. Mar 12), which Item 3's report does "
        "not. A count on Item 2 gives seven and fails. The sheet names Item 3.",
        (("item2", "cw12"),),
    ),
    C(
        "C27",
        "count",
        "plain",
        "contradicted",
        "near_window",
        "On March 12, 2025, Item 3 recorded 4 text messages exchanged between PELLOQUIN and "
        "VARLOW.",
        ("Item 3 holds exactly 4 SMS between PELLOQUIN and VARLOW on Mar 12",),
        (
            ("item3", "v12a"),
            ("item3", "v12b"),
            ("item3", "v12c"),
            ("item3", "v12d"),
            ("item3", "pv_code"),
            ("item3", "v12f"),
        ),
        "Six on the Pacific day, from 12:15 a.m. to 9:52 p.m. PDT. More than the exact count.",
        "Item 3 prints the 12:15 and 12:45 a.m. PDT texts as 11:15 and 11:45 PM(UTC-8) on Mar "
        "11, so its printed Mar 12 holds four, matching the claim. The sheet names the Pacific "
        "day.",
        (("item3", "v12a"), ("item3", "v12b")),
    ),
    C(
        "C28",
        "count",
        "affidavit",
        "supported",
        "second_number",
        "During the SURVEILLANCE, the HAULER sent the SPARE LINE seven text messages, all "
        "recorded on the KYOCERA.",
        ("Item 3 holds exactly 7 SMS from PELLOQUIN to +13605550163, Mar 17 to 19",),
        (
            ("item3", "s1"),
            ("item3", "s2"),
            ("item3", "s3"),
            ("item3", "s4"),
            ("item3", "s5"),
            ("item3", "s6"),
            ("item3", "s7"),
        ),
        "Seven from PELLOQUIN to the SPARE LINE on Item 3 (the KYOCERA), Mar 17 to 19. The one "
        "on the evening of Mar 16 and the one on the morning of Mar 20 are outside.",
        "He also texted VARLOW's own number three times in those days. A count of texts to "
        "both of CC-1's numbers gives ten and fails. The sheet names the SPARE LINE.",
        (("item3", "pv_s1"), ("item3", "pv_s2"), ("item3", "pv_s3")),
        "defined terms (SURVEILLANCE, SPARE LINE, the KYOCERA), a role (the HAULER), a window "
        "set by an event, a number in words",
    ),
    C(
        "C29",
        "count",
        "affidavit",
        "unproven",
        "second_phone",
        "Between March 3 and March 7, 2025, the GALAXY recorded at least six WhatsApp messages "
        "between CC-1 and CC-3.",
        ("Item 1 holds at least 6 WhatsApp messages between VARLOW and PELLOQUIN, Mar 3 to 7",),
        (("item1", "w03"), ("item1", "w04a"), ("item1", "w05"), ("item1", "w06")),
        "The GALAXY (Item 1) holds four. Fewer than claimed is never a fail on a curated report.",
        "Item 3 holds six for the same days. A count on Item 3 supports the claim. The sheet "
        "names Item 1.",
        (("item3", "w04b"), ("item3", "w07")),
        "a phone by its defined name (the GALAXY), designations, a number in words",
    ),
    C(
        "C30",
        "count",
        "affidavit",
        "supported",
        "near_window",
        "On the night of the TRANSFER, between 11 p.m. and 4 a.m., CC-1 and CC-2 "
        "exchanged eleven Signal messages, as recorded on Item 2.",
        ("Item 2 holds exactly 11 Signal messages between VARLOW and COYLE, 11 p.m. to 4 a.m.",),
        (
            ("item2", "tn01"),
            ("item2", "tn02"),
            ("item2", "tn03"),
            ("item2", "tn04"),
            ("item2", "tn05"),
            ("item2", "tn06"),
            ("item2", "tn07"),
            ("item2", "tn08"),
            ("item2", "tn09"),
            ("item2", "tn10"),
            ("item2", "tn11"),
        ),
        "Eleven between 11:05 p.m. PST and 3:58 a.m. PDT, both ways: four real hours, because 2 "
        "to 3 a.m. never came.",
        "A five-hour window at one offset (07:00 to 12:00 UTC) also takes the two after 4 a.m. "
        "PDT and gives thirteen, failing. The sheet names 11 p.m. PST to 4:00:59 a.m. PDT.",
        (("item2", "tn12"), ("item2", "tn13")),
        "defined terms (TRANSFER), designations, a night set by an event across the change to "
        "daylight time, a number in words",
    ),
    # ------------------------------------------------------------ absence
    C(
        "C31",
        "absence",
        "plain",
        "contradicted",
        "near_window",
        "VARLOW and PELLOQUIN had no contact of any kind on February 18, 2025.",
        ("No contact between VARLOW and PELLOQUIN on Feb 18",),
        (("item1", "vp_18a"), ("item3", "vp_18a"), ("item3", "vp_18b")),
        "Texts at 6:25 and 6:31 p.m. PST on Feb 18.",
        "Item 1 prints both on Feb 19 (2:25:30 AM(UTC+0)). A reading of Item 1's printed dates "
        "finds no contact on Feb 18. The sheet names the Pacific day.",
        (("item1", "vp_18a"), ("item1", "vp_18b")),
    ),
    C(
        "C32",
        "absence",
        "plain",
        "contradicted",
        "second_number",
        "COYLE and VARLOW had no contact of any kind between March 26 and March 28, 2025.",
        ("No contact between COYLE and VARLOW, Mar 26 to 28",),
        (("item1", "cv_wa27"), ("item2", "cv_wa27"), ("item2", "cv_wa27b")),
        "A WhatsApp exchange on Mar 27 ('dont use texts anymore. only here').",
        "Their texts stop after Mar 22. A reading that searches only their phone numbers (SMS "
        "and calls) misses their WhatsApp accounts and finds none; the sheet names both people "
        "and no channel.",
        (("item2", "cv_wa27"),),
    ),
    C(
        "C33",
        "absence",
        "plain",
        "unproven",
        "contact_name",
        "PELLOQUIN had no contact of any kind with the number +1 (253) 555-0148 between March 1 "
        "and March 31, 2025.",
        ("No contact between PELLOQUIN and +12535550148 in March",),
        (("item1", "contact:Lars"), ("item3", "contact:Lars")),
        "No record between PELLOQUIN and +12535550148 is on any phone; the reports are curated, "
        "so the absence cannot be shown.",
        "PELLOQUIN has texts and calls all month with Item 3's 'Lars', +13605550173; Item 1 "
        "saves +12535550148 as 'Lars'. Taking one Lars for the other contradicts the claim "
        "wrongly. The sheet names +12535550148.",
        (("item3", "pl_yam"),),
        cross_device=True,
    ),
    C(
        "C34",
        "absence",
        "affidavit",
        "unproven",
        "near_window",
        "In the hour before the clocks went forward that night, the HAULER and CC-2 had no "
        "contact.",
        ("No contact between PELLOQUIN and COYLE from 1 to 2 a.m. PST on Mar 9",),
        (
            ("item2", "pc_road"),
            ("item2", "cp_hill"),
            ("item3", "pc_road"),
            ("item3", "cp_hill"),
        ),
        "None from 1 to 2 a.m. PST (09:00 to 10:00 UTC); their WhatsApps fall at 12:52 a.m. PST "
        "and 3:05 a.m. PDT, either side. Curated reports, so not shown.",
        "A window built at the new offset (1 to 2 a.m. PDT, 08:00 to 09:00 UTC) takes the 12:52 "
        "a.m. message; one read off Item 3's UTC-8 print as 'the hour before 3 a.m.' takes the "
        "3:05 a.m. message, printed 2:05:10 AM(UTC-8). Either contradicts the claim wrongly. "
        "The sheet names 09:00 to 10:00 UTC.",
        (("item3", "pc_road"), ("item3", "cp_hill")),
        "a role (the HAULER), a designation, 'that night' referring back, a window set by the "
        "clock change",
    ),
    C(
        "C35",
        "absence",
        "affidavit",
        "contradicted",
        "same_name",
        "On the two days after the RECOVERY, CC-2 had no contact with DUKE.",
        ("No contact between COYLE and PELLOQUIN on Mar 26 and 27",),
        (("item2", "cp_took"), ("item3", "cp_took"), ("item3", "cp_took2")),
        "DUKE is PELLOQUIN (paragraph 2). Texts on Mar 26 ('they took the 150s' / 'i know. dont "
        "call me').",
        "Item 2 saves another number as 'Duke' (+12535550151), with which she has no contact "
        "after Mar 22. A reading that takes Item 2's 'Duke' finds none and leaves the claim "
        "unproven. The sheet names PELLOQUIN.",
        (("item2", "contact:Duke"),),
        "defined terms (RECOVERY), a designation, an alias (DUKE), days set by an event",
    ),
    C(
        "C36",
        "absence",
        "affidavit",
        "unproven",
        "second_phone",
        "From the day after the RECOVERY through March 31, 2025, CC-1 and the HAULER had no "
        "contact, per the GALAXY.",
        ("Item 1 holds no contact between VARLOW and PELLOQUIN, Mar 26 to 31",),
        (("item3", "vw_28"), ("item3", "vw_28b")),
        "None on Item 1 (the GALAXY); curated, so not shown. Item 3 holds a WhatsApp exchange on "
        "Mar 28, which Item 1's report does not.",
        "A reading across all phones finds the Mar 28 exchange and contradicts a claim made "
        "about the GALAXY alone. The sheet names Item 1.",
        (("item3", "vw_28"),),
        "defined terms (RECOVERY, the GALAXY), a designation, a role, a range set by an event",
    ),
    # ------------------------------------------------------------ role
    C(
        "C37",
        "role",
        "plain",
        "supported",
        "similar_quote",
        "On March 14, 2025, COYLE set the price for the motors, telling PELLOQUIN by WhatsApp "
        '"2200 for the big ones, 900 for the kickers".',
        (
            "COYLE sent the message to PELLOQUIN on Mar 14",
            "COYLE set the price",
        ),
        (
            ("item2", "cp_ask"),
            ("item2", "cp_price"),
            ("item2", "cp_price2"),
            ("item3", "cp_price"),
        ),
        "PELLOQUIN asked 'what do i ask for the motors?', COYLE answered with the prices, and "
        "he took them ('ok 2200'): the exchange fixes who set the price.",
        "That evening Item 2's 'Duke' (+12535550151) sent her, on WhatsApp, 'skiff rebuild "
        "quote: 1900 for the big one, 700 for the kicker, parts extra'. A loose match on a price "
        "for the big one and the kicker makes him the one who set it. The sheet tests the exact "
        "words, from COYLE.",
        (("item2", "mc_price"),),
    ),
    C(
        "C38",
        "role",
        "plain",
        "contradicted",
        "near_window",
        'On March 22, 2025, VARLOW told COYLE where to store the motors, texting her "put them '
        'in 17, not the boathouse".',
        (
            "VARLOW sent the message to COYLE on Mar 22",
            "VARLOW decided where the motors were stored",
        ),
        (("item1", "vc_store"), ("item2", "vc_store")),
        "Sent at 6:15 p.m. PDT on Mar 21 (both copies). Observed data puts it on another day.",
        "Item 1 prints it as 3/22/2025 1:15:10 AM(UTC+0). Reading the printed date passes it. "
        "The sheet names Mar 22, Pacific time.",
        (("item1", "vc_store"),),
    ),
    C(
        "C39",
        "role",
        "plain",
        "unproven",
        "same_name",
        "COYLE recruited PELLOQUIN to haul the stolen motors.",
        ("COYLE recruited PELLOQUIN",),
        (("item3", "pv_offer"), ("item2", "cm_recruit"), ("item2", "cm_recruit2")),
        "No record shows COYLE asking PELLOQUIN. He offered himself to VARLOW ('if u ever need "
        "a driver to pull ur trailer im around'); COYLE asked Item 2's 'Duke' (+12535550151) "
        "'need someone with a truck to pull my skiff trailer to the ramp sat, u in?', and he "
        "said 'sure, sat at 9'. Recruitment of PELLOQUIN by her is not fixed.",
        "DUKE is PELLOQUIN's nickname (paragraph 2). A reading that takes Item 2's 'Duke' for "
        "PELLOQUIN finds her asking him to pull a trailer and his yes, and supports the claim. "
        "The sheet names PELLOQUIN.",
        (("item2", "cm_recruit"),),
    ),
    C(
        "C40",
        "role",
        "affidavit",
        "supported",
        "second_phone",
        'CC-1 put the HAULER in charge of the trailer keys, telling him on WhatsApp "keys '
        'stay with u, nobody else tows it".',
        (
            "VARLOW sent the message to PELLOQUIN",
            "VARLOW put PELLOQUIN in charge of the trailer keys",
        ),
        (("item3", "vw_keys0"), ("item3", "vw_keys"), ("item3", "vw_keys2")),
        "Incoming on Item 3 from VARLOW's WhatsApp at 7:20 p.m. PST on Feb 27. Eight minutes "
        "earlier, opening the thread, he wrote 'left the trailer at ur place. hitch lock and "
        "trailer keys are in ur mailbox', which fixes the keys as the trailer's; the HAULER "
        "answered 'got it, nobody else'.",
        "CC-1's own phone (Item 1) does not hold the exchange. A reading of Item 1 alone "
        "finds nothing. The sheet names no phone, and the check finds Item 3's copy.",
        (("item3", "vw_keys"),),
        "a designation (CC-1), a role (the HAULER), indirect speech",
    ),
    C(
        "C41",
        "role",
        "affidavit",
        "supported",
        "similar_quote",
        "On the night of the KITTIWAKE THEFT, CC-2 kept lookout for SKIP, warning him on "
        'Signal that a "patrol car just passed".',
        (
            "COYLE sent the message to VARLOW on the night of Mar 13",
            "COYLE kept lookout",
        ),
        (("item2", "yl_1"), ("item2", "yl_2"), ("item2", "yl_3"), ("item1", "yl_2")),
        "At 10:58 p.m. PDT she wrote 'parked at the corner of ferrule, ill watch the road', at "
        "11:09 'patrol car just passed, wait', at 11:14 'clear, go'. The thread fixes the role.",
        "The night before, Item 1's 'Mina' (+13605550135) wrote 'patrol car just passed our "
        "street again, u driving home?' to VARLOW. A loose match makes her the lookout. The "
        "sheet tests the exact words, from COYLE, on Signal.",
        (("item1", "mv_patrol"),),
        "defined terms (KITTIWAKE THEFT), a designation, an alias (SKIP), 'the night of' an "
        "event, indirect speech",
    ),
    C(
        "C42",
        "role",
        "affidavit",
        "unproven",
        "contact_name",
        'CC-3 arranged the sale of the stolen motors to the BROKER, telling "Lars" by text '
        'that "the two yamahas are ready".',
        (
            "PELLOQUIN sent the message",
            "PELLOQUIN arranged a sale to the BROKER",
        ),
        (
            ("item3", "pl_yam"),
            ("item3", "pl_yam2"),
            ("item3", "contact:Lars"),
            ("item1", "contact:Lars"),
        ),
        "PELLOQUIN sent the words, on Mar 16, to Item 3's 'Lars', +13605550173, who answered "
        "'thx cuz, my boat misses them'. The BROKER's number (+12535550148, Item 1's 'Lars') is "
        "not in the exchange. A sale to the BROKER is not fixed.",
        "Item 1 saves the BROKER as 'Lars'. A reading that takes Item 3's 'Lars' for the BROKER "
        "supports the claim. The role row names the BROKER's number.",
        (("item3", "contact:Lars"),),
        "a designation (CC-3), a designation for a person who owns no phone (the BROKER), "
        "a contact name in quotes",
    ),
    # ------------------------------------------------------------ event
    C(
        "C43",
        "event",
        "plain",
        "supported",
        "similar_quote",
        "On March 18, 2025, VARLOW and COYLE arranged by text to meet at 6 p.m. on Thursday, "
        "March 20, 2025, at the fuel dock.",
        (
            "VARLOW proposed the meeting by text on Mar 18",
            "'thursday' meant Mar 20",
            "they arranged it",
        ),
        (("item1", "vc_fuel"), ("item2", "vc_fuel"), ("item2", "vc_fuel2")),
        "VARLOW wrote 'fuel dock thursday 6pm' at 10:15 a.m. PDT on Tuesday, Mar 18, and COYLE "
        "answered 'ok'. Thursday after Tuesday Mar 18 is Mar 20.",
        "That morning Item 2's 'Duke' (+12535550151) wrote to her 'bring the skiff to the fuel "
        "dock thursday 8am, ill check the pump'. A loose match takes his Thursday at the fuel "
        "dock for the meeting claimed. The sheet names VARLOW and COYLE.",
        (("item2", "mc_fuel"),),
    ),
    C(
        "C44",
        "event",
        "plain",
        "supported",
        "same_name",
        "On March 4, 2025, COYLE asked VARLOW by text to clear the motors out of the boathouse, "
        "and VARLOW agreed.",
        (
            "COYLE sent the request to VARLOW on Mar 4",
            "VARLOW sent the agreement",
        ),
        (
            ("item1", "cv_clear"),
            ("item1", "cv_clear2"),
            ("item2", "cv_clear"),
            ("item2", "cv_clear2"),
        ),
        "'need the motors out of the boathouse by sat' at 9:30 a.m. PST and 'ok ill clear it "
        "friday' at 9:44 a.m. on Mar 4.",
        "That morning COYLE asked Item 2's 'Emmett' (+12535550159) 'need the kayaks out of the "
        "garage by sat', and he agreed. A reading that takes Item 2's 'Emmett' for EMMETT "
        "VARLOW finds the kayak exchange. The sheet names VARLOW's accounts.",
        (("item2", "cs_kayak"), ("item2", "cs_kayak2")),
    ),
    C(
        "C45",
        "event",
        "plain",
        "unproven",
        "same_name",
        "On March 16, 2025, COYLE and PELLOQUIN spoke by phone for about ten minutes.",
        ("A call between COYLE and PELLOQUIN on Mar 16, 540 to 660 s",),
        (("item2", "cl_cp16"), ("item3", "cl_cp16"), ("item2", "cl_cm16")),
        "Their only call that day is 45 s (11:20 a.m. PDT). The ten-minute call (612 s, 2:40 "
        "p.m.) is with Item 2's 'Duke' (+12535550151). Curated reports, so not shown.",
        "DUKE is PELLOQUIN's nickname (paragraph 2). A reading that takes Item 2's 'Duke' for "
        "PELLOQUIN finds the 612 s call and supports the claim. The sheet names PELLOQUIN.",
        (("item2", "cl_cm16"), ("item2", "contact:Duke")),
    ),
    C(
        "C46",
        "event",
        "affidavit",
        "supported",
        "second_phone",
        "At about 4:50 a.m. that morning, the HAULER let CC-1 know on Telegram that the "
        'trailer was "back in the barn".',
        (
            "PELLOQUIN sent the message to VARLOW at about 4:50 a.m. PDT on Mar 9",
            "the trailer was back",
        ),
        (("item3", "pt_barn"),),
        "Outgoing on Item 3 at 4:47 a.m. PDT on Mar 9: 'all unloaded. trailer is back in the "
        "barn'.",
        "CC-1's own phone (Item 1) does not hold it, and Item 3 prints it as 3:47:10 "
        "AM(UTC-8). A reading of Item 1, or of Item 3's printed time, leaves it unproven. The "
        "sheet names 4:42 to 4:58 a.m. PDT.",
        (("item3", "pt_barn"),),
        "a role (the HAULER), a designation, 'that morning' referring back, an approximate time, "
        "indirect speech",
    ),
    C(
        "C47",
        "event",
        "affidavit",
        "supported",
        "second_number",
        "On the Monday after the HARBOR THEFT, CC-2 offered two outboard motors to the "
        'KELPWISE ACCOUNT on Telegram, which answered "deal, 3k for both, cash".',
        (
            "The KELPWISE ACCOUNT sent the answer to COYLE on Mar 3",
            "COYLE offered two outboard motors",
        ),
        (("item2", "kc_offer"), ("item2", "kc_deal"), ("item2", "kc_ok")),
        "On Mar 3 at 10:05 a.m. PST COYLE wrote '2 outboards, 90s, both run. 3500 for the pair' "
        "to Telegram user id 8820450, which answered 'deal, 3k for both, cash'.",
        "The BROKER's phone number (+12535550148) also texted her that morning ('u get my "
        "telegram?'). A reading that takes the number for the KELPWISE ACCOUNT finds the quote "
        "came from elsewhere. The sheet names Telegram user id 8820450.",
        (("item2", "bc_tg"),),
        "defined terms (HARBOR THEFT, KELPWISE ACCOUNT), a designation, a day set by an event, "
        "a number in words",
    ),
    C(
        "C48",
        "event",
        "affidavit",
        "contradicted",
        "second_phone",
        "After the SURVEILLANCE ended, CC-2 did not call the HAULER again until the RECOVERY.",
        ("No call between COYLE and PELLOQUIN from Mar 20 to 10:40 a.m. Mar 25",),
        (("item3", "cl_cp22"),),
        "Item 3's call log holds an incoming call from COYLE's number at 8:05 p.m. PDT on Mar "
        "22, 140 s.",
        "Item 2's call log does not hold it. A reading of CC-2's own phone finds no call "
        "and leaves the claim unproven. The sheet names no phone.",
        (("item3", "cl_cp22"),),
        "defined terms (SURVEILLANCE, RECOVERY, the HAULER), a designation, a range between two "
        "events",
    ),
)

# One line per claim for the signing sheet.
SUMMARY: dict[str, str] = {
    "C01": "Sent 8:15 p.m. PST Feb 19; Item 1 prints Feb 20 (UTC+0).",
    "C02": "Observed on Items 2 and 3, Mar 4.",
    "C03": "Sent by VARLOW, not COYLE; her 'white cowls' text went to Item 2's 'Duke'.",
    "C04": "No such text; VARLOW wrote 'keep the motors wrapped till the paint cures' to his "
    "foreman.",
    "C05": "The SPARE LINE's text on Item 3, 7:15 p.m. Feb 26; VARLOW's own number gave the "
    "HAULER that number on Feb 20.",
    "C06": "Item 3 (the KYOCERA) received it at 3:41 a.m. PDT Mar 9; Item 2 lacks it.",
    "C07": "Item 1's 'Lars' holds +12535550148; Item 3's 'Lars' is another number.",
    "C08": "Item 1's 'Duke' holds 0138; 0192 is saved as 'Duke work'. Not shown (contact lists "
    "edit).",
    "C09": "Two Telegram ids: 'Skip' 8820484 (another man), 'Em V' 8820411.",
    "C10": "Item 2's 'Captain' holds +13605550163; she wrote 'saved u as captain lol'.",
    "C11": "One Telegram id, 8820422 (Item 2's own); Item 3 shows 'Ren C' to Mar 11, "
    "'harborlights' from Mar 12.",
    "C12": "Item 2's 'Duke' (+12535550151) sent it, not PELLOQUIN's +13605550138.",
    "C13": "9:12 p.m. PST, 236 s; Item 1 prints 9:09 PM(UTC+0) for a 1:09 p.m. call of 38 s.",
    "C14": "3:14 a.m. PDT, 118 s; Item 3 prints 2:14 AM(UTC-8), and 3:12 AM for a 31 s call.",
    "C15": "Sent 9:40 p.m. PDT Mar 12; 8:40 PM is Item 3's UTC-8 print.",
    "C16": "11:48 p.m., 68 s, from the WORK NUMBER (Item 1).",
    "C17": "Sent 4:31 p.m. PDT Mar 15; 11:31 PM is Item 1's UTC print.",
    "C18": "No call on Item 1; the 10:55 a.m. call is on Item 3's log only.",
    "C19": "'the outboards?' / 'ya 4 outboards, two are 150s' fix the meaning.",
    "C20": "Observed; 'the sleeping bags' is not fixed (and she wrote the same words to her "
    "mother).",
    "C21": "Sent 6:05 p.m. PDT Mar 18; Item 1 prints Mar 19 (UTC+0).",
    "C22": "Mar 4 morning; 'ya the soup cans. all 6 fuel tanks' the evening before fixes it.",
    "C23": "'the 150s?' / 'ya both 150 outboards, locked up' fix it.",
    "C24": "Observed; which Duke is not fixed (Item 2's 'Duke' wanted out of a boat show "
    "booth that morning).",
    "C25": "8 on Pacific dates; printed (UTC) dates give 9.",
    "C26": "6 on Item 3; Item 2 has 7.",
    "C27": "6 on Mar 12 Pacific; Item 3's printed Mar 12 gives 4.",
    "C28": "7 texts HAULER to the SPARE LINE, Mar 17-19 on Item 3.",
    "C29": "4 on Item 1 (curated); Item 3 holds 6.",
    "C30": "11 in 11 p.m.-4 a.m. (four real hours, DST began); five hours at one offset gives 13.",
    "C31": "6:25 p.m. PST Feb 18 text; Item 1 prints Feb 19.",
    "C32": "WhatsApp exchange on Mar 27.",
    "C33": "No record with 0148; Item 3's 'Lars' is 0173. Curated, so not shown.",
    "C34": "None 1-2 a.m. PST; WhatsApps at 12:52 a.m. PST and 3:05 a.m. PDT.",
    "C35": "COYLE-PELLOQUIN texts on Mar 26.",
    "C36": "None on Item 1 (curated); Item 3 holds a Mar 28 WhatsApp.",
    "C37": "He asked the price, COYLE set it, he took it.",
    "C38": "Sent 6:15 p.m. PDT Mar 21; Item 1 prints Mar 22 (UTC+0).",
    "C39": "PELLOQUIN offered himself to VARLOW; COYLE asked Item 2's 'Duke', who agreed.",
    "C40": "'trailer keys are in ur mailbox', his instruction and 'got it, nobody else', on "
    "Item 3 only.",
    "C41": "'ill watch the road', 'patrol car just passed, wait', 'clear, go' on Signal.",
    "C42": "Sent to Item 3's 'Lars' (his cousin), not the BROKER; no sale shown.",
    "C43": "Proposal and 'ok' on Mar 18; Thursday is Mar 20. Item 2's 'Duke' set her an 8 "
    "a.m. Thursday at the fuel dock.",
    "C44": "Request and 'ok ill clear it friday' on Mar 4.",
    "C45": "Only a 45 s call; the ten-minute call is with Item 2's 'Duke'.",
    "C46": "4:47 a.m. PDT Mar 9, on Item 3 only.",
    "C47": "Offer, 'deal, 3k for both, cash' and 'ok 3k' with Telegram 8820450 on Mar 3.",
    "C48": "COYLE called PELLOQUIN on Mar 22, on Item 3's log only.",
}

# Affidavit layout: (page, paragraph parts). A part is plain text or a claim id. Paragraphs are
# numbered from 1 in this order.
AFFIDAVIT: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            "I, Sergeant M. Aldecott of the Brackwater County Marine Theft Unit (a fictional "
            "agency), make this affidavit from my training, experience and review of the evidence "
            "described below.",
        ),
    ),
    (
        1,
        (
            "This affidavit relies on forensic extraction reports for three phones. Item 1 is a "
            'Samsung Galaxy Z Flip5 (the "GALAXY") seized from EMMETT VARLOW ("VARLOW" or '
            '"CC-1"), who goes by "SKIP". Item 2 is an Apple iPhone 12 mini seized from '
            'RENATA COYLE ("COYLE" or "CC-2"). Item 3 is a Kyocera DuraForce Ultra 5G (the '
            '"KYOCERA") seized from DUNCAN PELLOQUIN ("PELLOQUIN" or "CC-3"), called '
            '"DUKE", who hauled the stolen equipment on VARLOW\'s trailer for VARLOW and COYLE '
            '(the "HAULER").',
        ),
    ),
    (
        1,
        (
            'VARLOW also used a second phone number, +1 (360) 555-0163 (the "SPARE LINE"). '
            "PELLOQUIN's employer gave him a work phone number, +1 (360) 555-0192 (the \"WORK "
            'NUMBER"), used on a phone that was not seized. A buyer of stolen marine equipment, '
            'referred to below as the "BROKER", used the number +1 (253) 555-0148 and the '
            'Telegram account "kelpwise", user ID 8820450 (the "KELPWISE ACCOUNT").',
        ),
    ),
    (
        1,
        (
            "On the night of Friday, February 28, 2025, into the early hours of Saturday, March "
            "1, 2025, four outboard motors and two chartplotters were taken from boats moored at "
            'Sculpin Harbor Marina on Tidewrack Road (the "HARBOR THEFT").',
        ),
    ),
    (
        1,
        (
            "On the night of Saturday, March 8, 2025, into the early hours of Sunday, March 9, "
            "2025 (the night the clocks went forward, at 2 a.m.), VARLOW and PELLOQUIN "
            "moved the motors from COYLE's boathouse on Halyard Point to a barn on Gannet Lane "
            '(the "TRANSFER").',
        ),
    ),
    (
        1,
        (
            "On Thursday, March 13, 2025, at about 11:15 p.m., two outboard motors and a pallet "
            "of marine batteries were taken from the fenced yard of Kittiwake Marine Supply on "
            'Ferrule Street (the "KITTIWAKE THEFT").',
        ),
    ),
    (
        1,
        (
            "From Monday, March 17, 2025, through Wednesday, March 19, 2025, deputies watched "
            'COYLE\'s boathouse on Halyard Point (the "SURVEILLANCE"). On Tuesday, March 25, '
            "2025, at 10:40 a.m., deputies opened unit 17 at Port Wendle Mini Storage and "
            'recovered three of the outboard motors (the "RECOVERY"). The three phones were '
            "seized on April 8, 2025.",
        ),
    ),
    (1, ("All times in this affidavit are Pacific time, the time the phones themselves kept.",)),
    (2, ("C39", "C31", "C01", "C25")),
    (2, ("C13", "C19", "C05", "C40")),
    (2, ("C07", "C08", "C09", "C10", "C12")),
    (2, ("C47", "C20", "C22", "C29")),
    (2, ("C44", "C02", "C03")),
    (3, ("C30", "C34", "C14", "C06", "C46")),
    (3, ("C04", "C11", "C27", "C15")),
    (3, ("C41", "C16", "C26", "C37")),
    (3, ("C24", "C17", "C45", "C42")),
    (4, ("C28", "C43", "C21", "C38", "C23")),
    (4, ("C48", "C18", "C35", "C32", "C36", "C33")),
    (
        4,
        (
            "Based on the above, I believe there is probable cause that VARLOW, COYLE and "
            "PELLOQUIN took part in the thefts described above and in the sale of the stolen "
            "equipment.",
        ),
    ),
)


# ---------------------------------------------------------------- DRAFT assumption sheet

VAR, COY, PEL = "person:varlow", "person:coyle", "person:pelloquin"
ITEM1, ITEM2, ITEM3 = "dev:item1", "dev:item2", "dev:item3"
SPR2 = "acct:item2:SMS:+13605550163"  # the SPARE LINE, as Item 2 logs it
SPR3 = "acct:item3:SMS:+13605550163"  # the SPARE LINE, as Item 3 logs it
WRK1 = "acct:item1:SMS:+13605550192"  # the WORK NUMBER, as Item 1 logs it
BRK1 = "acct:item1:SMS:+12535550148"  # the BROKER's number (paragraph 3), as Item 1 logs it
KELP2 = "acct:item2:Telegram:8820450"  # the KELPWISE ACCOUNT, as Item 2 logs it
COY_TG2 = "acct:item2:Telegram:8820422"  # CC-2's Telegram account, on her own phone
COY_TG3 = "acct:item3:Telegram:8820422"  # the same account as Item 3 logs it

Expect = Literal["pass", "fail", "inconclusive"] | None


def window(start: str, end_exclusive: str, raw: str, tz: str = TZ) -> dict[str, str]:
    """Wall-clock [start, end_exclusive) in tz -> the contract's inclusive UTC TimeWindow.

    The same arithmetic as core.audit.assumptions.local_window and the case05 sheet. No window
    edge here falls in the 2 a.m. hour of 2025-03-09, which never happened.
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


def days(first: str, last: str, raw: str) -> dict[str, str]:
    """Local calendar days first..last, both whole: midnight to the midnight after the last."""
    end = datetime.fromisoformat(last) + timedelta(days=1)
    return window(first, end.date().isoformat(), raw)


def day(date: str, raw: str) -> dict[str, str]:
    """One local calendar day."""
    return days(date, date, raw)


def about(local: str, raw: str) -> dict[str, str]:
    """'At about H:MM': 8 minutes before to 8 minutes after, end exclusive."""
    t = datetime.fromisoformat(local)
    return window(
        (t - timedelta(minutes=8)).isoformat(), (t + timedelta(minutes=8)).isoformat(), raw
    )


def minute(local: str, raw: str) -> dict[str, str]:
    """'At H:MM': that minute."""
    t = datetime.fromisoformat(local)
    return window(t.isoformat(), (t + timedelta(minutes=1)).isoformat(), raw)


def between(start: str, end: str, raw: str) -> dict[str, str]:
    """'Between H1 and H2': H1:00 through the whole H2:00 minute."""
    e = datetime.fromisoformat(end) + timedelta(minutes=1)
    return window(start, e.isoformat(), raw)


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


# The windows no convention covers: claim id -> the careful examiner's reasoning. Every window
# in these claims' rows is the examiner's; every other window follows a convention, and
# tests/test_synthetic_case06.py recomputes each one from the claim's words. SIGNING_SHEET.md
# lists these under their own heading.
NON_CONVENTION: dict[str, str] = {
    "C16": "'Within an hour after' the KITTIWAKE THEFT, which paragraph 6 puts at about 11:15 "
    "p.m. on March 13: the hour from 11:15 p.m. to 12:15 a.m. The 'about' in the event's time "
    "is not widened; the theft's stated time is the anchor.",
    "C18": "'Within half an hour after' the RECOVERY, which paragraph 7 puts at 10:40 a.m. on "
    "March 25: 10:40 to 11:10 a.m.",
    "C22": "'The next morning' after March 3 (the sentence before, C20): March 4, morning read as "
    "5 a.m. to noon.",
    "C34": "'The hour before the clocks went forward that night' (the night of the TRANSFER): the "
    "clocks jumped from 2 to 3 a.m. on March 9, so the hour is 1 to 2 a.m. PST, 09:00 to 10:00 "
    "UTC (written as 1 a.m. to 3 a.m. wall clock, the same instants).",
    "C41": "'The night of' the KITTIWAKE THEFT (Thursday, March 13): 6 p.m. on March 13 to 6 "
    "a.m. on March 14.",
    "C48": "'After the SURVEILLANCE ended' (its last day is Wednesday, March 19) 'until the "
    "RECOVERY' (10:40 a.m. on March 25): midnight starting March 20 to 10:40 a.m. on March 25.",
}

Q01 = "check the dinghy dock after 9, its quiet"
Q02 = "boathouse key is on the nail in the shed"
Q03 = "the white cowls are off, come see tonight"
Q04 = "the motors stay wrapped till the heat dies down"
Q05 = "bring the long straps and the dolly"
Q06 = "leave the trailer at the barn, not the boathouse"
Q12 = "the lower unit is shot"
Q15 = "barn code is 4417 now, dont lose it"
Q17 = "move the trailer behind the barn tonight"
Q19 = "spotted 4 big fish on the north float"
Q20 = "keep the sleeping bags dry"
Q21 = "the guard naps after 2, every night"
Q22 = "bring the soup cans to the boathouse"
Q23 = "the twins are in 17"
Q24 = "duke wants out"
Q37 = "2200 for the big ones, 900 for the kickers"
Q38 = "put them in 17, not the boathouse"
Q40 = "keys stay with u, nobody else tows it"
Q41 = "patrol car just passed"
Q42 = "the two yamahas are ready"
Q43 = "fuel dock thursday 6pm"
Q44_ASK = "need the motors out of the boathouse by sat"
Q44_OK = "ok ill clear it friday"
Q46 = "back in the barn"
Q47 = "deal, 3k for both, cash"

C22_MORNING = window(
    "2025-03-04T05:00:00",
    "2025-03-04T12:00:00",
    "The next morning (March 4, 2025, 5 a.m. to noon)",
)
C46_ABOUT = about("2025-03-09T04:50", "At about 4:50 a.m. that morning (March 9, 2025)")
C47_MONDAY = day("2025-03-03", "On the Monday after the HARBOR THEFT (March 3, 2025)")

SHEET: tuple[ClaimSpec, ...] = (
    # ------------------------------------------------------------ communication
    ClaimSpec(
        "C01",
        (
            A(
                "sender",
                P(quoted_text=Q01, person_ids=[VAR], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q01,
                    person_ids=[VAR, COY],
                    channels=["SMS"],
                    window=day("2025-02-19", "On February 19, 2025"),
                ),
                "pass",
                "8:15 p.m. PST Feb 19; Item 1 prints 2/20 4:15:40 AM(UTC+0).",
            ),
        ),
    ),
    ClaimSpec(
        "C02",
        (
            A(
                "sender",
                P(quoted_text=Q02, person_ids=[COY], channels=["WhatsApp"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q02,
                    person_ids=[COY, PEL],
                    channels=["WhatsApp"],
                    window=day("2025-03-04", "On March 4, 2025"),
                ),
                "pass",
                "4:10 p.m. PST Mar 4.",
            ),
        ),
    ),
    ClaimSpec(
        "C03",
        (
            A(
                "sender",
                P(quoted_text=Q03, person_ids=[COY], channels=["SMS"]),
                "fail",
                "Both copies came from VARLOW's +13605550114, not from COYLE.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q03,
                    person_ids=[VAR, COY],
                    channels=["SMS"],
                    window=day("2025-03-06", "On March 6, 2025"),
                ),
                "pass",
                "11:45 a.m. PST Mar 6, between their numbers.",
            ),
        ),
    ),
    ClaimSpec(
        "C04",
        (
            A(
                "sender",
                P(quoted_text=Q04, person_ids=[VAR], channels=["SMS"]),
                "inconclusive",
                "No message with these words on any phone.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q04,
                    person_ids=[VAR, PEL],
                    channels=["SMS"],
                    window=day("2025-03-10", "The day after the TRANSFER (Monday, March 10, 2025)"),
                ),
                "inconclusive",
                "The TRANSFER ended on March 9, so the day after is March 10. Not found.",
            ),
        ),
    ),
    ClaimSpec(
        "C05",
        (
            A(
                "sender",
                P(quoted_text=Q05, account_ids=[SPR3], channels=["SMS"]),
                "pass",
                "Incoming on Item 3 from the SPARE LINE (paragraph 3).",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q05,
                    person_ids=[PEL],
                    account_ids=[SPR3],
                    channels=["SMS"],
                    window=day(
                        "2025-02-26",
                        "Two days before the HARBOR THEFT (Wednesday, February 26, 2025)",
                    ),
                ),
                "pass",
                "The HARBOR THEFT began on February 28. 7:15 p.m. PST Feb 26.",
            ),
            A(
                "authorship",
                P(quoted_text=Q05, person_ids=[VAR], account_ids=[SPR3], channels=["SMS"]),
                None,
                "That VARLOW used the SPARE LINE: paragraph 3; his own number's 'new number "
                "for boat stuff is 360 555 0163. this one stays personal' to the HAULER (Items 1 "
                "and 3, Feb 20); 0163's 'this is the other number' to him twenty minutes later "
                "(Item 3); his own number's 'use the other number' (Mar 19, Items 1 and 3). "
                "Note: Item 3 saves 0163 as 'Skip 2' and another number, +13605550184, as "
                "'Skip', so 0163's 'its skip' to COYLE does not tie it to VARLOW by itself. Core: "
                "the expert decides it.",
            ),
        ),
    ),
    ClaimSpec(
        "C06",
        (
            A(
                "sender",
                P(quoted_text=Q06, person_ids=[COY], channels=["Telegram"]),
                "pass",
                "CC-2 is COYLE; her Telegram (8820422) sent it.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q06,
                    person_ids=[COY, PEL],
                    device_ids=[ITEM3],
                    channels=["Telegram"],
                    window=about("2025-03-09T03:40", "At about 3:40 a.m. on March 9, 2025"),
                ),
                "pass",
                "The KYOCERA is Item 3 (paragraph 2). 3:41 a.m. PDT Mar 9 (printed 2:41:30 "
                "AM(UTC-8)).",
            ),
        ),
    ),
    # ------------------------------------------------------------ identity
    ClaimSpec(
        "C07",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM1], quoted_text="Lars", account_ids=[BRK1]),
                "pass",
                "Item 1's 'Lars' holds +12535550148.",
            ),
        ),
    ),
    ClaimSpec(
        "C08",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM1], quoted_text="Duke", account_ids=[WRK1]),
                "inconclusive",
                "Item 1's 'Duke' holds +13605550138; a missing entry is never a fail.",
            ),
        ),
        (
            "Unproven, not contradicted: the contact check never fails on a missing entry "
            "(contact lists are edited, and a curated report may leave entries out), so Item 1's "
            "'Duke' holding +13605550138 does not rule out an entry 'Duke' with +13605550192.",
        ),
    ),
    ClaimSpec(
        "C09",
        (
            A(
                "same_account",
                P(channels=["Telegram"], handles=["Skip", "Em V"], device_ids=[ITEM3]),
                "fail",
                "'Skip' resolves to user id 8820484 and 'Em V' to 8820411.",
            ),
        ),
    ),
    ClaimSpec(
        "C10",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM2], quoted_text="Captain", account_ids=[SPR2]),
                "pass",
                "'Her phone' is Item 2 (CC-2 is COYLE).",
            ),
        ),
    ),
    ClaimSpec(
        "C11",
        (
            A(
                "same_account",
                P(channels=["Telegram"], handles=["Ren C", "harborlights"], device_ids=[ITEM3]),
                "pass",
                "Both names resolve to Telegram user id 8820422 (Item 2's own account). The "
                "check resolves names on every phone, not only Item 3; on Telegram only Item 3 "
                "shows her account to someone else.",
            ),
            A(
                "person_identity",
                P(
                    person_ids=[COY],
                    account_ids=[COY_TG2, COY_TG3],
                    channels=["Telegram"],
                ),
                None,
                "That user id 8820422 is CC-2's: it is Item 2's own Telegram account (its "
                "User Accounts sheet, and the outgoing copies on Item 2), and Item 2 is COYLE's "
                "phone (the shared device attribution). Core: the expert decides it.",
            ),
        ),
        (
            "same_account passes because the account's display name is the first name Item 3 "
            "shows ('Ren C'), and the thread title and later rows' sender cells show "
            "'harborlights'. No row tests when the name changed: 'until March 12' rests on the "
            "printed rows (last 'Ren C' 8:41 p.m. Mar 11, first 'harborlights' 4:45 p.m. Mar "
            "12).",
        ),
    ),
    ClaimSpec(
        "C12",
        (
            A(
                "sender",
                P(quoted_text=Q12, person_ids=[PEL], channels=["SMS"]),
                "fail",
                "The one copy came from +12535550151, Item 2's 'Duke', not from PELLOQUIN.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q12,
                    channels=["SMS"],
                    device_ids=[ITEM2],
                    window=day("2025-03-11", "on March 11, 2025"),
                ),
                "pass",
                "9:40 a.m. PDT Mar 11, on Item 2.",
            ),
        ),
        gaps=("That CC-2 received it is shown by the time row's phone (Item 2), not by a party.",),
    ),
    # ------------------------------------------------------------ timing
    ClaimSpec(
        "C13",
        (
            A(
                "record_time",
                P(
                    person_ids=[VAR, PEL],
                    channels=["call"],
                    duration_s=(180, 300),
                    window=about("2025-02-21T21:10", "At about 9:10 p.m. on February 21, 2025"),
                ),
                "pass",
                "9:12:40 p.m. PST, 236 s. 'About four minutes' is 180 to 300 s.",
            ),
        ),
    ),
    ClaimSpec(
        "C14",
        (
            A(
                "record_time",
                P(
                    person_ids=[VAR, PEL],
                    channels=["call"],
                    duration_s=(90, 150),
                    window=about("2025-03-09T03:15", "At about 3:15 a.m. on March 9, 2025"),
                ),
                "pass",
                "3:14:20 a.m. PDT, 118 s. 3:07 to 3:23 a.m. is after the jump, all PDT.",
            ),
        ),
    ),
    ClaimSpec(
        "C15",
        (
            A(
                "sender",
                P(quoted_text=Q15, person_ids=[PEL], channels=["SMS"]),
                "pass",
                "Outgoing on Item 3.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q15,
                    person_ids=[PEL, VAR],
                    channels=["SMS"],
                    window=minute("2025-03-12T20:40", "At 8:40 p.m. on March 12, 2025"),
                ),
                "fail",
                "Sent 9:40:15 p.m. PDT; Item 3 prints 8:40:15 PM(UTC-8).",
            ),
        ),
    ),
    ClaimSpec(
        "C16",
        (
            A(
                "record_time",
                P(
                    person_ids=[VAR],
                    account_ids=[WRK1],
                    channels=["call"],
                    duration_s=(45, 75),
                    window=window(
                        "2025-03-13T23:15:00",
                        "2025-03-14T00:15:00",
                        "Within an hour after the KITTIWAKE THEFT (11:15 p.m. on March 13 to "
                        "12:15 a.m. on March 14, 2025)",
                    ),
                ),
                "pass",
                "Examiner's window: " + NON_CONVENTION["C16"] + " 11:48:10 p.m. PDT, 68 s.",
            ),
        ),
    ),
    ClaimSpec(
        "C17",
        (
            A(
                "sender",
                P(quoted_text=Q17, person_ids=[VAR], channels=["WhatsApp"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q17,
                    person_ids=[VAR, PEL],
                    channels=["WhatsApp"],
                    window=about(
                        "2025-03-15T23:30",
                        "Two days before the SURVEILLANCE began, at about 11:30 p.m. (March 15, "
                        "2025)",
                    ),
                ),
                "fail",
                "The SURVEILLANCE began March 17. Sent 4:31 p.m. PDT Mar 15; Item 1 prints "
                "11:31:20 PM(UTC+0).",
            ),
        ),
    ),
    ClaimSpec(
        "C18",
        (
            A(
                "record_time",
                P(
                    person_ids=[VAR, PEL],
                    device_ids=[ITEM1],
                    channels=["call"],
                    window=window(
                        "2025-03-25T10:40:00",
                        "2025-03-25T11:10:00",
                        "Within half an hour after the RECOVERY (10:40 to 11:10 a.m., March "
                        "25, 2025)",
                    ),
                ),
                "inconclusive",
                "Examiner's window: "
                + NON_CONVENTION["C18"]
                + " The GALAXY is Item 1; no call there. Item 3 holds one at 10:55 a.m.",
            ),
        ),
    ),
    # ------------------------------------------------------------ content meaning
    ClaimSpec(
        "C19",
        (
            A(
                "sender",
                P(quoted_text=Q19, person_ids=[VAR], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q19,
                    person_ids=[VAR, COY],
                    channels=["SMS"],
                    window=day("2025-02-24", "On February 24, 2025"),
                ),
                "pass",
                "11:20 a.m. PST Feb 24.",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q19,
                    person_ids=[VAR, COY],
                    channels=["SMS"],
                    window=day("2025-02-24", "On February 24, 2025"),
                ),
                None,
                "'the outboards?' / 'ya 4 outboards, two are 150s' in the same exchange.",
            ),
        ),
    ),
    ClaimSpec(
        "C20",
        (
            A(
                "sender",
                P(quoted_text=Q20, person_ids=[COY], channels=["SMS"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q20,
                    person_ids=[COY, VAR],
                    channels=["SMS"],
                    window=day("2025-03-03", "On March 3, 2025"),
                ),
                "pass",
                "2:15 p.m. PST Mar 3.",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q20,
                    person_ids=[COY, VAR],
                    channels=["SMS"],
                    window=day("2025-03-03", "On March 3, 2025"),
                ),
                None,
                "Not fixed: VARLOW answered only 'will do'.",
            ),
        ),
    ),
    ClaimSpec(
        "C21",
        (
            A(
                "sender",
                P(quoted_text=Q21, person_ids=[COY], channels=["SMS"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q21,
                    person_ids=[COY, VAR],
                    channels=["SMS"],
                    window=day("2025-03-19", "On March 19, 2025"),
                ),
                "fail",
                "Sent 6:05 p.m. PDT Mar 18; Item 1 prints 3/19 1:05:20 AM(UTC+0).",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q21,
                    person_ids=[COY, VAR],
                    channels=["SMS"],
                    window=day("2025-03-19", "On March 19, 2025"),
                ),
                None,
                "That the words told him when the yard was unwatched.",
            ),
        ),
    ),
    ClaimSpec(
        "C22",
        (
            A(
                "sender",
                P(quoted_text=Q22, person_ids=[VAR], channels=["Telegram"]),
                "pass",
                "SKIP is VARLOW; outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q22,
                    person_ids=[VAR, PEL],
                    channels=["Telegram"],
                    window=C22_MORNING,
                ),
                "pass",
                "Examiner's window: " + NON_CONVENTION["C22"] + " 9:20 a.m. PST Mar 4.",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q22,
                    person_ids=[VAR, PEL],
                    channels=["Telegram"],
                    window=C22_MORNING,
                ),
                None,
                "'ya the soup cans. all 6 fuel tanks' (Mar 3) and 'all 6 tanks ya' in the "
                "thread. Examiner's window: " + NON_CONVENTION["C22"],
            ),
        ),
    ),
    ClaimSpec(
        "C23",
        (
            A(
                "sender",
                P(quoted_text=Q23, account_ids=[SPR2]),
                "pass",
                "Incoming on Item 2 from the SPARE LINE.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q23,
                    person_ids=[COY],
                    account_ids=[SPR2],
                    window=day(
                        "2025-03-22", "Three days before the RECOVERY (Saturday, March 22, 2025)"
                    ),
                ),
                "pass",
                "The RECOVERY was March 25. 11:40 a.m. PDT Mar 22.",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q23,
                    person_ids=[COY],
                    account_ids=[SPR2],
                    window=day(
                        "2025-03-22", "Three days before the RECOVERY (Saturday, March 22, 2025)"
                    ),
                ),
                None,
                "'the 150s?' / 'ya both 150 outboards, locked up' in the same exchange; '150' "
                "is an outboard's horsepower, as in the Feb 24 thread ('ya 4 outboards, two are "
                "150s').",
            ),
        ),
    ),
    ClaimSpec(
        "C24",
        (
            A(
                "sender",
                P(quoted_text=Q24, person_ids=[COY]),
                "pass",
                "A text, outgoing on Item 2 and incoming on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q24,
                    person_ids=[COY, VAR],
                    window=day(
                        "2025-03-15",
                        "Two days after the KITTIWAKE THEFT (Saturday, March 15, 2025)",
                    ),
                ),
                "pass",
                "The KITTIWAKE THEFT was March 13. 7:10 p.m. PDT Mar 15 (Item 1 prints Mar 16).",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q24,
                    person_ids=[COY, VAR],
                    window=day(
                        "2025-03-15",
                        "Two days after the KITTIWAKE THEFT (Saturday, March 15, 2025)",
                    ),
                ),
                None,
                "Not fixed: which Duke.",
            ),
        ),
    ),
    # ------------------------------------------------------------ count
    ClaimSpec(
        "C25",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM1],
                    person_ids=[VAR, COY],
                    channels=["Signal"],
                    expected_count=8,
                    count_op="eq",
                    each_way=True,
                    window=days(
                        "2025-02-17", "2025-02-23", "Between February 17 and February 23, 2025"
                    ),
                ),
                "pass",
                "Eight on Pacific dates; printed (UTC) dates give nine.",
            ),
        ),
    ),
    ClaimSpec(
        "C26",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM3],
                    person_ids=[PEL, COY],
                    channels=["WhatsApp"],
                    expected_count=6,
                    count_op="eq",
                    each_way=True,
                    window=days("2025-03-10", "2025-03-14", "From March 10 through March 14, 2025"),
                ),
                "pass",
                "Six on Item 3; Item 2 holds seven.",
            ),
        ),
    ),
    ClaimSpec(
        "C27",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM3],
                    person_ids=[PEL, VAR],
                    channels=["SMS"],
                    expected_count=4,
                    count_op="eq",
                    each_way=True,
                    window=day("2025-03-12", "On March 12, 2025"),
                ),
                "fail",
                "Six on the Pacific day; Item 3's printed Mar 12 holds four.",
            ),
        ),
    ),
    ClaimSpec(
        "C28",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM3],
                    person_ids=[PEL],
                    account_ids=[SPR3],
                    channels=["SMS"],
                    expected_count=7,
                    count_op="eq",
                    sent_by=[PEL],
                    window=days(
                        "2025-03-17",
                        "2025-03-19",
                        "During the SURVEILLANCE (Monday, March 17 to Wednesday, March 19, 2025)",
                    ),
                ),
                "pass",
                "Seven from PELLOQUIN to the SPARE LINE on Item 3 (the KYOCERA).",
            ),
        ),
    ),
    ClaimSpec(
        "C29",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM1],
                    person_ids=[VAR, PEL],
                    channels=["WhatsApp"],
                    expected_count=6,
                    count_op="ge",
                    window=days("2025-03-03", "2025-03-07", "Between March 3 and March 7, 2025"),
                ),
                "inconclusive",
                "Four on the GALAXY (Item 1); fewer than claimed is never a fail.",
            ),
        ),
    ),
    ClaimSpec(
        "C30",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM2],
                    person_ids=[VAR, COY],
                    channels=["Signal"],
                    expected_count=11,
                    count_op="eq",
                    each_way=True,
                    window=between(
                        "2025-03-08T23:00:00",
                        "2025-03-09T04:00:00",
                        "On the night of the TRANSFER, between 11 p.m. and 4 a.m. (11 p.m. PST on "
                        "March 8 to 4:00:59 a.m. PDT on March 9, 2025)",
                    ),
                ),
                "pass",
                "The 'between' convention on the night the TRANSFER began (March 8 into 9): "
                "07:00:00 to 11:00:59.999999 UTC, four real hours and a minute. Eleven on Item 2.",
            ),
        ),
    ),
    # ------------------------------------------------------------ absence
    ClaimSpec(
        "C31",
        (
            A(
                "no_contact",
                P(person_ids=[VAR, PEL], window=day("2025-02-18", "on February 18, 2025")),
                "fail",
                "The 6:25 and 6:31 p.m. PST texts.",
            ),
        ),
    ),
    ClaimSpec(
        "C32",
        (
            A(
                "no_contact",
                P(
                    person_ids=[COY, VAR],
                    window=days("2025-03-26", "2025-03-28", "between March 26 and March 28, 2025"),
                ),
                "fail",
                "The Mar 27 WhatsApp exchange. No channel: the claim says any kind.",
            ),
        ),
    ),
    ClaimSpec(
        "C33",
        (
            A(
                "no_contact",
                P(
                    person_ids=[PEL],
                    account_ids=[BRK1],
                    window=days("2025-03-01", "2025-03-31", "between March 1 and March 31, 2025"),
                ),
                "inconclusive",
                "None found; curated reports. Item 3's 'Lars' is another number.",
            ),
        ),
    ),
    ClaimSpec(
        "C34",
        (
            A(
                "no_contact",
                P(
                    person_ids=[PEL, COY],
                    window=window(
                        "2025-03-09T01:00:00",
                        "2025-03-09T03:00:00",
                        "In the hour before the clocks went forward that night (1 to 2 a.m. "
                        "PST, March 9, 2025)",
                    ),
                ),
                "inconclusive",
                "Examiner's window: "
                + NON_CONVENTION["C34"]
                + " None in the hour; the WhatsApps at 12:52 a.m. PST and 3:05 a.m. PDT fall "
                "either side.",
            ),
        ),
    ),
    ClaimSpec(
        "C35",
        (
            A(
                "no_contact",
                P(
                    person_ids=[COY, PEL],
                    window=days(
                        "2025-03-26",
                        "2025-03-27",
                        "On the two days after the RECOVERY (March 26 and 27, 2025)",
                    ),
                ),
                "fail",
                "DUKE is PELLOQUIN (paragraph 2). Texts on Mar 26.",
            ),
        ),
    ),
    ClaimSpec(
        "C36",
        (
            A(
                "no_contact",
                P(
                    person_ids=[VAR, PEL],
                    device_ids=[ITEM1],
                    window=days(
                        "2025-03-26",
                        "2025-03-31",
                        "From the day after the RECOVERY through March 31, 2025",
                    ),
                ),
                "inconclusive",
                "None on Item 1 (the GALAXY); curated. Item 3 holds a Mar 28 WhatsApp.",
            ),
        ),
    ),
    # ------------------------------------------------------------ role
    ClaimSpec(
        "C37",
        (
            A(
                "sender",
                P(quoted_text=Q37, person_ids=[COY], channels=["WhatsApp"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q37,
                    person_ids=[COY, PEL],
                    channels=["WhatsApp"],
                    window=day("2025-03-14", "On March 14, 2025"),
                ),
                "pass",
                "1:06 p.m. PDT Mar 14.",
            ),
            A(
                "role",
                P(person_ids=[COY]),
                None,
                "That COYLE set the price: he asked, she named it, he took it.",
            ),
        ),
    ),
    ClaimSpec(
        "C38",
        (
            A(
                "sender",
                P(quoted_text=Q38, person_ids=[VAR], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q38,
                    person_ids=[VAR, COY],
                    channels=["SMS"],
                    window=day("2025-03-22", "On March 22, 2025"),
                ),
                "fail",
                "Sent 6:15 p.m. PDT Mar 21; Item 1 prints 3/22 1:15:10 AM(UTC+0).",
            ),
            A("role", P(person_ids=[VAR]), None, "That VARLOW decided where they were stored."),
        ),
    ),
    ClaimSpec(
        "C39",
        (A("role", P(person_ids=[COY, PEL]), None, "That COYLE recruited PELLOQUIN."),),
        (
            "Role only: no check tests recruitment. PELLOQUIN offered himself to VARLOW (Feb 14); "
            "COYLE's request to pull her skiff trailer went to Item 2's 'Duke' (+12535550151), "
            "who agreed.",
        ),
    ),
    ClaimSpec(
        "C40",
        (
            A(
                "sender",
                P(quoted_text=Q40, person_ids=[VAR], channels=["WhatsApp"]),
                "pass",
                "CC-1 is VARLOW; his WhatsApp sent it (on Item 3 only).",
            ),
            A(
                "role",
                P(person_ids=[VAR, PEL]),
                None,
                "That VARLOW put him in charge of the trailer keys: 'left the trailer at ur "
                "place. hitch lock and trailer keys are in ur mailbox' (7:12 p.m.), his "
                "instruction, 'got it, nobody else' (Item 3).",
            ),
        ),
    ),
    ClaimSpec(
        "C41",
        (
            A(
                "sender",
                P(quoted_text=Q41, person_ids=[COY], channels=["Signal"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q41,
                    person_ids=[COY, VAR],
                    channels=["Signal"],
                    window=window(
                        "2025-03-13T18:00:00",
                        "2025-03-14T06:00:00",
                        "On the night of the KITTIWAKE THEFT (6 p.m. on March 13 to 6 a.m. on "
                        "March 14, 2025)",
                    ),
                ),
                "pass",
                "Examiner's window: " + NON_CONVENTION["C41"] + " 11:09 p.m. PDT Mar 13.",
            ),
            A("role", P(person_ids=[COY]), None, "That COYLE kept lookout: her thread that night."),
        ),
    ),
    ClaimSpec(
        "C42",
        (
            A(
                "sender",
                P(quoted_text=Q42, person_ids=[PEL], channels=["SMS"]),
                "pass",
                "CC-3 is PELLOQUIN; outgoing on Item 3, to Item 3's 'Lars'.",
            ),
            A(
                "role",
                P(person_ids=[PEL], account_ids=[BRK1]),
                None,
                "That PELLOQUIN arranged a sale to the BROKER (+12535550148): not shown.",
            ),
        ),
    ),
    # ------------------------------------------------------------ event
    ClaimSpec(
        "C43",
        (
            A(
                "sender",
                P(quoted_text=Q43, person_ids=[VAR], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q43,
                    person_ids=[VAR, COY],
                    channels=["SMS"],
                    window=day("2025-03-18", "On March 18, 2025"),
                ),
                "pass",
                "10:15 a.m. PDT Mar 18.",
            ),
            A(
                "weekday_date",
                P(
                    quoted_text=Q43,
                    channels=["SMS"],
                    window=day("2025-03-20", "Thursday, March 20, 2025"),
                ),
                "pass",
                "'thursday' sent on Tuesday Mar 18 is Mar 20.",
            ),
            A(
                "event",
                P(
                    person_ids=[VAR, COY],
                    channels=["SMS"],
                    window=day("2025-03-18", "On March 18, 2025"),
                ),
                None,
                "That they arranged it: COYLE's 'ok'.",
            ),
        ),
        gaps=(
            "'At the fuel dock' and '6 p.m.' are tested only as words inside the quote, which "
            "the sender check matches verbatim; whether anyone met there is not tested.",
        ),
    ),
    ClaimSpec(
        "C44",
        (
            A(
                "sender",
                P(quoted_text=Q44_ASK, person_ids=[COY], channels=["SMS"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "sender",
                P(quoted_text=Q44_OK, person_ids=[VAR], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q44_ASK,
                    person_ids=[COY, VAR],
                    channels=["SMS"],
                    window=day("2025-03-04", "On March 4, 2025"),
                ),
                "pass",
                "9:30 a.m. PST Mar 4.",
            ),
            A(
                "event",
                P(
                    person_ids=[COY, VAR],
                    channels=["SMS"],
                    window=day("2025-03-04", "On March 4, 2025"),
                ),
                None,
                "That the request and the agreement are what the claim states.",
            ),
        ),
    ),
    ClaimSpec(
        "C45",
        (
            A(
                "record_time",
                P(
                    person_ids=[COY, PEL],
                    channels=["call"],
                    duration_s=(540, 660),
                    window=day("2025-03-16", "On March 16, 2025"),
                ),
                "inconclusive",
                "Their only call that day is 45 s; 'about ten minutes' is 540 to 660 s.",
            ),
        ),
    ),
    ClaimSpec(
        "C46",
        (
            A(
                "sender",
                P(quoted_text=Q46, person_ids=[PEL], channels=["Telegram"]),
                "pass",
                "The HAULER is PELLOQUIN; outgoing on Item 3.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q46,
                    person_ids=[PEL, VAR],
                    channels=["Telegram"],
                    window=C46_ABOUT,
                ),
                "pass",
                "'That morning' is March 9 (the sentence before, C06). 4:47 a.m. PDT (Item 3 "
                "prints 3:47:10 AM(UTC-8)).",
            ),
            A(
                "event",
                P(person_ids=[PEL, VAR], channels=["Telegram"], window=C46_ABOUT),
                None,
                "That the trailer was back: 'all unloaded. trailer is back in the barn'.",
            ),
        ),
    ),
    ClaimSpec(
        "C47",
        (
            A(
                "sender",
                P(quoted_text=Q47, account_ids=[KELP2], channels=["Telegram"]),
                "pass",
                "Incoming on Item 2 from the KELPWISE ACCOUNT (paragraph 3).",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q47,
                    person_ids=[COY],
                    account_ids=[KELP2],
                    channels=["Telegram"],
                    window=C47_MONDAY,
                ),
                "pass",
                "The HARBOR THEFT ended Saturday, March 1. 10:40 a.m. PST Mar 3.",
            ),
            A(
                "event",
                P(
                    person_ids=[COY],
                    account_ids=[KELP2],
                    channels=["Telegram"],
                    window=C47_MONDAY,
                ),
                None,
                "That she offered two outboard motors: '2 outboards, 90s, both run. 3500 for "
                "the pair'.",
            ),
        ),
    ),
    ClaimSpec(
        "C48",
        (
            A(
                "no_contact",
                P(
                    person_ids=[COY, PEL],
                    channels=["call"],
                    window=window(
                        "2025-03-20T00:00:00",
                        "2025-03-25T10:40:00",
                        "After the SURVEILLANCE ended (from midnight on March 20, 2025, until the "
                        "RECOVERY at 10:40 a.m. on March 25, 2025)",
                    ),
                ),
                "fail",
                "Examiner's window: "
                + NON_CONVENTION["C48"]
                + " COYLE's 8:05 p.m. Mar 22 call, on Item 3's log.",
            ),
        ),
        gaps=(
            "The row tests any call between them; the claim says CC-2 placed it, which the "
            "one call found (outgoing from her number) also shows.",
        ),
    ),
)

NO_SHEET: dict[str, str] = {}

# Where an alias the affidavit defines (case.json "aliases") matches a name inside a claim's
# quote. An alias is matched whole, in any case, so these match; that is real product behaviour
# and the claims keep their wording. Each line says which person the match points to, and
# whether that is right, so the signer sees it.
ALIAS_IN_QUOTES: dict[str, str] = {
    "C08": 'DUKE matches the quoted contact name "Duke" and points to PELLOQUIN. Right person, '
    "other number: Item 1's 'Duke' holds PELLOQUIN's own +13605550138; the claim's "
    "+13605550192 is saved as 'Duke work'.",
    "C09": 'SKIP matches the quoted Telegram name "Skip" and points to VARLOW. Wrong: on Item 3, '
    "Telegram 'Skip' is another man, user id 8820484 (also 'Skip', +13605550184). (\"Em V\" "
    "matches no alias.)",
    "C12": 'DUKE matches the quoted sender name "Duke" and points to PELLOQUIN. Wrong: on Item 2, '
    "'Duke' is +12535550151, a mechanic by his own texts. The claim's own 'the HAULER' is "
    "PELLOQUIN, rightly.",
    "C24": 'DUKE matches "duke" in the quote "duke wants out" and points to PELLOQUIN. Not '
    "fixed: Item 2 also saves another number as 'Duke' (+12535550151), and the conversation "
    "does not say which Duke is meant. The claim's own 'the HAULER' is PELLOQUIN.",
}

# Verdicts a second read changed: claim id -> the verdict first drafted. Empty until a second
# reader reads the draft.
FIRST_DRAFT_VERDICT: dict[str, str] = {}

SECOND_READ_DATE = "2026-11-03"


@dataclass(frozen=True)
class Finding:
    finding_id: str
    claims: tuple[str, ...]
    severity: str  # wrong verdict, sheet, weak, cosmetic (graded by the builder)
    outcome: Literal["fixed", "kept"]
    answer: str


# The second blind read's findings, one line each, once a second reader has read the draft.
SECOND_READ: tuple[Finding, ...] = (
    Finding(
        "R1",
        ("C40", "C02"),
        "wrong verdict",
        "fixed",
        "Agreed: as drafted no record fixed 'trailer', and paragraph 2 made the trailer his own. "
        "The data changed, not the verdict: the trailer is now VARLOW's (paragraph 2; his offer "
        "'if u ever need a driver to pull ur trailer im around'), the WhatsApp thread on Item 3 "
        "now opens with 'left the trailer at ur place. hitch lock and trailer keys are in ur "
        "mailbox' eight minutes before the quote, the quote reads 'nobody else tows it', and the "
        "core row says trailer keys. C02's text is now about the boathouse key, so no record "
        "points the keys elsewhere. Supported, now fixed by the records.",
    ),
    Finding(
        "R2",
        ("C39",),
        "weak",
        "fixed",
        "Agreed: the decoy said no, so the described trap did not support. Item 2's 'Duke' now "
        "answers her 'need someone with a truck to pull my skiff trailer to the ramp sat, u in?' "
        "with 'sure, sat at 9', so taking him for PELLOQUIN does find a yes. Hazard and gap "
        "rewritten. Unproven unchanged.",
    ),
    Finding(
        "R3",
        ("C12", "C24", "C37", "C43", "C35", "C45", "C03"),
        "weak",
        "fixed",
        "Agreed: three of his texts read like an insider's. Item 2's 'Duke' (+12535550151) is "
        "now plainly her mechanic: he opens with 'this is duke at marchetti marine. ur skiff is "
        "in bay 2', quotes a 'skiff rebuild quote: 1900 for the big one, 700 for the kicker, "
        "parts extra', wants out of 'the boat show booth', and sets her own 8 a.m. Thursday at "
        "the fuel dock for the skiff. No text of his touches the scheme's prices, plans or "
        "times. Verdicts unchanged: C12 contradicted, C24 unproven, C37 and C43 supported.",
    ),
    Finding(
        "R4",
        ("C05",),
        "sheet",
        "fixed",
        "Agreed: the key now cites 0163's 'this is the other number' (Item 3, Feb 20) and "
        "VARLOW's 'use the other number' (Mar 19, Items 1 and 3), and the authorship note says "
        "Item 3 saves +13605550184 as 'Skip' beside 0163 as 'Skip 2', so 'its skip' is not "
        "relied on. Supported unchanged.",
    ),
    Finding(
        "R5",
        ("C09", "C12", "C24", "C35", "C39", "C45"),
        "sheet",
        "fixed",
        "Agreed: the sheet now says plainly that SKIP and DUKE equal the first names of two "
        "people who own no phone, on purpose (the same-name hazard), as a departure from the "
        "brief's naming rule, and lists it under What to decide.",
    ),
    Finding(
        "R6",
        ("C47",),
        "cosmetic",
        "kept",
        "No change: the expert action that enters number names accepts any id an account in the "
        "case holds, so a Telegram user id is a valid number name.",
    ),
    Finding(
        "R7",
        ("C03", "C09", "C12", "C24", "C35", "C37", "C39", "C41", "C43", "C44", "C45"),
        "cosmetic",
        "fixed",
        "Agreed: rationales, hazards and the alias notes now name decoys only by the contact "
        "name, number or id a report shows, or by words in their own texts.",
    ),
    Finding(
        "R8",
        ("C23", "C24"),
        "sheet",
        "fixed",
        "Agreed: the claims name no app, so their rows no longer set a channel. C23 keeps the "
        "SPARE LINE's account, C24 the two people.",
    ),
    Finding(
        "R9",
        ("C23",),
        "weak",
        "fixed",
        "Agreed: the exchange now reads 'ya both 150 outboards, locked up', and the key and the "
        "meaning row cite the Feb 24 'ya 4 outboards, two are 150s' for the horsepower.",
    ),
    Finding(
        "R10",
        ("C34",),
        "weak",
        "kept",
        "Kept: paragraph 5 itself puts the clock change in the TRANSFER ('the night the clocks "
        "went forward, at 2 a.m.'), signed case05 C34 has the same construction, and the sheet "
        "lists the window. A clock-time wording would have to end on 2 a.m., a minute that "
        "never existed that night, which is a worse trap than the one it removes.",
    ),
)

"""Case05 mock affidavit, DRAFT answer key and DRAFT assumption sheet. SYNTHETIC.

DRAFT ONLY. Every verdict and every assumption row below is the builder's proposal. Arsh reviews
and decides each one; nothing here is gold until a human copies it into eval/gold/. The
affidavit text is generated from this file so claim wording stays verbatim.

case05 is a held-out set for one measured step, built blind to case04's design so the two cases
are comparable. Its builder did not read the measured step's prompt, code, tests or demo claims.
The design was fixed claim by claim before any of the story was written, and is recorded here:

- 48 claims, 6 of each claim type in core/contracts.py. Draft verdicts: 24 supported, 12
  contradicted, 12 unproven, spread as each type allows (no absence claim can be supported on a
  curated report):
    communication 4/1/1, identity 3/2/1, timing 4/1/1, content_meaning 3/1/2, count 4/1/1,
    absence 0/3/3, role 2/2/2, event 4/1/1 (supported/contradicted/unproven).
  The second read (2026-10-31) moved C04 to unproven, so the draft stands at 23/12/13
  (communication 3/1/2); FIRST_DRAFT_VERDICT keeps the first draft.
- Wording: per type, 3 claims "plain" (names, dates and quotes stated outright, as case01's
  read) and 3 "affidavit" (defined terms and designations, aliases, relative or approximate
  times, indirect speech, references back, roles, numbers in words).
- Hazard: a wrong reading the data holds a candidate for (a second person with the same first
  name or nickname, a second number or account for the same person, a second phone that could
  be meant, a near-miss window, one contact name on two phones for two people, similar words in
  another thread). 46 of the 48 claims carry one: near_window 11, similar_quote 9,
  second_number 8, second_phone 7, same_name 6, contact_name 5; C02 and C39 carry none. The
  sheet names only the right person, phone, account and window.
- A sheet for every claim (draft_assumptions.jsonl). Two role claims (C39, C42) have only a
  role row, which no check tests; every other claim has a core row a check tests.
- Three phones set to America/Denver; the case runs from October 6 to November 30, 2025 and
  crosses the end of daylight saving (2 a.m. on November 2, 2025, the night of the LOCKER
  BURGLARY, when 1 to 2 a.m. came twice). Item 1 prints local time with each row's offset,
  Item 2 prints UTC+0, Item 3 prints every row at a fixed UTC-7.

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

DRAFT_LABEL = "DRAFT (case05 builder, not signed by Arsh)"
TEMPLATES_VERSION = "1.0.0"
TZ = "America/Denver"

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
    "came twice when the clocks went back, an adjacent day, or Item 3's fixed UTC-7 print",
    "contact_name": "one contact name saved on two phones for two people",
    "similar_quote": "similar words in another thread",
    "none": "no wrong reading planted",
}

READING_RULES = (
    "Times are the phones' own clock, America/Denver (paragraph 7), never a printed value. Item 1 "
    "prints each row's own offset. Item 2 prints UTC+0. Item 3 prints every row at UTC-7, so "
    "until 2 a.m. on November 2 (when the clocks went back) its printed times are an hour behind "
    "the phone.",
    "'At about' is 8 minutes either side; 'about five minutes' is 240 to 360 s, 'about two "
    "minutes' 90 to 150 s, 'about eight minutes' 420 to 540 s, 'roughly a minute and a half' 70 "
    "to 110 s.",
    "'The early hours' is midnight to 6 a.m.; 'evening' 5 p.m. to midnight; 'morning' 5 a.m. to "
    "noon; 'shortly before 6 a.m.' 5:30 to 6 a.m.; 'within an hour after' the SHOP BURGLARY "
    "(about 9:40 p.m.) is 9:40 to 10:40 p.m.; 'the hour before' it 8:40 to 9:40 p.m.; 'within "
    "half an hour after' the STOP (3:10 p.m.) is 3:10 to 3:40 p.m.",
    "The night of the LOCKER BURGLARY: 'the hour after the clocks went back' is the second pass "
    "of 1 to 2 a.m., in MST (08:00 to 09:00 UTC); 'between 11 p.m. and 3 a.m.' is five real hours "
    "(05:00 to 10:00 UTC), because 1 to 2 a.m. came twice.",
    "'After' an event starts the day after it and 'before' ends the day before: 'the three days "
    "after the day of' the SHOP BURGLARY are November 15 to 17, 'two days after' it November 16, "
    "'three days before the STOP' November 16, 'two days after the STOP' November 21, 'the seven "
    "days starting the day after the STOP' November 20 to 26, 'from the day after the STOP to "
    "the end of November' November 20 to 30. The "
    "LOCKER BURGLARY began on Saturday, November 1: 'two days before' it is Thursday, October "
    "30, 'the five days before' it Monday, October 27 to Friday, October 31, 'the Saturday "
    "morning before' it November 1, 'the Tuesday after' it November 4. Relative dates count from "
    "the sentence before them: 'the next evening' after November 3 is November 4, 'that "
    "morning' after November 2 is November 2.",
    "Defined terms are read as the affidavit defines them (paragraphs 2 and 3): TOBY = SUBJECT-1 "
    "= MERROW, whose phone is Item 1, the SAMSUNG; SUBJECT-2 = VARGA, whose phone is Item 2, the "
    "iPHONE; CAL = the COURIER = SUBJECT-3 = ODUM, whose phone is Item 3, the ONEPLUS; the BURNER "
    "is +17205550186, MERROW's second number; the FENCE used +17205550129.",
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
    "Item 1 is used by MERROW, Item 2 by VARGA and Item 3 by ODUM, so each phone's own accounts "
    "speak for its owner. The key treats this as given, as the affidavit does; it is not proven by "
    "the data. Paragraph 3 says the BURNER is MERROW's, and the number writes 'its toby. new "
    "number, use this one for work stuff' to ODUM and 'its toby, new number. save it' to VARGA "
    "(Item 2 saves it as 'T2', Item 3 as 'Toby work'). No record from his own phone shows it, "
    "and the key does not take a number's self-identification as a tie: the Telegram account "
    "shown as 'T.M.' also writes 'its toby', and the data holds a second Toby (Toby Rusk, "
    "+13035550139). So C04, the one claim that rests on the BURNER being his, is unproven. C09 "
    "is about accounts, not people."
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
        'On October 9, 2025, MERROW texted VARGA "back row at quillbarrow has no cameras".',
        ("MERROW's SMS account sent the message to VARGA on Oct 9, Denver time",),
        (("item1", "mv_cam"), ("item2", "mv_cam")),
        "Outgoing SMS on Item 1 at 7:25 p.m. MDT on Oct 9, incoming on Item 2.",
        "Item 2 prints its copy as 10/10/2025 1:25:10 AM(UTC+0); a window on that printed date "
        "misses it. The sheet names Oct 9, Denver time.",
        (("item2", "mv_cam"),),
    ),
    C(
        "C02",
        "communication",
        "plain",
        "supported",
        "none",
        'On October 21, 2025, VARGA sent ODUM a WhatsApp message reading "unit 41, code is 7719".',
        ("VARGA's WhatsApp account sent the message to ODUM on Oct 21",),
        (("item2", "vw_code"), ("item3", "vw_code")),
        "Outgoing on Item 2 at 2:05 p.m. MDT on Oct 21, incoming on Item 3. A clean claim.",
    ),
    C(
        "C03",
        "communication",
        "plain",
        "contradicted",
        "same_name",
        'On November 6, 2025, ODUM sent VARGA a WhatsApp message reading "the blue ones fit in '
        'my hatchback".',
        ("ODUM's WhatsApp account sent the message to VARGA on Nov 6",),
        (("item2", "ca_blue"), ("item2", "contact:Cal"), ("item2", "ca_blue2")),
        "The only copy is on Item 2, sent by WhatsApp 13035550161, the number Item 2 saves as "
        "'Cal'; that number's next message is 'both paddles, no problem'. ODUM's WhatsApp "
        "(17205550168, saved on Item 2 as 'Calvin O') did not send it. Observed data rules out "
        "the stated sender.",
        "CAL is ODUM's nickname (paragraph 2), but Item 2's 'Cal' is another person. A reading "
        "that takes Item 2's 'Cal' for ODUM passes the sender; the sheet names ODUM.",
        (("item2", "contact:Cal"),),
    ),
    C(
        "C04",
        "communication",
        "affidavit",
        "unproven",
        "second_number",
        "Two days before the LOCKER BURGLARY, SUBJECT-1 texted the COURIER from the BURNER: "
        '"gate code is 2291, use the side lane".',
        (
            "The BURNER sent the message to ODUM on Thursday, Oct 30",
            "MERROW is the BURNER's user (paragraph 3, and the number's own 'its toby. new "
            "number')",
        ),
        (("item3", "b_gate"), ("item3", "b_new3")),
        "Item 3 holds the message from +17205550186 at 6:50 p.m. MDT on Oct 30 (printed 5:50:40 "
        "PM(UTC-7)). That SUBJECT-1 used the BURNER rests on paragraph 3 and on the number's own "
        "'its toby. new number, use this one for work stuff' to ODUM (Item 3 saves it as 'Toby "
        "work'). That is self-identification, the tie the key does not accept for 'T.M.', and the "
        "data holds a second Toby (Toby Rusk, +13035550139). No record from MERROW's own phone "
        "ties him to the number, so the core authorship row stays open: unproven.",
        "MERROW's own number also texted the COURIER that afternoon ('did u fix the van light'). "
        "A reading that names MERROW's phone accounts as the sender fails the sender check; the "
        "sheet names the BURNER account.",
        (("item3", "mo_light"),),
        "defined terms (LOCKER BURGLARY, SUBJECT-1, COURIER, BURNER), a relative date",
    ),
    C(
        "C05",
        "communication",
        "affidavit",
        "supported",
        "second_phone",
        "In the early hours of November 2, 2025, SUBJECT-2 sent the ONEPLUS a Telegram message "
        'that read "park it behind the feed store till light".',
        (
            "VARGA's Telegram account sent the message",
            "Item 3 (the ONEPLUS) received it between midnight and 6 a.m. on Nov 2",
        ),
        (("item3", "vt_park"), ("item3", "vt_where")),
        "Incoming on Item 3 at 3:40 a.m. MST on Nov 2, after the clocks went back, from VARGA's "
        "Telegram account (6630402), in answer to ODUM's 'where do i put the van'.",
        "The ONEPLUS is Item 3 (paragraph 2). The sender's own phone, Item 2, holds ODUM's "
        "question but not the answer: a reading that looks for the message on SUBJECT-2's phone "
        "finds none. The sheet names Item 3.",
        (("item2", "vt_where"),),
        "defined terms (SUBJECT-2, ONEPLUS), a relative time ('the early hours')",
    ),
    C(
        "C06",
        "communication",
        "affidavit",
        "unproven",
        "similar_quote",
        'On the Tuesday after the LOCKER BURGLARY, TOBY told the COURIER in a text that "nobody '
        'rides them till december".',
        ("MERROW's SMS account sent the message to ODUM on Tuesday, Nov 4",),
        (("item1", "mo_work"), ("item1", "mo_work2")),
        "No message with these words is on any phone. The only MERROW-ODUM texts that day are "
        "'u at work?' and 'till 6'. The reports are curated, so not found does not mean not sent.",
        "That morning MERROW texted Item 1's 'Arlo' (+19705550125) 'nobody rides the quad till "
        "december, its in the shop'. A repair that quotes those words passes the sender; the "
        "sheet quotes the claim's words.",
        (("item1", "ar_quad"),),
        "alias (TOBY), a role (the COURIER), a relative date ('the Tuesday after'), indirect "
        "speech",
    ),
    # ------------------------------------------------------------ identity
    C(
        "C07",
        "identity",
        "plain",
        "supported",
        "contact_name",
        'Item 3 contains a contact saved as "Toby" with the number +1 (720) 555-0134.',
        ("Item 3's contact list has an entry named 'Toby' with +17205550134",),
        (("item3", "contact:Toby"),),
        "Observed in Item 3's contacts; +17205550134 is Item 1's own number.",
        "Item 2 also has a 'Toby', with +13035550139. The sheet names Item 3.",
        (("item2", "contact:Toby"),),
    ),
    C(
        "C08",
        "identity",
        "plain",
        "unproven",
        "second_number",
        'Item 1 contains a contact saved as "Cal" with the number +1 (720) 555-0168.',
        ("Item 1's contact list has an entry named 'Cal' with +17205550168",),
        (("item1", "contact:Cal"), ("item1", "contact:Cal 2"), ("item1", "wk_cell2")),
        "Item 1's 'Cal' holds +17205550153 and +17205550168 is saved as 'Cal 2'. The 0153 "
        "number answers MERROW 'ya the warehouse one. my own is the other number'. No entry "
        "'Cal' with 0168 is in the report; contact lists can be edited and the report is "
        "curated, so this is not shown, not ruled out.",
        "A reading that takes 'Cal' with the number it holds (0153, a second number of the same "
        "person) passes; the sheet names 0168, as the claim does.",
        (("item1", "contact:Cal"),),
    ),
    C(
        "C09",
        "identity",
        "plain",
        "contradicted",
        "second_number",
        'On Item 3, the Telegram names "Toby M" and "T.M." belong to one account.',
        ("On Telegram, 'Toby M' and 'T.M.' resolve to one account id",),
        (("item3", "mt_first"), ("item3", "tm_new")),
        "'Toby M' is Telegram user id 6630401, Item 1's own account; 'T.M.' is user id 6630488, "
        "which first writes to ODUM on Nov 20. Two user ids are two accounts. Observed data "
        "rules out one account.",
        "6630488 writes 'new acct. its toby. the old one is done': one person may use two "
        "accounts, and a reading that merges them by the person passes. The sheet names the two "
        "names as the claim does.",
        (("item3", "tm_new"),),
    ),
    C(
        "C10",
        "identity",
        "affidavit",
        "supported",
        "second_number",
        "From November 10, 2025, the ONEPLUS shows SUBJECT-2's Telegram account under a new "
        'name, "vee.rides"; before that it appeared as "Ines V".',
        (
            "On Telegram, 'Ines V' and 'vee.rides' resolve to one account id (6630402)",
            "Telegram user id 6630402 is VARGA's (Item 2's own account)",
        ),
        (("item3", "vt_08"), ("item3", "vt_10"), ("item2", "vt_08"), ("item2", "vt_10")),
        "Every row of the conversation on Item 3 carries Telegram user id 6630402, Item 2's own "
        "account, whose outgoing copies are on Item 2. Item 3's rows show the name 'Ines V' last "
        "at 7:30 p.m. on Nov 8 and 'vee.rides' from 4:45 p.m. on Nov 10; no row falls between.",
        "Item 1 saves VARGA's phone number (+13035550157) as 'Ines V' too, so her SMS and Signal "
        "accounts carry that name there. A reading that does not keep to Telegram finds two "
        "accounts under 'Ines V'; the sheet names Telegram.",
        (("item1", "contact:Ines V"),),
        "defined terms (ONEPLUS, SUBJECT-2), a reference back ('before that')",
    ),
    C(
        "C11",
        "identity",
        "affidavit",
        "supported",
        "contact_name",
        'SUBJECT-2 saved the BURNER in the iPHONE as "T2".',
        ("Item 2's contact list has an entry named 'T2' with +17205550186",),
        (("item2", "contact:T2"), ("item2", "b_new2b")),
        "Observed in Item 2's contacts; VARGA answered the number's 'its toby, new number. save "
        "it' with 'saved as T2'.",
        "Item 3 also has a 'T2', with +17205550143 (another person). The iPHONE is Item 2; the "
        "sheet names Item 2. Item 2 saves MERROW's main number as 'Tobias'.",
        (("item3", "contact:T2"),),
        "defined terms (SUBJECT-2, BURNER, iPHONE)",
    ),
    C(
        "C12",
        "identity",
        "affidavit",
        "contradicted",
        "contact_name",
        'The text message "left the key under the blue pot" that SUBJECT-2 received from "Toby" '
        "on November 11, 2025 was sent by TOBY.",
        ("MERROW's SMS account sent 'left the key under the blue pot'",),
        (("item2", "ru_key"), ("item2", "contact:Toby")),
        "The only copy is on Item 2, from +13035550139, which Item 2 saves as 'Toby'; the "
        "message goes on 'plumber comes at 2'. MERROW's number is +17205550134 (saved on Item 2 "
        "as 'Tobias'). Observed data rules out the stated sender.",
        "TOBY is MERROW (paragraph 2), and Item 3 saves MERROW's number as 'Toby'; on Item 2 "
        "'Toby' is someone else. A reading that takes Item 2's 'Toby' for TOBY passes; the sheet "
        "names MERROW.",
        (("item3", "contact:Toby"),),
        "alias (TOBY), a defined term (SUBJECT-2), a saved name in the claim ('from \"Toby\"')",
    ),
    # ------------------------------------------------------------ timing
    C(
        "C13",
        "timing",
        "plain",
        "supported",
        "near_window",
        "At about 9:30 p.m. on October 17, 2025, MERROW called ODUM; the call lasted about five "
        "minutes.",
        ("A call of about five minutes between MERROW and ODUM at about 9:30 p.m. MDT, Oct 17",),
        (("item1", "cl_1017a"), ("item3", "cl_1017a")),
        "Outgoing on Item 1 at 9:31:05 PM(UTC-6), 288 s; incoming on Item 3.",
        "Item 3 prints that call as 8:31:05 PM(UTC-7), and a later 41 s call at 10:30 p.m. MDT "
        "as 9:30:20 PM(UTC-7). A reading of Item 3's print takes the 41 s call for the 9:30 one "
        "and finds no five-minute call.",
        (("item3", "cl_1017a"), ("item3", "cl_1017b")),
    ),
    C(
        "C14",
        "timing",
        "plain",
        "supported",
        "near_window",
        "At about 11:50 p.m. on November 14, 2025, VARGA called ODUM; the call lasted about two "
        "minutes.",
        ("A call of about two minutes between VARGA and ODUM at about 11:50 p.m. MST, Nov 14",),
        (("item2", "cl_1114b"), ("item3", "cl_1114b")),
        "Outgoing on Item 2 at 11:52:10 p.m. MST, 128 s (Item 2 prints 11/15/2025 6:52:10 "
        "AM(UTC+0); Item 3 prints 11/14/2025 11:52:10 PM(UTC-7)).",
        "Item 2 prints an earlier VARGA-ODUM call, at 4:50 p.m. MST and 305 s, as 11/14/2025 "
        "11:50:30 PM(UTC+0). A window read off Item 2's print finds that call, which does not "
        "last about two minutes.",
        (("item2", "cl_1114a"), ("item2", "cl_1114b")),
    ),
    C(
        "C15",
        "timing",
        "plain",
        "contradicted",
        "near_window",
        'At 6:45 p.m. on October 24, 2025, MERROW texted ODUM "need u next saturday, bring the '
        'trailer".',
        ("The message was sent at 6:45 p.m. on Oct 24, Denver time",),
        (("item1", "mo_trailer"), ("item3", "mo_trailer")),
        "Sent at 7:45:30 p.m. MDT on Oct 24. Item 3 prints 10/24/2025 6:45:30 PM(UTC-7), which "
        "is where the claim's time comes from; every copy is outside the stated minute.",
        "Item 3's fixed UTC-7 print is an hour behind the phone before the clocks went back; the "
        "sheet names 6:45 p.m. Denver time.",
        (("item3", "mo_trailer"),),
    ),
    C(
        "C16",
        "timing",
        "affidavit",
        "supported",
        "second_number",
        "Within an hour after the SHOP BURGLARY, the BURNER called the COURIER; they spoke for "
        "roughly a minute and a half.",
        ("A call of 70 to 110 s between the BURNER and ODUM from 9:40 to 10:40 p.m., Nov 14",),
        (("item3", "cl_bur1114"),),
        "Incoming on Item 3 from +17205550186 at 10:07:15 p.m. MST, 92 s.",
        "At 10:31 p.m. MERROW's own number called the COURIER for 22 s. A repair that names "
        "MERROW's phone accounts instead of the BURNER finds only that call, which is too short; "
        "the sheet names the BURNER.",
        (("item3", "cl_mer1114"),),
        "defined terms (SHOP BURGLARY, BURNER, COURIER), a relative window, a duration in words",
    ),
    C(
        "C17",
        "timing",
        "affidavit",
        "supported",
        "near_window",
        "In the hour after the clocks went back that night, SUBJECT-1 told SUBJECT-2 on Signal "
        'that the "last two are in the van".',
        (
            "MERROW's Signal account sent the message to VARGA from 1 to 2 a.m. MST, Nov 2 (the "
            "second 1 a.m. hour)",
        ),
        (("item1", "sn09"), ("item2", "sn09")),
        "Outgoing on Item 1 at 1:34:50 AM(UTC-7) on Nov 2, the second pass of 1 a.m.; Item 2 "
        "prints 8:34:50 AM(UTC+0).",
        "A window on the first 1 a.m. hour (MDT, 07:00 to 08:00 UTC) misses the message and "
        "fails the time; in that hour MERROW wrote 'first 6 are in the van'. The sheet names 1 "
        "to 2 a.m. MST.",
        (("item1", "sn06"), ("item1", "sn09")),
        "defined terms (SUBJECT-1, SUBJECT-2), a time given by an event, 'that night' referring "
        "back, indirect speech",
    ),
    C(
        "C18",
        "timing",
        "affidavit",
        "unproven",
        "contact_name",
        "Within half an hour after the STOP, SUBJECT-3 spoke by phone with the FENCE.",
        ("A call between ODUM and +17205550129 from 3:10 to 3:40 p.m., Nov 19",),
        (("item3", "cl_jory"), ("item3", "contact:Jory"), ("item2", "contact:Jory")),
        "No call or message between ODUM and the FENCE's number is on any phone. The only call in "
        "the window is to +17205550181, which Item 3 saves as 'Jory'; Item 2 saves the FENCE's "
        "number as 'Jory'. The reports are curated, so not shown, not ruled out.",
        "A reading that takes Item 3's 'Jory' (+17205550181) for the FENCE passes on that call; "
        "the sheet names the FENCE's number.",
        (("item3", "cl_jory"),),
        "defined terms (STOP, SUBJECT-3, FENCE), a relative window, a number in words",
        cross_device=True,
    ),
    # ------------------------------------------------------------ content meaning
    C(
        "C19",
        "content_meaning",
        "plain",
        "supported",
        "similar_quote",
        'On October 14, 2025, MERROW texted VARGA "found 6 tall ones in the back row"; in that '
        'exchange, "tall ones" meant electric mountain bikes.',
        (
            "MERROW's SMS account sent the message to VARGA on Oct 14",
            "In that exchange 'tall ones' means electric mountain bikes",
        ),
        (("item1", "mv_tall"), ("item1", "mv_tall2"), ("item1", "mv_tall3")),
        "The exchange fixes the meaning: VARGA asks 'the emtbs?' and MERROW answers 'ya electric "
        "mountain bikes, all 6'.",
        "That evening VARGA wrote to Item 2's 'Mama' 'found 6 tall ones at the thrift for ur "
        "patio' about something else. The sheet quotes the claimed message and names MERROW and "
        "VARGA.",
        (("item2", "ma_tall"),),
    ),
    C(
        "C20",
        "content_meaning",
        "plain",
        "unproven",
        "similar_quote",
        'On November 3, 2025, MERROW texted VARGA "the cold ones are in the garage", meaning '
        "e-bikes with their batteries removed.",
        (
            "MERROW's SMS account sent the message to VARGA on Nov 3",
            "'the cold ones' are e-bikes with their batteries removed",
        ),
        (("item1", "mv_cold"), ("item1", "mv_cold2")),
        "The message is observed (8:30 p.m. MST on Nov 3; Item 2 prints 11/4/2025 3:30:25 "
        "AM(UTC+0)). VARGA answers only 'ok'; nothing in the exchange says what the cold ones "
        "are. The meaning is not fixed.",
        "The day before, MERROW wrote the same words to Item 1's 'Arlo', 'the cold ones are in "
        "the garage fridge, help urself', about drinks. The sheet names MERROW and VARGA and "
        "leaves the meaning to the expert.",
        (("item1", "ar_cold"),),
    ),
    C(
        "C21",
        "content_meaning",
        "plain",
        "contradicted",
        "similar_quote",
        'On November 12, 2025, ODUM texted VARGA "the shop on larch closes at 9 on fridays", '
        "telling her when the BIKE SHOP would be empty.",
        (
            "ODUM's SMS account sent the message to VARGA on Nov 12",
            "The words tell when the BIKE SHOP would be empty",
        ),
        (("item2", "vo_larch"), ("item3", "vo_larch")),
        "VARGA sent it to ODUM (outgoing on Item 2, incoming on Item 3); ODUM only answered 'ok "
        "noted'. Observed data rules out the stated sender; the meaning is not reached.",
        "The next day ODUM texted Item 3's 'Pell' 'the gym on larch closes at 9 on fridays now'. "
        "A repair that quotes the shared words ('closes at 9 on fridays') finds senders on both "
        "sides; the sheet quotes the claim's words and names ODUM, as the claim does.",
        (("item3", "pe_gym"),),
    ),
    C(
        "C22",
        "content_meaning",
        "affidavit",
        "supported",
        "similar_quote",
        'The next evening, TOBY asked the COURIER on Telegram to "grab the pizzas from the '
        'container", by which he meant the battery packs.',
        (
            "MERROW's Telegram account sent 'grab the pizzas from the container' to ODUM on the "
            "evening of Nov 4",
            "'the pizzas' means the battery packs",
        ),
        (
            ("item3", "mt_pizza"),
            ("item3", "mt_bat"),
            ("item3", "mt_bat2"),
            ("item3", "mt_pizza2"),
            ("item3", "mt_pizza3"),
        ),
        "On Nov 3 the COURIER asked 'do the batteries come off those' and TOBY answered 'ya pop em "
        "off. on here we call them pizzas'; on Nov 4 at 6:40 p.m. MST he wrote 'grab the pizzas "
        "from the container' and, asked 'all 11?', 'all 11 batteries ya'. The thread fixes the "
        "meaning.",
        "An hour earlier Item 3's 'Dorrie' wrote 'grab the pizzas from the freezer for the kids'. "
        "A repair that quotes 'grab the pizzas' finds two senders; the sheet quotes TOBY's "
        "message.",
        (("item3", "do_pizza"),),
        "alias (TOBY), a role (the COURIER), 'the next evening' referring back to C20's Nov 3, "
        "paraphrase",
    ),
    C(
        "C23",
        "content_meaning",
        "affidavit",
        "supported",
        "second_number",
        'Three days before the STOP, the BURNER told SUBJECT-2 that "the 4 skinnies are at the '
        'dock", which in that exchange meant the four carbon road bikes from the BIKE SHOP.',
        (
            "The BURNER sent 'the 4 skinnies are at the dock' to VARGA on Nov 16",
            "'the 4 skinnies' means the four carbon road bikes from the BIKE SHOP",
        ),
        (("item2", "b_skin"), ("item2", "b_skin2"), ("item2", "b_skin3")),
        "VARGA asked 'the pindlewick road bikes?' and the BURNER answered 'ya the carbon ones from "
        "friday, all 4'. The BIKE SHOP is Pindlewick Cycles, entered on Friday, Nov 14 (paragraph "
        "5). The exchange fixes the meaning.",
        "MERROW's own number also texted VARGA that morning ('call me later'). A repair that "
        "names MERROW's phone accounts as the sender fails the sender check; the sheet names the "
        "BURNER account, as the claim does.",
        (("item2", "mv_later"),),
        "defined terms (STOP, BURNER, SUBJECT-2, BIKE SHOP), a relative date, a number in words",
    ),
    C(
        "C24",
        "content_meaning",
        "affidavit",
        "unproven",
        "same_name",
        'Two days after the STOP, SUBJECT-2 warned SUBJECT-1 that "cal is getting nervous", '
        "referring to the COURIER.",
        (
            "VARGA's SMS account sent the message to MERROW on Nov 21",
            "'cal' is ODUM",
        ),
        (("item2", "vm_nerv"), ("item2", "contact:Cal"), ("item2", "contact:Calvin O")),
        "The message is observed (8:20 p.m. MST on Nov 21). Which Cal is not fixed: VARGA's phone "
        "holds two (ODUM, saved as 'Calvin O', and Item 2's 'Cal', +13035550161), and that "
        "morning Item 2's 'Cal' wrote her 'im getting nervous about saturday, first comp in "
        "years'. MERROW answers only 'ok'.",
        "CAL is ODUM's nickname (paragraph 2). A reading that takes 'cal' for ODUM without asking "
        "passes the meaning; the sheet leaves the meaning to the expert.",
        (("item2", "ca_nerv"),),
        "defined terms (STOP, SUBJECT-2, SUBJECT-1), a role (the COURIER), a relative date, "
        "indirect speech",
    ),
    # ------------------------------------------------------------ count
    C(
        "C25",
        "count",
        "plain",
        "supported",
        "near_window",
        "Between October 13 and October 19, 2025, Item 2 recorded 7 Signal messages exchanged "
        "between MERROW and VARGA.",
        ("Item 2 holds exactly 7 Signal messages between them Oct 13 to 19, Denver time",),
        tuple(("item2", f"sg0{i}") for i in range(1, 8)),
        "Seven rows on Item 2 on Denver dates Oct 13 to 19.",
        "Item 2 prints UTC+0: three messages on the evening of Oct 12 print as Oct 13, and the "
        "two on the evening of Oct 19 print as Oct 20. A count on printed dates gives 8.",
        (("item2", "sg00a"), ("item2", "sg00b"), ("item2", "sg00c")),
    ),
    C(
        "C26",
        "count",
        "plain",
        "supported",
        "second_phone",
        "From November 3 through November 9, 2025, Item 3 recorded 5 Telegram messages exchanged "
        "between ODUM and VARGA.",
        ("Item 3 holds exactly 5 Telegram messages between them Nov 3 to 9",),
        tuple(("item3", k) for k in ("vt_03a", "vt_03b", "vt_06a", "vt_06b", "vt_08")),
        "Five rows on Item 3.",
        "Item 2 holds one more in the window (Nov 7, '?'), which Item 3's report does not: a "
        "count on Item 2 gives 6. The sheet names Item 3.",
        (("item2", "vt_07"),),
    ),
    C(
        "C27",
        "count",
        "plain",
        "contradicted",
        "near_window",
        "On November 14, 2025, Item 2 recorded 4 text messages exchanged between MERROW and VARGA.",
        ("Item 2 holds exactly 4 SMS messages between them on Nov 14, Denver time",),
        tuple(("item2", f"mv_14{c}") for c in "abcdef"),
        "Item 2 holds six on Nov 14 local time, so exactly four is ruled out.",
        "Two of the six were sent after 5 p.m. MST and fall on Nov 15 in UTC, which is how Item 2 "
        "prints them; a UTC day counts four and passes. The sheet names the Denver day.",
        (("item2", "mv_14e"), ("item2", "mv_14f")),
    ),
    C(
        "C28",
        "count",
        "affidavit",
        "supported",
        "second_number",
        "In the five days before the LOCKER BURGLARY, the COURIER sent the BURNER five text "
        "messages, all recorded on the ONEPLUS.",
        ("Item 3 holds exactly 5 SMS messages ODUM sent to the BURNER, Oct 27 to Oct 31",),
        tuple(("item3", k) for k in ("b27b", "b28a", "b29a", "b_gate2", "b31a")),
        "Five rows on Item 3 from ODUM to +17205550186, Monday Oct 27 through Friday Oct 31.",
        "ODUM also texted MERROW's own number three times that week; a repair that names "
        "MERROW's phone accounts counts those. His next text to the BURNER is on Saturday Nov 1, "
        "outside the five days. The sheet names the BURNER, ODUM as the sender, and Item 3.",
        (("item3", "mo_meet2"), ("item3", "om_game"), ("item3", "mo_light2"), ("item3", "ob_here")),
        "defined terms (LOCKER BURGLARY, COURIER, BURNER, ONEPLUS), a relative range, a number "
        "in words",
    ),
    C(
        "C29",
        "count",
        "affidavit",
        "unproven",
        "second_phone",
        "Between November 10 and November 13, 2025, the SAMSUNG recorded at least five Telegram "
        "messages between SUBJECT-1 and SUBJECT-3.",
        ("Item 1 holds at least 5 Telegram messages between MERROW and ODUM, Nov 10 to 13",),
        tuple(("item1", k) for k in ("mt_10a", "mt_10b", "mt_12")),
        "Item 1 holds three in the window. Fewer than claimed is not a contradiction (curated "
        "report), so unproven.",
        "Item 3 holds five, two of which (Nov 11 and Nov 13) Item 1's report does not: a count "
        "on the ONEPLUS passes. The SAMSUNG is Item 1; the sheet names Item 1.",
        (("item3", "mt_11"), ("item3", "mt_13")),
        "defined terms (SAMSUNG, SUBJECT-1, SUBJECT-3), a number in words",
    ),
    C(
        "C30",
        "count",
        "affidavit",
        "supported",
        "near_window",
        "On the night of the LOCKER BURGLARY, between 11 p.m. and 3 a.m., SUBJECT-1 and SUBJECT-2 "
        "exchanged at least a dozen Signal messages, as recorded on the iPHONE.",
        ("Item 2 holds at least 12 Signal messages between them, 11 p.m. Nov 1 to 3 a.m. Nov 2",),
        tuple(("item2", f"sn{i:02d}") for i in range(1, 13)),
        "11 p.m. to 3 a.m. that night is five hours, because 1 to 2 a.m. came twice. Item 2 holds "
        "twelve Signal messages in it.",
        "A window that forgets the repeated hour (05:00 to 09:00 UTC, or 06:00 to 10:00 UTC) "
        "holds ten or nine, which is fewer than claimed. The sheet names wall-clock 11 p.m. MDT "
        "to 3 a.m. MST.",
        (("item2", "sn11"), ("item2", "sn12"), ("item2", "sn13")),
        "defined terms (LOCKER BURGLARY, SUBJECT-1, SUBJECT-2, iPHONE), a number in words",
    ),
    # ------------------------------------------------------------ absence
    C(
        "C31",
        "absence",
        "plain",
        "contradicted",
        "near_window",
        "MERROW and ODUM had no contact of any kind on October 23, 2025.",
        ("No message or call between them on Oct 23, Denver time",),
        (("item1", "mo_keys"), ("item3", "mo_keys"), ("item3", "mo_keys2")),
        "MERROW texted ODUM 'u up? need the van keys' at 12:30 a.m. MDT on Oct 23 and ODUM "
        "answered at 12:40 a.m.",
        "Item 3 prints both as Oct 22 (11:30:15 PM and 11:40:02 PM, UTC-7), and nothing else "
        "between them falls on Oct 23 in Item 3's print: a day read off Item 3 finds no contact. "
        "The sheet names the Denver day.",
        (("item3", "mo_keys"), ("item3", "mo_keys2")),
    ),
    C(
        "C32",
        "absence",
        "plain",
        "contradicted",
        "second_number",
        "VARGA and MERROW had no contact of any kind between November 22 and November 24, 2025.",
        ("No message or call between VARGA and MERROW, on any app, Nov 22 to 24",),
        (("item1", "sg_only"), ("item2", "sg_only"), ("item2", "sg_only2")),
        "On Nov 23 MERROW wrote to VARGA on Signal 'dont text the old way. only here from now', "
        "and she answered 'ok'. Both phones hold the exchange.",
        "Their phone numbers have no texts or calls those days. A reading limited to the numbers "
        "(SMS and calls) misses his Signal account and finds none; the sheet names both people "
        "and no channel.",
        (("item2", "sg_only"),),
    ),
    C(
        "C33",
        "absence",
        "plain",
        "unproven",
        "contact_name",
        "ODUM had no contact of any kind with the number +1 (720) 555-0129 between November 1 and "
        "November 30, 2025.",
        ("No message or call between ODUM and +17205550129 in November",),
        (("item2", "contact:Jory"), ("item3", "contact:Jory")),
        "No record between ODUM and +17205550129 is on any phone; the reports are curated, so the "
        "absence cannot be shown.",
        "ODUM has calls and texts all month with Item 3's 'Jory', +17205550181; Item 2 saves "
        "+17205550129 as 'Jory'. Taking one Jory for the other contradicts the claim wrongly. The "
        "sheet names +17205550129.",
        (("item3", "cl_jory"),),
        cross_device=True,
    ),
    C(
        "C34",
        "absence",
        "affidavit",
        "unproven",
        "near_window",
        "Once the clocks had gone back that night, the COURIER and SUBJECT-2 had no contact for "
        "the next hour.",
        ("No message or call between ODUM and VARGA from 1 to 2 a.m. MST, Nov 2",),
        (("item2", "ow_full"), ("item3", "vt_where")),
        "Nothing between them from 1 to 2 a.m. MST (08:00 to 09:00 UTC); the nearest records are "
        "a WhatsApp at 1:25 a.m. MDT, in the first pass of the hour, and a Telegram at 3:20 a.m. "
        "MST. Curated reports cannot show an absence, so unproven.",
        "A window on the first 1 a.m. hour (MDT, 07:00 to 08:00 UTC) finds 'the van is full, cant "
        "fit the boots' and contradicts the claim wrongly. The sheet names 1 to 2 a.m. MST.",
        (("item2", "ow_full"), ("item3", "ow_full")),
        "a role (the COURIER), a defined term (SUBJECT-2), a time given by an event, 'that "
        "night' referring back",
    ),
    C(
        "C35",
        "absence",
        "affidavit",
        "contradicted",
        "same_name",
        "On the three days after the day of the SHOP BURGLARY, SUBJECT-2 had no contact with CAL.",
        ("No message or call between VARGA and ODUM, Nov 15 to 17",),
        (("item2", "vw_15a"), ("item2", "vw_15b"), ("item2", "vw_16")),
        "VARGA and ODUM exchanged WhatsApp messages on Nov 15 and Nov 16.",
        "CAL is ODUM (paragraph 2). Item 2's 'Cal' is +13035550161, which has no contact with "
        "her those days: that reading finds none. The sheet names ODUM.",
        (("item2", "contact:Cal"),),
        "alias (CAL), defined terms (SUBJECT-2, SHOP BURGLARY), a relative range, a number in "
        "words",
    ),
    C(
        "C36",
        "absence",
        "affidavit",
        "unproven",
        "second_phone",
        "From the day after the STOP to the end of November, SUBJECT-1 and the COURIER had no "
        "contact, per the SAMSUNG.",
        ("Item 1 holds no message or call between MERROW and ODUM, Nov 20 to 30",),
        (("item3", "mo_good"),),
        "Item 1's report holds none, but a curated report cannot show that the phone held none, so "
        "unproven. Item 3 holds a text from MERROW to ODUM on Nov 22 that Item 1's report does "
        "not.",
        "The claim rests on the SAMSUNG (Item 1). A repair with no phone named finds the Item 3 "
        "copy and contradicts it; the sheet names Item 1.",
        (("item3", "mo_good"),),
        "defined terms (STOP, SAMSUNG, SUBJECT-1), a role (the COURIER), a relative range",
    ),
    # ------------------------------------------------------------ role
    C(
        "C37",
        "role",
        "plain",
        "supported",
        "similar_quote",
        "On November 5, 2025, VARGA set the asking price for the red e-bikes, telling ODUM by "
        'WhatsApp "1400 each, dont go under 1200".',
        (
            "VARGA's WhatsApp account sent '1400 each, dont go under 1200' to ODUM on Nov 5",
            "VARGA set the asking price",
        ),
        (("item2", "vw_price0"), ("item2", "vw_price"), ("item2", "vw_price2")),
        "ODUM asked 'what do i ask for the red ebikes on marketplace?', VARGA answered '1400 "
        "each, dont go under 1200' and ODUM took it ('ok 1400'). The exchange fixes that she set "
        "the asking price; it says nothing about a sale.",
        "That evening Item 2's 'Cal' wrote '1400 each for the kayaks? no way lol'. A repair that "
        "quotes '1400 each' finds two senders; the sheet quotes VARGA's message.",
        (("item2", "ca_kayak"),),
    ),
    C(
        "C38",
        "role",
        "plain",
        "contradicted",
        "similar_quote",
        'On November 13, 2025, ODUM set the time, texting MERROW "friday 9:30, back door".',
        (
            "ODUM's SMS account sent 'friday 9:30, back door' to MERROW on Nov 13",
            "ODUM set the time",
        ),
        (("item1", "mo_fri"), ("item3", "mo_fri"), ("item3", "mo_fri2")),
        "MERROW sent it to ODUM, who answered '9:30 back door works'. Observed data rules out the "
        "stated sender.",
        "ODUM's answer holds similar words. A repair that quotes '9:30 back door' matches only "
        "his answer and passes the sender; the sheet quotes the claim's words.",
        (("item3", "mo_fri2"),),
    ),
    C(
        "C39",
        "role",
        "plain",
        "unproven",
        "none",
        "MERROW recruited VARGA to sell the stolen bikes.",
        ("MERROW recruited VARGA",),
        (("item1", "mv_page"), ("item1", "mv_page2")),
        "The record shows VARGA offering ('if u ever have bikes to move i can list them on my "
        "page') and MERROW answering 'good to know'. Who recruited whom is interpretation.",
    ),
    C(
        "C40",
        "role",
        "affidavit",
        "supported",
        "second_phone",
        'SUBJECT-2 gave the COURIER the marketplace listings to run, telling him on WhatsApp "u '
        'handle marketplace, i do insta".',
        (
            "VARGA's WhatsApp account sent 'u handle marketplace, i do insta' to ODUM",
            "VARGA assigned ODUM the marketplace listings",
        ),
        (("item3", "vw_mkt"), ("item3", "vw_mkt2")),
        "On Nov 3 VARGA wrote 'u handle marketplace, i do insta' and ODUM answered 'ok i got "
        "marketplace'. The exchange fixes the assignment and his acceptance; the claim says no "
        "more than that.",
        "Only Item 3 holds the exchange; Item 2's report does not. A repair that limits the "
        "search to SUBJECT-2's phone finds no copy; the sheet names no phone.",
        (("item3", "vw_mkt"),),
        "a defined term (SUBJECT-2), a role (the COURIER), indirect speech",
    ),
    C(
        "C41",
        "role",
        "affidavit",
        "contradicted",
        "near_window",
        "On the Saturday morning before the LOCKER BURGLARY, SUBJECT-2 told the COURIER which "
        'lockers to open: "start with 12 and 14, then the cage".',
        (
            "VARGA's WhatsApp account sent the message to ODUM on the morning of Saturday, Nov 1",
            "VARGA chose the lockers",
        ),
        (("item2", "vw_lock"), ("item3", "vw_lock")),
        "Sent at 11:20:30 p.m. MDT on Friday, Oct 31 (Item 3 prints 10:20:30 PM(UTC-7)). Every "
        "copy is outside Saturday morning, so the stated time is ruled out.",
        "Item 2 prints it as 11/1/2025 5:20:30 AM(UTC+0), Saturday morning on its face; a window "
        "read off Item 2's print passes. The sheet names Saturday 5 a.m. to noon, Denver time.",
        (("item2", "vw_lock"),),
        "defined terms (LOCKER BURGLARY, SUBJECT-2), a role (the COURIER), a relative date",
    ),
    C(
        "C42",
        "role",
        "affidavit",
        "unproven",
        "same_name",
        "In the hour before the SHOP BURGLARY, SUBJECT-2 kept watch on the BIKE SHOP, letting CAL "
        "know by text that the staff had gone.",
        ("VARGA kept watch on the BIKE SHOP and reported to ODUM",),
        (("item2", "vc_staff"), ("item2", "contact:Cal")),
        "The only such text is VARGA's 'staff all gone, come up whenever' at 8:55 p.m. MST, to "
        "Item 2's 'Cal' (+13035550161), not to ODUM. It does not show anyone keeping watch.",
        "CAL is ODUM (paragraph 2); Item 2's 'Cal' is someone else. A reading that takes Item 2's "
        "'Cal' for CAL finds a report to the COURIER; the sheet has only the role row, which no "
        "check tests.",
        (("item2", "vc_staff"),),
        "defined terms (SHOP BURGLARY, SUBJECT-2, BIKE SHOP), alias (CAL), a relative window, "
        "paraphrase",
    ),
    # ------------------------------------------------------------ event
    C(
        "C43",
        "event",
        "plain",
        "supported",
        "similar_quote",
        "On October 28, 2025, MERROW and ODUM arranged by text to meet at 7 p.m. on Thursday, "
        "October 30, 2025, at the lot by the grain elevator.",
        (
            "MERROW proposed the meeting by SMS on Oct 28",
            "'thursday' sent on Tuesday Oct 28 is Oct 30",
            "ODUM agreed",
        ),
        (("item1", "mo_meet"), ("item1", "mo_meet2"), ("item3", "mo_meet")),
        "'grain elevator lot thursday 7pm' from MERROW, 'bet' from ODUM.",
        "The next day ODUM texted Item 3's 'Jory' 'drop the van at the grain elevator lot after "
        "5'; the sheet quotes MERROW's message.",
        (("item3", "jo_lot"),),
    ),
    C(
        "C44",
        "event",
        "plain",
        "supported",
        "same_name",
        "On November 18, 2025, VARGA asked MERROW by text to move the road bikes out of unit 41, "
        "and MERROW agreed.",
        ("VARGA asked by SMS on Nov 18", "MERROW answered that he would"),
        (("item2", "vm_move"), ("item2", "vm_move2")),
        "'need the road bikes out of unit 41 by thurs' from VARGA, 'ok ill move them tonight' "
        "from MERROW.",
        "That morning VARGA asked Item 2's 'Toby' (+13035550139, a second Toby) 'need the bikes "
        "out of the stairwell by thurs, inspection'. The sheet names MERROW.",
        (("item2", "ru_stair"),),
    ),
    C(
        "C45",
        "event",
        "plain",
        "unproven",
        "same_name",
        "On November 4, 2025, VARGA and ODUM spoke by phone for about eight minutes.",
        ("A call of about eight minutes between VARGA and ODUM on Nov 4",),
        (("item2", "cl_vo04"), ("item2", "cl_vc04"), ("item2", "contact:Cal")),
        "Their only call that day lasted 50 s. The eight-minute call (482 s) is with Item 2's "
        "'Cal' (+13035550161). No such call between them is in the reports; not shown.",
        "Taking Item 2's 'Cal' for CAL (ODUM) passes on that call; the sheet names ODUM.",
        (("item2", "cl_vc04"),),
    ),
    C(
        "C46",
        "event",
        "affidavit",
        "supported",
        "second_phone",
        "Shortly before 6 a.m. that morning, the COURIER let SUBJECT-2 know on WhatsApp that the "
        'van was "back at the yard".',
        (
            "ODUM's WhatsApp sent 'moved it. van is back at the yard' to VARGA, 5:30 to 6 a.m., "
            "Nov 2",
        ),
        (("item3", "ow_yard"),),
        "Outgoing on Item 3 at 5:48:20 AM(UTC-7) on Nov 2, which after the clocks went back is "
        "the phone's own time.",
        "Only Item 3 holds the message; Item 2's report does not. A repair that looks for it on "
        "SUBJECT-2's phone, the one it was sent to, finds none; the sheet names no phone.",
        (("item3", "ow_yard"),),
        "a role (the COURIER), defined term (SUBJECT-2), 'that morning' referring back to C05's "
        "Nov 2, an approximate time, indirect speech",
    ),
    C(
        "C47",
        "event",
        "affidavit",
        "supported",
        "similar_quote",
        "Two days after the SHOP BURGLARY, SUBJECT-1 paid the COURIER, writing to him on Telegram "
        '"sent u 400 for friday, check ur bank".',
        (
            "MERROW's Telegram sent the message to ODUM on Nov 16",
            "The money was sent and he got it",
        ),
        (("item3", "mt_pay"), ("item3", "mt_pay2"), ("item1", "mt_pay")),
        "'sent u 400 for friday, check ur bank' from MERROW at 2:20 p.m. MST on Nov 16, and 'got "
        "the 400, thx' from ODUM twenty minutes later. The event row rests on reading those as a "
        "payment sent and received; no record shows the transfer itself. The expert decides that "
        "reading.",
        "That morning MERROW wrote to Item 1's 'Brynn' 'sent u 40 for the gas, check ur bank'. "
        "The sheet quotes the Telegram message and names ODUM.",
        (("item1", "br_gas"),),
        "defined terms (SHOP BURGLARY, SUBJECT-1), a role (the COURIER), a relative date, "
        "indirect speech",
    ),
    C(
        "C48",
        "event",
        "affidavit",
        "contradicted",
        "second_phone",
        "In the seven days starting the day after the STOP, SUBJECT-2 stopped phoning the COURIER.",
        ("No call between VARGA and ODUM, Nov 20 to 26",),
        (("item3", "cl_vo23"),),
        "On Nov 23 VARGA called ODUM for 210 s; Item 3's call log holds it. The calls had not "
        "stopped.",
        "Item 2's report does not hold the call: a repair limited to SUBJECT-2's phone finds none. "
        "The sheet searches both phones.",
        (("item3", "cl_vo23"),),
        "defined terms (STOP, SUBJECT-2), a role (the COURIER), a relative range",
    ),
)

# One line per claim for the signing sheet.
SUMMARY: dict[str, str] = {
    "C01": "Sent 7:25 p.m. MDT Oct 9; Item 2 prints Oct 10 (UTC+0).",
    "C02": "Observed on Items 2 and 3, Oct 21.",
    "C03": "Sent by Item 2's 'Cal' (WhatsApp 13035550161), not ODUM's 17205550168.",
    "C04": "The BURNER's text on Item 3, 6:50 p.m. Oct 30; MERROW as its user rests on the "
    "number's self-identification only.",
    "C05": "Item 3 (the ONEPLUS) received it at 3:40 a.m. MST Nov 2; Item 2 lacks it.",
    "C06": "No such text anywhere; 'Arlo' got 'nobody rides the quad till december'.",
    "C07": "Item 3's 'Toby' holds +17205550134; Item 2's 'Toby' is another number.",
    "C08": "Item 1's 'Cal' holds 0153; 0168 is saved as 'Cal 2'. Not shown (contact lists edit).",
    "C09": "Two Telegram ids: 'Toby M' 6630401, 'T.M.' 6630488.",
    "C10": "One Telegram id, 6630402 (Item 2's own); Item 3 shows 'Ines V' to Nov 8, 'vee.rides' "
    "from Nov 10.",
    "C11": "Item 2's 'T2' holds +17205550186; she wrote 'saved as T2'.",
    "C12": "Item 2's 'Toby' (+13035550139) sent it, not MERROW's +17205550134.",
    "C13": "9:31 p.m. MDT, 288 s; Item 3 prints 8:31 PM(UTC-7), and 9:30 PM for a 41 s call.",
    "C14": "11:52 p.m. MST, 128 s; Item 2 prints 11:50 PM for a 4:50 p.m. call of 305 s.",
    "C15": "Sent 7:45 p.m. MDT Oct 24; 6:45 PM is Item 3's UTC-7 print.",
    "C16": "10:07 p.m., 92 s, from the BURNER (Item 3).",
    "C17": "1:34 a.m. MST, the second 1 a.m. hour.",
    "C18": "No FENCE call; the 3:22 p.m. call is to Item 3's 'Jory', +17205550181.",
    "C19": "'the emtbs?' / 'ya electric mountain bikes, all 6' fix the meaning.",
    "C20": "Observed; 'the cold ones' is not fixed (and the same words went to 'Arlo' about "
    "drinks).",
    "C21": "VARGA sent it, not ODUM.",
    "C22": "Nov 3: 'on here we call them pizzas' after 'do the batteries come off' fixes it.",
    "C23": "'the pindlewick road bikes?' / 'ya the carbon ones from friday, all 4' fix it.",
    "C24": "Two Cals on Item 2; which one is not fixed.",
    "C25": "7 on Denver dates; printed dates give 8.",
    "C26": "5 on Item 3; Item 2 has 6.",
    "C27": "6 on Nov 14 local; a UTC day gives 4.",
    "C28": "5 texts ODUM to the BURNER, Oct 27-31 on Item 3.",
    "C29": "3 on Item 1 (curated); Item 3 holds 5.",
    "C30": "12 in 11 p.m.-3 a.m. (five hours, DST ended); a four-hour window gives 10 or 9.",
    "C31": "12:30 a.m. MDT Oct 23 text; Item 3 prints Oct 22.",
    "C32": "Signal exchange on Nov 23.",
    "C33": "No record with 0129; Item 3's 'Jory' is 0181. Curated, so not shown.",
    "C34": "None 1-2 a.m. MST; the 1:25 a.m. WhatsApp is in the first (MDT) hour.",
    "C35": "VARGA-ODUM WhatsApp on Nov 15 and 16.",
    "C36": "None on Item 1 (curated); Item 3 holds a Nov 22 text.",
    "C37": "ODUM asked the price, VARGA set it, he took it.",
    "C38": "MERROW sent 'friday 9:30, back door'.",
    "C39": "VARGA offered herself; recruitment is interpretation.",
    "C40": "Her assignment and his 'ok i got marketplace', on Item 3 only.",
    "C41": "Sent 11:20 p.m. Friday Oct 31; Item 2 prints Saturday 5:20 AM.",
    "C42": "'staff all gone' went to Item 2's 'Cal'; no watch shown.",
    "C43": "Proposal and 'bet' on Oct 28; Thursday is Oct 30.",
    "C44": "Request and 'ok ill move them tonight' on Nov 18.",
    "C45": "Only a 50 s call; the eight-minute call is with Item 2's 'Cal'.",
    "C46": "5:48 a.m. MST Nov 2, on Item 3 only.",
    "C47": "Message and 'got the 400, thx' on Nov 16; 'paid' rests on reading those words.",
    "C48": "VARGA called ODUM on Nov 23, on Item 3's log only.",
}

# Affidavit layout: (page, paragraph parts). A part is plain text or a claim id. Paragraphs are
# numbered from 1 in this order.
AFFIDAVIT: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            "I, Detective L. Strand of the Juniper Valley Property Crimes Unit (a fictional "
            "agency), make this affidavit from my training, experience and review of the evidence "
            "described below.",
        ),
    ),
    (
        1,
        (
            "This affidavit relies on forensic extraction reports for three phones. Item 1 is a "
            'Samsung Galaxy A54 (the "SAMSUNG") seized from TOBIAS MERROW ("MERROW" or '
            '"SUBJECT-1"), who goes by "TOBY". Item 2 is an Apple iPhone 13 (the "iPHONE") seized '
            'from INES VARGA ("VARGA" or "SUBJECT-2"). Item 3 is a OnePlus Nord N30 (the '
            '"ONEPLUS") seized from CALVIN ODUM ("ODUM" or "SUBJECT-3"), called "CAL", who moved '
            'the stolen property for MERROW and VARGA (the "COURIER").',
        ),
    ),
    (
        1,
        (
            'MERROW also used a second phone number, +1 (720) 555-0186 (the "BURNER"). A buyer '
            'of stolen bicycles, referred to below as the "FENCE", used the number +1 (720) '
            "555-0129.",
        ),
    ),
    (
        1,
        (
            "On the night of Saturday, November 1, 2025, into the early hours of Sunday, November "
            "2, 2025 (the night the clocks went back an hour, at 2 a.m.), eleven electric "
            "bicycles and a pallet of ski boots were taken from storage lockers at Quillbarrow "
            'Self Storage on Bramblewood Road (the "LOCKER BURGLARY").',
        ),
    ),
    (
        1,
        (
            "On Friday, November 14, 2025, at about 9:40 p.m., four carbon road bikes and a box "
            "of wheelsets were taken from Pindlewick Cycles on Larch Street (the "
            '"BIKE SHOP"). That theft is referred to below as the "SHOP BURGLARY".',
        ),
    ),
    (
        1,
        (
            "On Wednesday, November 19, 2025, at 3:10 p.m., officers stopped a white box van "
            'driven by ODUM on County Road 9 (the "STOP") and recovered three of the electric '
            "bicycles. ODUM was released at the scene. The three phones were seized on December "
            "3, 2025.",
        ),
    ),
    (1, ("All times in this affidavit are Mountain time, the time the phones themselves kept.",)),
    (2, ("C39", "C01", "C19", "C25")),
    (2, ("C13", "C02", "C31", "C15")),
    (2, ("C07", "C08", "C11", "C12")),
    (2, ("C43", "C28", "C04", "C41")),
    (3, ("C30", "C17", "C34")),
    (3, ("C05", "C46")),
    (3, ("C20", "C22", "C40", "C06", "C45")),
    (3, ("C37", "C03", "C26", "C10")),
    (3, ("C29", "C21", "C38", "C27")),
    (4, ("C42", "C16", "C14", "C35", "C47", "C23")),
    (4, ("C44", "C18", "C24", "C09", "C32", "C36", "C48", "C33")),
    (
        4,
        (
            "Based on the above, I believe there is probable cause that MERROW, VARGA and ODUM "
            "took part in the burglaries described above and in the sale of the stolen property.",
        ),
    ),
)


# ---------------------------------------------------------------- DRAFT assumption sheet

MER, VAR, ODU = "person:merrow", "person:varga", "person:odum"
ITEM1, ITEM2, ITEM3 = "dev:item1", "dev:item2", "dev:item3"
BUR2 = "acct:item2:SMS:+17205550186"  # the BURNER, as Item 2 logs it
BUR3 = "acct:item3:SMS:+17205550186"  # the BURNER, as Item 3 logs it
FEN2 = "acct:item2:SMS:+17205550129"  # the FENCE's number (paragraph 3), as Item 2 logs it
MER_ON_ITEM3 = "acct:item3:SMS:+17205550134"
ODU_ON_ITEM1 = "acct:item1:SMS:+17205550168"
VAR_TG2 = "acct:item2:Telegram:6630402"  # SUBJECT-2's Telegram account, on her own phone
VAR_TG3 = "acct:item3:Telegram:6630402"  # the same account as Item 3 logs it

Expect = Literal["pass", "fail", "inconclusive"] | None


def window(
    start: str,
    end_exclusive: str,
    raw: str,
    tz: str = TZ,
    fold_start: int = 0,
    fold_end: int = 0,
) -> dict[str, str]:
    """Wall-clock [start, end_exclusive) in tz -> the contract's inclusive UTC TimeWindow.

    The same arithmetic as core.audit.assumptions.local_window and the case04 sheet. A fold of 1
    picks the second pass of a wall-clock time that happened twice (1 a.m. on 2025-11-02).
    """
    zone = ZoneInfo(tz)
    s = datetime.fromisoformat(start).replace(tzinfo=zone, fold=fold_start).astimezone(UTC)
    e = datetime.fromisoformat(end_exclusive).replace(tzinfo=zone, fold=fold_end).astimezone(UTC)
    e -= timedelta(microseconds=1)
    return {
        "start_utc": s.isoformat().replace("+00:00", "Z"),
        "end_utc": e.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "tz": tz,
        "raw": raw,
    }


def day(date: str, raw: str) -> dict[str, str]:
    """One local calendar day."""
    start = datetime.fromisoformat(date)
    return window(date, (start + timedelta(days=1)).date().isoformat(), raw)


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


Q01 = "back row at quillbarrow has no cameras"
Q02 = "unit 41, code is 7719"
Q03 = "the blue ones fit in my hatchback"
Q04 = "gate code is 2291, use the side lane"
Q05 = "park it behind the feed store till light"
Q06 = "nobody rides them till december"
Q12 = "left the key under the blue pot"
Q15 = "need u next saturday, bring the trailer"
Q17 = "last two are in the van"
Q19 = "found 6 tall ones in the back row"
Q20 = "the cold ones are in the garage"
Q21 = "the shop on larch closes at 9 on fridays"
Q22 = "grab the pizzas from the container"
Q23 = "the 4 skinnies are at the dock"
Q24 = "cal is getting nervous"
Q37 = "1400 each, dont go under 1200"
Q38 = "friday 9:30, back door"
Q40 = "u handle marketplace, i do insta"
Q41 = "start with 12 and 14, then the cage"
Q43 = "grain elevator lot thursday 7pm"
Q44_ASK = "need the road bikes out of unit 41 by thurs"
Q44_OK = "ok ill move them tonight"
Q46 = "back at the yard"
Q47 = "sent u 400 for friday, check ur bank"

# 1 to 2 a.m. MST on Nov 2: the second pass of the hour (08:00 to 09:00 UTC)
SECOND_ONE_AM = "2025-11-02T01:00:00"
AFTER_STOP = window(
    "2025-11-20",
    "2025-12-01",
    "From the day after the STOP to the end of November (November 20 to 30, 2025)",
)

SHEET: tuple[ClaimSpec, ...] = (
    # ------------------------------------------------------------ communication
    ClaimSpec(
        "C01",
        (
            A(
                "sender",
                P(quoted_text=Q01, person_ids=[MER], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q01,
                    person_ids=[MER, VAR],
                    channels=["SMS"],
                    window=day("2025-10-09", "On October 9, 2025"),
                ),
                "pass",
                "7:25 p.m. MDT Oct 9; Item 2 prints 10/10 1:25:10 AM(UTC+0).",
            ),
        ),
    ),
    ClaimSpec(
        "C02",
        (
            A(
                "sender",
                P(quoted_text=Q02, person_ids=[VAR], channels=["WhatsApp"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q02,
                    person_ids=[VAR, ODU],
                    channels=["WhatsApp"],
                    window=day("2025-10-21", "On October 21, 2025"),
                ),
                "pass",
                "2:05 p.m. MDT Oct 21.",
            ),
        ),
    ),
    ClaimSpec(
        "C03",
        (
            A(
                "sender",
                P(quoted_text=Q03, person_ids=[ODU], channels=["WhatsApp"]),
                "fail",
                "The one copy came from WhatsApp 13035550161, Item 2's 'Cal', not from ODUM's "
                "17205550168.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q03,
                    channels=["WhatsApp"],
                    device_ids=[ITEM2],
                    window=day("2025-11-06", "On November 6, 2025"),
                ),
                "pass",
                "10:15 a.m. MST Nov 6, on Item 2.",
            ),
        ),
        gaps=("That VARGA received it is shown by the time row's phone (Item 2), not by a party.",),
    ),
    ClaimSpec(
        "C04",
        (
            A(
                "sender",
                P(quoted_text=Q04, account_ids=[BUR3], channels=["SMS"]),
                "pass",
                "Incoming on Item 3 from the BURNER (paragraph 3).",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q04,
                    person_ids=[ODU],
                    account_ids=[BUR3],
                    channels=["SMS"],
                    window=day(
                        "2025-10-30",
                        "Two days before the LOCKER BURGLARY (Thursday, October 30, 2025)",
                    ),
                ),
                "pass",
                "6:50 p.m. MDT Oct 30 (printed 5:50:40 PM(UTC-7)).",
            ),
            A(
                "authorship",
                P(quoted_text=Q04, person_ids=[MER], account_ids=[BUR3], channels=["SMS"]),
                None,
                "That MERROW used the BURNER: paragraph 3, and the number's own 'its toby. new "
                "number, use this one for work stuff' (Item 3 saves it as 'Toby work'). Core: "
                "the expert decides it.",
            ),
        ),
    ),
    ClaimSpec(
        "C05",
        (
            A(
                "sender",
                P(quoted_text=Q05, person_ids=[VAR], channels=["Telegram"]),
                "pass",
                "SUBJECT-2 is VARGA; her Telegram (6630402) sent it.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q05,
                    person_ids=[VAR, ODU],
                    device_ids=[ITEM3],
                    channels=["Telegram"],
                    window=window(
                        "2025-11-02T00:00:00",
                        "2025-11-02T06:00:00",
                        "In the early hours of November 2, 2025 (midnight to 6 a.m.)",
                    ),
                ),
                "pass",
                "The ONEPLUS is Item 3 (paragraph 2). 3:40 a.m. MST Nov 2.",
            ),
        ),
    ),
    ClaimSpec(
        "C06",
        (
            A(
                "sender",
                P(quoted_text=Q06, person_ids=[MER], channels=["SMS"]),
                "inconclusive",
                "No message with these words on any phone.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q06,
                    person_ids=[MER, ODU],
                    channels=["SMS"],
                    window=day(
                        "2025-11-04", "On the Tuesday after the LOCKER BURGLARY (November 4, 2025)"
                    ),
                ),
                "inconclusive",
                "The Tuesday after the Saturday-night burglary is Nov 4. Not found.",
            ),
        ),
    ),
    # ------------------------------------------------------------ identity
    ClaimSpec(
        "C07",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM3], quoted_text="Toby", account_ids=[MER_ON_ITEM3]),
                "pass",
                "Item 3's 'Toby' holds +17205550134.",
            ),
        ),
    ),
    ClaimSpec(
        "C08",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM1], quoted_text="Cal", account_ids=[ODU_ON_ITEM1]),
                "inconclusive",
                "Item 1's 'Cal' holds +17205550153; a missing entry is never a fail.",
            ),
        ),
        (
            "Unproven, not contradicted: the contact check never fails on a missing entry "
            "(contact lists are edited, and a curated report may leave entries out), so Item 1's "
            "'Cal' holding +17205550153 does not rule out an entry 'Cal' with +17205550168.",
        ),
    ),
    ClaimSpec(
        "C09",
        (
            A(
                "same_account",
                P(channels=["Telegram"], handles=["Toby M", "T.M."], device_ids=[ITEM3]),
                "fail",
                "'Toby M' resolves to user id 6630401 and 'T.M.' to 6630488.",
            ),
        ),
    ),
    ClaimSpec(
        "C10",
        (
            A(
                "same_account",
                P(channels=["Telegram"], handles=["Ines V", "vee.rides"], device_ids=[ITEM3]),
                "pass",
                "Both names resolve to Telegram user id 6630402 (Item 2's own account). The "
                "check resolves names on every phone, not only Item 3; on Telegram only Item 3 "
                "shows her account.",
            ),
            A(
                "person_identity",
                P(
                    person_ids=[VAR],
                    account_ids=[VAR_TG2, VAR_TG3],
                    channels=["Telegram"],
                ),
                None,
                "That user id 6630402 is SUBJECT-2's: it is Item 2's own Telegram account (its "
                "User Accounts sheet, and the outgoing copies on Item 2), and Item 2 is VARGA's "
                "phone (the shared device attribution). Core: the expert decides it.",
            ),
        ),
        (
            "same_account passes because the account's display name is the first name it shows "
            "('Ines V'), and later rows' sender cells show 'vee.rides'. No row tests when the "
            "name changed: 'from November 10' rests on the printed rows (last 'Ines V' 7:30 p.m. "
            "Nov 8, first 'vee.rides' 4:45 p.m. Nov 10).",
        ),
    ),
    ClaimSpec(
        "C11",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM2], quoted_text="T2", account_ids=[BUR2]),
                "pass",
                "The iPHONE is Item 2.",
            ),
        ),
    ),
    ClaimSpec(
        "C12",
        (
            A(
                "sender",
                P(quoted_text=Q12, person_ids=[MER], channels=["SMS"]),
                "fail",
                "The one copy came from +13035550139, Item 2's 'Toby', not from MERROW.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q12,
                    channels=["SMS"],
                    device_ids=[ITEM2],
                    window=day("2025-11-11", "on November 11, 2025"),
                ),
                "pass",
                "9:40 a.m. MST Nov 11, on Item 2.",
            ),
        ),
        gaps=(
            "That the sender was shown as 'Toby' is in the claim's words; the sender row tests "
            "the account, not the saved name.",
        ),
    ),
    # ------------------------------------------------------------ timing
    ClaimSpec(
        "C13",
        (
            A(
                "record_time",
                P(
                    person_ids=[MER, ODU],
                    channels=["call"],
                    duration_s=[240, 360],
                    window=window(
                        "2025-10-17T21:22:00",
                        "2025-10-17T21:39:00",
                        "At about 9:30 p.m. on October 17, 2025",
                    ),
                ),
                "pass",
                "9:31:05 p.m. MDT, 288 s. Item 3 prints 8:31:05 PM(UTC-7).",
            ),
        ),
        gaps=(
            "No template says who placed a call; Item 1 logs it as outgoing, as the claim says.",
        ),
    ),
    ClaimSpec(
        "C14",
        (
            A(
                "record_time",
                P(
                    person_ids=[VAR, ODU],
                    channels=["call"],
                    duration_s=[90, 150],
                    window=window(
                        "2025-11-14T23:42:00",
                        "2025-11-14T23:59:00",
                        "At about 11:50 p.m. on November 14, 2025",
                    ),
                ),
                "pass",
                "11:52:10 p.m. MST, 128 s. The 4:50 p.m. call (305 s) is outside.",
            ),
        ),
        gaps=(
            "No template says who placed a call; Item 2 logs it as outgoing, as the claim says.",
        ),
    ),
    ClaimSpec(
        "C15",
        (
            A(
                "sender",
                P(quoted_text=Q15, person_ids=[MER], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q15,
                    person_ids=[MER, ODU],
                    channels=["SMS"],
                    window=window(
                        "2025-10-24T18:45:00",
                        "2025-10-24T18:46:00",
                        "At 6:45 p.m. on October 24, 2025",
                    ),
                ),
                "fail",
                "Sent 7:45:30 p.m. MDT Oct 24; 6:45:30 PM is Item 3's UTC-7 print.",
            ),
        ),
    ),
    ClaimSpec(
        "C16",
        (
            A(
                "record_time",
                P(
                    person_ids=[ODU],
                    account_ids=[BUR3],
                    channels=["call"],
                    duration_s=[70, 110],
                    window=window(
                        "2025-11-14T21:40:00",
                        "2025-11-14T22:40:00",
                        "Within an hour after the SHOP BURGLARY (9:40 to 10:40 p.m., November 14, "
                        "2025)",
                    ),
                ),
                "pass",
                "10:07:15 p.m. MST, 92 s, from +17205550186.",
            ),
        ),
        gaps=(
            "No template says who placed a call; Item 3 logs it as incoming from the BURNER, as "
            "the claim says.",
        ),
    ),
    ClaimSpec(
        "C17",
        (
            A(
                "sender",
                P(quoted_text=Q17, person_ids=[MER], channels=["Signal"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q17,
                    person_ids=[MER, VAR],
                    channels=["Signal"],
                    window=window(
                        SECOND_ONE_AM,
                        "2025-11-02T02:00:00",
                        "In the hour after the clocks went back that night (1 to 2 a.m. MST, "
                        "November 2, 2025)",
                        fold_start=1,
                    ),
                ),
                "pass",
                "1:34:50 a.m. MST (08:34:50 UTC); the first 1 a.m. hour is 07:00 to 08:00 UTC.",
            ),
        ),
    ),
    ClaimSpec(
        "C18",
        (
            A(
                "record_time",
                P(
                    person_ids=[ODU],
                    account_ids=[FEN2],
                    channels=["call"],
                    window=window(
                        "2025-11-19T15:10:00",
                        "2025-11-19T15:40:00",
                        "Within half an hour after the STOP (3:10 to 3:40 p.m., November 19, 2025)",
                    ),
                ),
                "inconclusive",
                "No call with the FENCE's number; the 3:22 p.m. call is to Item 3's 'Jory', "
                "+17205550181.",
            ),
        ),
    ),
    # ------------------------------------------------------------ content meaning
    ClaimSpec(
        "C19",
        (
            A(
                "sender",
                P(quoted_text=Q19, person_ids=[MER], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q19,
                    person_ids=[MER, VAR],
                    channels=["SMS"],
                    window=day("2025-10-14", "On October 14, 2025"),
                ),
                "pass",
                "12:40 p.m. MDT Oct 14.",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q19,
                    person_ids=[MER, VAR],
                    channels=["SMS"],
                    window=day("2025-10-14", "On October 14, 2025"),
                ),
                None,
                "'the emtbs?' / 'ya electric mountain bikes, all 6' in the same exchange.",
            ),
        ),
    ),
    ClaimSpec(
        "C20",
        (
            A(
                "sender",
                P(quoted_text=Q20, person_ids=[MER], channels=["SMS"]),
                "pass",
                "Both copies of the words (to VARGA and to 'Arlo') came from MERROW.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q20,
                    person_ids=[MER, VAR],
                    channels=["SMS"],
                    window=day("2025-11-03", "On November 3, 2025"),
                ),
                "pass",
                "8:30 p.m. MST Nov 3; Item 2 prints 11/4 3:30:25 AM(UTC+0).",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q20,
                    person_ids=[MER, VAR],
                    channels=["SMS"],
                    window=day("2025-11-03", "On November 3, 2025"),
                ),
                None,
                "Whether 'the cold ones' are e-bikes without batteries; nothing fixes it.",
            ),
        ),
    ),
    ClaimSpec(
        "C21",
        (
            A(
                "sender",
                P(quoted_text=Q21, person_ids=[ODU], channels=["SMS"]),
                "fail",
                "VARGA sent it to ODUM.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q21,
                    channels=["SMS"],
                    window=day("2025-11-12", "On November 12, 2025"),
                ),
                "pass",
                "5:10 p.m. MST Nov 12.",
            ),
            A(
                "meaning",
                P(quoted_text=Q21, channels=["SMS"]),
                None,
                "That the words tell when the BIKE SHOP would be empty.",
            ),
        ),
    ),
    ClaimSpec(
        "C22",
        (
            A(
                "sender",
                P(quoted_text=Q22, person_ids=[MER], channels=["Telegram"]),
                "pass",
                "TOBY is MERROW; outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q22,
                    person_ids=[MER, ODU],
                    channels=["Telegram"],
                    window=window(
                        "2025-11-04T17:00:00",
                        "2025-11-05T00:00:00",
                        "The next evening (November 4, 2025, 5 p.m. to midnight)",
                    ),
                ),
                "pass",
                "'The next evening' follows C20's November 3. 6:40 p.m. MST Nov 4.",
            ),
            A(
                "meaning",
                P(quoted_text=Q22, person_ids=[MER, ODU], channels=["Telegram"]),
                None,
                "The Nov 3 'on here we call them pizzas' fixes 'pizzas'.",
            ),
        ),
    ),
    ClaimSpec(
        "C23",
        (
            A(
                "sender",
                P(quoted_text=Q23, account_ids=[BUR2], channels=["SMS"]),
                "pass",
                "Incoming on Item 2 from the BURNER (paragraph 3).",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q23,
                    person_ids=[VAR],
                    account_ids=[BUR2],
                    channels=["SMS"],
                    window=day("2025-11-16", "Three days before the STOP (November 16, 2025)"),
                ),
                "pass",
                "11:05 a.m. MST Nov 16.",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q23,
                    person_ids=[VAR],
                    account_ids=[BUR2],
                    channels=["SMS"],
                    window=day("2025-11-16", "Three days before the STOP (November 16, 2025)"),
                ),
                None,
                "'the pindlewick road bikes?' / 'ya the carbon ones from friday, all 4' after it "
                "fix the meaning.",
            ),
        ),
    ),
    ClaimSpec(
        "C24",
        (
            A(
                "sender",
                P(quoted_text=Q24, person_ids=[VAR], channels=["SMS"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q24,
                    person_ids=[VAR, MER],
                    channels=["SMS"],
                    window=day("2025-11-21", "Two days after the STOP (November 21, 2025)"),
                ),
                "pass",
                "8:20 p.m. MST Nov 21.",
            ),
            A(
                "meaning",
                P(quoted_text=Q24, person_ids=[VAR, MER], channels=["SMS"]),
                None,
                "Which Cal; not fixed.",
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
                    device_ids=[ITEM2],
                    person_ids=[MER, VAR],
                    channels=["Signal"],
                    expected_count=7,
                    count_op="eq",
                    each_way=True,
                    window=window(
                        "2025-10-13", "2025-10-20", "Between October 13 and October 19, 2025"
                    ),
                ),
                "pass",
                "Seven on Denver dates; printed dates give eight.",
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
                    person_ids=[ODU, VAR],
                    channels=["Telegram"],
                    expected_count=5,
                    count_op="eq",
                    each_way=True,
                    window=window(
                        "2025-11-03", "2025-11-10", "From November 3 through November 9, 2025"
                    ),
                ),
                "pass",
                "Five on Item 3; Item 2 holds six.",
            ),
        ),
    ),
    ClaimSpec(
        "C27",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM2],
                    person_ids=[MER, VAR],
                    channels=["SMS"],
                    expected_count=4,
                    count_op="eq",
                    each_way=True,
                    window=day("2025-11-14", "On November 14, 2025"),
                ),
                "fail",
                "Six on the Denver day.",
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
                    person_ids=[ODU],
                    account_ids=[BUR3],
                    channels=["SMS"],
                    expected_count=5,
                    count_op="eq",
                    sent_by=[ODU],
                    window=window(
                        "2025-10-27",
                        "2025-11-01",
                        "In the five days before the LOCKER BURGLARY (Monday, October 27 to "
                        "Friday, October 31, 2025)",
                    ),
                ),
                "pass",
                "Five from ODUM to the BURNER on Item 3 (the ONEPLUS).",
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
                    person_ids=[MER, ODU],
                    channels=["Telegram"],
                    expected_count=5,
                    count_op="ge",
                    window=window(
                        "2025-11-10", "2025-11-14", "Between November 10 and November 13, 2025"
                    ),
                ),
                "inconclusive",
                "Three on the SAMSUNG (Item 1); fewer than claimed is never a fail.",
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
                    person_ids=[MER, VAR],
                    channels=["Signal"],
                    expected_count=12,
                    count_op="ge",
                    each_way=True,
                    window=window(
                        "2025-11-01T23:00:00",
                        "2025-11-02T03:00:00",
                        "On the night of the LOCKER BURGLARY, between 11 p.m. and 3 a.m.",
                    ),
                ),
                "pass",
                "Twelve in the five real hours (05:00 to 10:00 UTC) on the iPHONE.",
            ),
        ),
    ),
    # ------------------------------------------------------------ absence
    ClaimSpec(
        "C31",
        (
            A(
                "no_contact",
                P(person_ids=[MER, ODU], window=day("2025-10-23", "on October 23, 2025")),
                "fail",
                "The 12:30 and 12:40 a.m. MDT texts.",
            ),
        ),
    ),
    ClaimSpec(
        "C32",
        (
            A(
                "no_contact",
                P(
                    person_ids=[VAR, MER],
                    window=window(
                        "2025-11-22", "2025-11-25", "between November 22 and November 24, 2025"
                    ),
                ),
                "fail",
                "The Nov 23 Signal exchange. No channel: the claim says any kind.",
            ),
        ),
    ),
    ClaimSpec(
        "C33",
        (
            A(
                "no_contact",
                P(
                    person_ids=[ODU],
                    account_ids=[FEN2],
                    window=window(
                        "2025-11-01", "2025-12-01", "between November 1 and November 30, 2025"
                    ),
                ),
                "inconclusive",
                "None found; curated reports. Item 3's 'Jory' is another number.",
            ),
        ),
    ),
    ClaimSpec(
        "C34",
        (
            A(
                "no_contact",
                P(
                    person_ids=[ODU, VAR],
                    window=window(
                        SECOND_ONE_AM,
                        "2025-11-02T02:00:00",
                        "Once the clocks had gone back that night, for the next hour (1 to 2 "
                        "a.m. MST, November 2, 2025)",
                        fold_start=1,
                    ),
                ),
                "inconclusive",
                "None in the hour; the 1:25 a.m. WhatsApp is in the first, MDT, hour.",
            ),
        ),
    ),
    ClaimSpec(
        "C35",
        (
            A(
                "no_contact",
                P(
                    person_ids=[VAR, ODU],
                    window=window(
                        "2025-11-15",
                        "2025-11-18",
                        "On the three days after the day of the SHOP BURGLARY (November 15 to "
                        "17, 2025)",
                    ),
                ),
                "fail",
                "CAL is ODUM (paragraph 2). WhatsApp on Nov 15 and 16.",
            ),
        ),
    ),
    ClaimSpec(
        "C36",
        (
            A(
                "no_contact",
                P(person_ids=[MER, ODU], device_ids=[ITEM1], window=AFTER_STOP),
                "inconclusive",
                "None on Item 1 (the SAMSUNG); curated. Item 3 holds a Nov 22 text.",
            ),
        ),
    ),
    # ------------------------------------------------------------ role
    ClaimSpec(
        "C37",
        (
            A(
                "sender",
                P(quoted_text=Q37, person_ids=[VAR], channels=["WhatsApp"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q37,
                    person_ids=[VAR, ODU],
                    channels=["WhatsApp"],
                    window=day("2025-11-05", "On November 5, 2025"),
                ),
                "pass",
                "1:06 p.m. MST Nov 5.",
            ),
            A(
                "role",
                P(person_ids=[VAR, ODU], channels=["WhatsApp"]),
                None,
                "That VARGA set the asking price: ODUM asked her what to ask and took her figure.",
            ),
        ),
    ),
    ClaimSpec(
        "C38",
        (
            A(
                "sender",
                P(quoted_text=Q38, person_ids=[ODU], channels=["SMS"]),
                "fail",
                "MERROW sent it.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q38,
                    channels=["SMS"],
                    window=day("2025-11-13", "On November 13, 2025"),
                ),
                "pass",
                "7:40 p.m. MST Nov 13.",
            ),
            A("role", P(person_ids=[ODU]), None, "That ODUM set the time."),
        ),
    ),
    ClaimSpec(
        "C39",
        (
            A(
                "role",
                P(person_ids=[MER, VAR]),
                None,
                "That MERROW recruited VARGA; VARGA offered herself.",
            ),
        ),
        gaps=(
            "The claim quotes nothing and names no time, so no check applies; only the expert can "
            "decide it.",
        ),
    ),
    ClaimSpec(
        "C40",
        (
            A(
                "sender",
                P(quoted_text=Q40, person_ids=[VAR], channels=["WhatsApp"]),
                "pass",
                "SUBJECT-2 is VARGA; the only copy is incoming on Item 3. No phone named.",
            ),
            A(
                "role",
                P(person_ids=[VAR, ODU], quoted_text=Q40, channels=["WhatsApp"]),
                None,
                "That VARGA gave ODUM the marketplace listings: her assignment and his 'ok i got "
                "marketplace'.",
            ),
        ),
        gaps=("The claim names no time, so no time row; the exchange is on Nov 3.",),
    ),
    ClaimSpec(
        "C41",
        (
            A(
                "sender",
                P(quoted_text=Q41, person_ids=[VAR], channels=["WhatsApp"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q41,
                    person_ids=[VAR, ODU],
                    channels=["WhatsApp"],
                    window=window(
                        "2025-11-01T05:00:00",
                        "2025-11-01T12:00:00",
                        "On the Saturday morning before the LOCKER BURGLARY (November 1, 2025, 5 "
                        "a.m. to noon)",
                    ),
                ),
                "fail",
                "Sent 11:20:30 p.m. MDT Friday Oct 31; Item 2 prints 11/1 5:20:30 AM(UTC+0).",
            ),
            A("role", P(person_ids=[VAR]), None, "That VARGA chose the lockers."),
        ),
    ),
    ClaimSpec(
        "C42",
        (
            A(
                "role",
                P(
                    person_ids=[VAR],
                    window=window(
                        "2025-11-14T20:40:00",
                        "2025-11-14T21:40:00",
                        "In the hour before the SHOP BURGLARY (8:40 to 9:40 p.m., November 14, "
                        "2025)",
                    ),
                ),
                None,
                "That VARGA kept watch and reported to ODUM; the only 'staff all gone' text went "
                "to Item 2's 'Cal'.",
            ),
        ),
        gaps=("The claim paraphrases a text without quoting it; no check applies.",),
    ),
    # ------------------------------------------------------------ event
    ClaimSpec(
        "C43",
        (
            A(
                "sender",
                P(quoted_text=Q43, person_ids=[MER], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q43,
                    person_ids=[MER, ODU],
                    channels=["SMS"],
                    window=day("2025-10-28", "On October 28, 2025"),
                ),
                "pass",
                "12:05 p.m. MDT Oct 28.",
            ),
            A(
                "weekday_date",
                P(
                    quoted_text=Q43,
                    channels=["SMS"],
                    window=day("2025-10-30", "Thursday, October 30, 2025"),
                ),
                "pass",
                "'thursday' sent on Tuesday Oct 28 is Oct 30.",
            ),
            A(
                "event",
                P(
                    person_ids=[MER, ODU],
                    channels=["SMS"],
                    window=day("2025-10-28", "On October 28, 2025"),
                ),
                None,
                "That they arranged it: ODUM's 'bet'.",
            ),
        ),
        gaps=(
            "'The lot by the grain elevator' is tested only as words inside the quote, which the "
            "sender check matches verbatim; whether anyone met there is not tested.",
        ),
    ),
    ClaimSpec(
        "C44",
        (
            A(
                "sender",
                P(quoted_text=Q44_ASK, person_ids=[VAR], channels=["SMS"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "sender",
                P(quoted_text=Q44_OK, person_ids=[MER], channels=["SMS"]),
                "pass",
                "MERROW's answer, outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q44_ASK,
                    person_ids=[VAR, MER],
                    channels=["SMS"],
                    window=day("2025-11-18", "On November 18, 2025"),
                ),
                "pass",
                "10:30 a.m. MST Nov 18.",
            ),
        ),
    ),
    ClaimSpec(
        "C45",
        (
            A(
                "record_time",
                P(
                    person_ids=[VAR, ODU],
                    channels=["call"],
                    duration_s=[420, 540],
                    window=day("2025-11-04", "On November 4, 2025"),
                ),
                "inconclusive",
                "Their only call that day lasted 50 s; the 482 s call is with Item 2's 'Cal'.",
            ),
        ),
    ),
    ClaimSpec(
        "C46",
        (
            A(
                "sender",
                P(quoted_text=Q46, person_ids=[ODU], channels=["WhatsApp"]),
                "pass",
                "The COURIER's WhatsApp, outgoing on Item 3. No phone named.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q46,
                    person_ids=[ODU, VAR],
                    channels=["WhatsApp"],
                    window=window(
                        "2025-11-02T05:30:00",
                        "2025-11-02T06:00:00",
                        "Shortly before 6 a.m. that morning (November 2, 2025, 5:30 to 6 a.m.)",
                    ),
                ),
                "pass",
                "5:48:20 a.m. MST; 'that morning' follows C05's November 2.",
            ),
        ),
        (
            "'Let SUBJECT-2 know' rests on the sending alone: the only copy is outgoing on Item "
            "3, and Item 2's report does not hold it, so no record shows she received it.",
        ),
    ),
    ClaimSpec(
        "C47",
        (
            A(
                "sender",
                P(quoted_text=Q47, person_ids=[MER], channels=["Telegram"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q47,
                    person_ids=[MER, ODU],
                    channels=["Telegram"],
                    window=day(
                        "2025-11-16", "Two days after the SHOP BURGLARY (November 16, 2025)"
                    ),
                ),
                "pass",
                "2:20 p.m. MST Nov 16.",
            ),
            A(
                "event",
                P(
                    person_ids=[MER, ODU],
                    channels=["Telegram"],
                    window=day(
                        "2025-11-16", "Two days after the SHOP BURGLARY (November 16, 2025)"
                    ),
                ),
                None,
                "That he was paid: reading 'sent u 400 for friday' as money sent to him and 'got "
                "the 400, thx' as receipt.",
            ),
        ),
    ),
    ClaimSpec(
        "C48",
        (
            A(
                "no_contact",
                P(
                    person_ids=[VAR, ODU],
                    channels=["call"],
                    window=window(
                        "2025-11-20",
                        "2025-11-27",
                        "In the seven days starting the day after the STOP (November 20 to 26, "
                        "2025)",
                    ),
                ),
                "fail",
                "VARGA's Nov 23 call, held on Item 3's log only.",
            ),
        ),
        (
            "The no_contact row on calls has no direction, so any call between them fails it. "
            "'Stopped phoning' is about calls SUBJECT-2 placed; the fail is right because the Nov "
            "23 call is VARGA's, logged on Item 3 as incoming from her number. No template says "
            "who placed a call.",
        ),
    ),
)

# Claims no template can state, with the reason. None: every claim has a sheet.
NO_SHEET: dict[str, str] = {}

# ---------------------------------------------------------------- second read

# Where an alias the affidavit defines (case.json "aliases") matches a name inside a claim's
# quote. An alias is matched whole, in any case, so these match; that is real product behaviour
# and the claims keep their wording. Each line says which person the match points to, and
# whether that is right, so the signer sees it.
ALIAS_IN_QUOTES: dict[str, str] = {
    "C07": 'TOBY matches the quoted contact name "Toby" and points to MERROW. Right: Item 3\'s '
    "'Toby' holds MERROW's number, +17205550134.",
    "C08": 'CAL matches the quoted contact name "Cal" and points to ODUM. Right person, other '
    "number: Item 1's 'Cal' holds ODUM's work cell, +17205550153; the claim's +17205550168 is "
    "saved as 'Cal 2'.",
    "C09": 'TOBY matches the quoted Telegram name "Toby M" and points to MERROW. Right: \'Toby '
    "M' is user id 6630401, Item 1's own account. (\"T.M.\" matches no alias.)",
    "C12": 'TOBY matches the quoted sender name "Toby" and points to MERROW. Wrong: on Item 2, '
    "'Toby' is Toby Rusk, +13035550139. The claim's own TOBY is MERROW, rightly.",
    "C24": 'CAL matches "cal" in the quote "cal is getting nervous" and points to ODUM. Not '
    "fixed: Item 2 also saves Calla Brightwater as 'Cal' (+13035550161), and the conversation "
    "does not say which Cal is meant. The claim's own 'the COURIER' is ODUM.",
}

# Verdicts the second read changed: claim id -> the verdict first drafted.
FIRST_DRAFT_VERDICT: dict[str, str] = {"C04": "supported"}

SECOND_READ_DATE = "2026-10-31"


@dataclass(frozen=True)
class Finding:
    finding_id: str
    claims: tuple[str, ...]
    severity: str  # wrong verdict, sheet, weak, cosmetic (graded by the builder)
    outcome: Literal["fixed", "kept"]
    answer: str


# A second, blind reviewer imported the reports, ran the real checks on all 85 rows against
# rules 0.4.0 and recomputed every window: every row returned its expected check, every record
# id resolved, and no window edge, verdict or name was wrong. Its findings, one line each: what
# changed, or why it stayed.
SECOND_READ: tuple[Finding, ...] = (
    Finding(
        "R1",
        ("C04",),
        "weak",
        "fixed",
        "Now unproven: that SUBJECT-1 used the BURNER rests on paragraph 3 and the number's own "
        "'its toby', the self-identification the key refuses for 'T.M.', with a second Toby "
        "(Rusk, +13035550139) in the data and no record from MERROW's phone tying him to it. "
        "Split now 23/12/13. If Arsh accepts paragraph 3's premise, C04 goes back to supported.",
    ),
    Finding(
        "R2",
        ("C08",),
        "sheet",
        "fixed",
        "Gap added for signing: unproven, not contradicted, because the contact check never fails "
        "on a missing entry; 'Cal' holding 0153 does not rule out a 'Cal' entry with 0168.",
    ),
    Finding(
        "R3",
        ("C39",),
        "weak",
        "kept",
        "Unproven kept: VARGA offered to list bikes and MERROW answered 'good to know'; who "
        "recruited whom is interpretation (reading rule 9). Listed as a close call.",
    ),
    Finding(
        "R4",
        ("C25", "C26", "C27", "C30"),
        "sheet",
        "fixed",
        "each_way set on all four rows, as 'exchanged' asks. The checks rerun to pass, pass, fail "
        "and pass, as before.",
    ),
    Finding(
        "R5",
        ("C10",),
        "sheet",
        "fixed",
        "A core person_identity row now ties user id 6630402 to SUBJECT-2 (Item 2's own account; "
        "Item 2's copies added as key evidence). 'From the second week of November' is now 'From "
        "November 10, 2025', the edge the rows show. A gap says same_account passes on the "
        "account's first name seen and that no row tests the rename's timing.",
    ),
    Finding(
        "R6",
        ("C48",),
        "sheet",
        "fixed",
        "Gap added: no_contact on calls has no direction; the fail is right because the Nov 23 "
        "call is VARGA's, logged incoming from her number on Item 3.",
    ),
    Finding(
        "R7",
        ("C35", "C36", "C48"),
        "weak",
        "fixed",
        "Reworded so each window follows from the words: 'On the three days after the day of the "
        "SHOP BURGLARY' (Nov 15 to 17), 'From the day after the STOP to the end of November' "
        "(Nov 20 to 30), 'In the seven days starting the day after the STOP' (Nov 20 to 26). "
        "Sheet windows unchanged; reading rule 5 updated.",
    ),
    Finding(
        "R8",
        ("C36",),
        "weak",
        "fixed",
        "Now 'SUBJECT-1 and the COURIER had no contact, per the SAMSUNG', a claim about contact "
        "that rests on Item 1. Still unproven: a curated report cannot show an absence.",
    ),
    Finding(
        "R9",
        ("C22",),
        "weak",
        "fixed",
        "Narrowed to 'the battery packs': the thread fixes 'pizzas' as the batteries ('do the "
        "batteries come off those', 'on here we call them pizzas'), not what they came off. "
        "Supported kept.",
    ),
    Finding(
        "R10",
        ("C46",),
        "sheet",
        "fixed",
        "Gap added: 'let SUBJECT-2 know' rests on the sending alone; the only copy is outgoing "
        "on Item 3, and Item 2's report does not hold it.",
    ),
    Finding(
        "R11",
        ("C07", "C08", "C09", "C12", "C24"),
        "weak",
        "fixed",
        "Wording kept. Each alias match inside a quote is recorded (ALIAS_IN_QUOTES, shown in "
        "both drafts): TOBY points to MERROW in C07 and C09 (right) and C12 (wrong: Toby Rusk); "
        "CAL points to ODUM in C08 (right person, other number) and C24 (not fixed). C09 was "
        "found by the same scan.",
    ),
    Finding(
        "R12",
        ("C04", "C06", "C16", "C22", "C24", "C28", "C34", "C36", "C40", "C41", "C46", "C47", "C48"),
        "cosmetic",
        "kept",
        "'the COURIER' kept as the alias, the form every one of these claims uses; paragraph 2 "
        'prints the definition as (the "COURIER").',
    ),
    Finding(
        "R13",
        ("C01", "C23"),
        "weak",
        "fixed",
        "The storage site and the bike shop now carry clearly invented names (Quillbarrow Self "
        "Storage, Pindlewick Cycles), in the quotes too; the four Instagram handles end in "
        "'_fict'. Hazards unchanged. The signing sheet says every name, handle and id is "
        "invented.",
    ),
)

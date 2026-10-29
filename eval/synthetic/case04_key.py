"""Case04 mock affidavit, DRAFT answer key and DRAFT assumption sheet. SYNTHETIC.

DRAFT ONLY. Every verdict and every assumption row below is the builder's proposal. Arsh reviews
and decides each one; nothing here is gold until a human copies it into eval/gold/. The
affidavit text is generated from this file so claim wording stays verbatim.

case04 is the held-out set for the testability step's go/no-go. Its design was fixed before any
data was written, claim by claim, and is recorded here:

- 48 claims, 6 of each claim type in core/contracts.py. Draft verdicts: 24 supported, 12
  contradicted, 12 unproven, spread as each type allows (no absence claim can be supported on
  a curated report).
- Wording: per type, 3 claims "plain" (as case01's read) and 3 "affidavit" (defined terms,
  aliases, relative or approximate times, indirect speech, references back, roles, numbers in
  words).
- Hazard: a wrong reading the data holds a candidate for (a second person with the same first
  name or nickname, a second number or account for the same person, a second phone that could
  be meant, a near-miss window, one contact name on two phones, similar words in another
  thread). The sheet names only the right person, phone, account and window.
- A sheet for every claim (draft_assumptions.jsonl). Two role claims (C39, C42) have only a
  role row, which no check tests; every other claim has a core row a check tests.

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

DRAFT_LABEL = "DRAFT (case04 builder, not signed by Arsh)"
TEMPLATES_VERSION = "1.0.0"
TZ = "America/Chicago"

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
    "near_window": "a near-miss window: UTC against local time across midnight, the DST change, "
    "an adjacent day, or Item 3's fixed UTC-6 print",
    "contact_name": "one contact name saved on two phones for two people",
    "similar_quote": "similar words in another thread",
    "none": "no wrong reading planted",
}

READING_RULES = (
    "Times are the phones' own clock, America/Chicago (paragraph 7), never a printed value. Item 1 "
    "prints UTC+0. Item 2 prints each row's own offset. Item 3 prints every row at UTC-6, so from "
    "2 a.m. on March 8 (when the clocks went forward) its printed times are an hour behind the "
    "phone.",
    "'At about' is 8 minutes either side; 'about four minutes' is 210 to 270 s, 'about one "
    "minute' 40 to 80 s, 'about ten minutes' 540 to 660 s, 'a little under three minutes' 150 to "
    "179 s; 'a quarter to midnight' is 11:45 p.m.",
    "'Evening' is 5 p.m. to midnight; 'the early hours' midnight to 6 a.m.; 'the night of' a "
    "theft 5 p.m. to 6 a.m.; 'the hours before' the BELMONT SITE theft 6 to 11 p.m.; 'shortly "
    "before 5 a.m.' 4:30 to 5 a.m.; 'within fifteen minutes of' 10:30 p.m. is 10:15 to 10:45; "
    "'within half an hour after' it is 10:30 to 11 p.m.",
    "'After the SEARCH' starts the day after it (March 27); 'the rest of March' ends on March 31. "
    "'Monday through Wednesday' before the Thursday SEARCH is March 23 to 25. Relative dates count "
    "from the sentence before them: 'the next day' after March 14 is March 15, 'two days later' "
    "after March 9 is March 11.",
    "Defined terms are read as the affidavit defines them (paragraphs 2 and 3): HAL = SUBJECT-1 = "
    "HALLORAN; SUBJECT-2 = FERRO; DEZ = the DRIVER = SUBJECT-3 = OKAFOR; the TARGET PHONE is Item "
    "2, not HALLORAN's Item 1; the PREPAID is +13125550199, HALLORAN's second number; CW-1 is "
    "+17735550187; the BUYER is the Instagram account kipflips.chi.",
    "A claim is contradicted only when observed data rules it out: the quoted words came from "
    "another account, or at another time; a phone holds more messages than an exact count; "
    "contact is found where the claim says there was none.",
    "A curated report cannot show an absence, so an absence claim is never supported here: it is "
    "contradicted if contact is found and unproven otherwise. Not found never means did not "
    "happen.",
    "A meaning or role is supported only when the conversation itself fixes it; an agent's "
    "reading of slang or of who directed whom is interpretation.",
)

DEVICE_ATTRIBUTION = (
    "Item 1 is used by HALLORAN, Item 2 by FERRO and Item 3 by OKAFOR, so each phone's own "
    "accounts speak for its owner. The key treats this as given, as the affidavit does; it is not "
    "proven by the data. The PREPAID is HALLORAN's because paragraph 3 says so; Item 2 saves it "
    "as 'Hal 2' and it writes 'new number, its hal' (C08)."
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
        'On February 18, 2026, HALLORAN texted FERRO "need the big van sat, 6am".',
        ("HALLORAN's SMS account sent the message to FERRO on Feb 18, Chicago time",),
        (("item1", "hf_van"), ("item2", "hf_van")),
        "Outgoing SMS on Item 1 at 8:12 p.m. CST on Feb 18, incoming on Item 2.",
        "Item 1 prints it as 2/19/2026 2:12:40 AM(UTC+0); a window on the printed date misses it. "
        "FERRO's neighbour, the other Owen, asked to borrow the van two days earlier.",
        (("item1", "hf_van"), ("item2", "pr_van")),
    ),
    C(
        "C02",
        "communication",
        "plain",
        "supported",
        "none",
        'On March 4, 2026, FERRO sent OKAFOR a WhatsApp message reading "address is 2210 n '
        'kildare, side gate".',
        ("FERRO's WhatsApp account sent the message to OKAFOR on Mar 4",),
        (("item2", "fw_addr"), ("item3", "fw_addr")),
        "Outgoing on Item 2 at 2:40 p.m. CST on Mar 4, incoming on Item 3. A clean claim.",
    ),
    C(
        "C03",
        "communication",
        "plain",
        "contradicted",
        "same_name",
        'On March 10, 2026, OKAFOR texted FERRO "the yellow ones are in my garage".',
        ("OKAFOR's SMS account sent the message to FERRO on Mar 10",),
        (("item2", "dz_yellow"), ("item2", "contact:Dez"), ("item2", "dz_yellow2")),
        "The only copy is on Item 2, sent by +17735550164, which Item 2 saves as 'Dez': FERRO's "
        "cousin Desiree, whose next message is about the kids' boots. OKAFOR (+17735550176, "
        "saved on Item 2 as 'Desmond O') did not send it. Observed data rules out the stated "
        "sender.",
        "DEZ is OKAFOR's nickname (paragraph 2) and Item 1 saves OKAFOR as 'Dez', but on Item 2 "
        "'Dez' is another person. A reading that takes Item 2's 'Dez' for OKAFOR passes the "
        "sender; the sheet names OKAFOR.",
        (("item1", "contact:Dez"),),
    ),
    C(
        "C04",
        "communication",
        "affidavit",
        "supported",
        "second_number",
        "On the evening before the BELMONT SITE theft, HALLORAN, using the PREPAID, told the "
        'DRIVER to "bring the long ladder and both dollies".',
        (
            "The PREPAID sent the message to OKAFOR on the evening of Mar 6",
            "HALLORAN is the PREPAID's user (paragraph 3; tested in C08)",
        ),
        (("item3", "p_ladder"), ("item3", "p_new3")),
        "Item 3 holds the message from +13125550199 at 7:15 p.m. CST on Mar 6 (printed 7:15:22 "
        "PM(UTC-6)); the PREPAID had introduced itself to OKAFOR as 'new number, its hal'.",
        "HALLORAN's own number also texted the DRIVER that evening ('u still got my drill?'). A "
        "repair that names HALLORAN's phone accounts fails the sender check; the sheet names the "
        "PREPAID account.",
        (("item3", "ho_drill"),),
        "defined terms (BELMONT SITE, PREPAID, DRIVER), a relative date",
    ),
    C(
        "C05",
        "communication",
        "affidavit",
        "supported",
        "second_phone",
        "In the early hours after the theft, SUBJECT-1 sent the TARGET PHONE a Telegram message "
        'that read "all 9 at the unit. go to bed".',
        (
            "HALLORAN's Telegram account sent the message",
            "Item 2 (the TARGET PHONE) received it between midnight and 6 a.m. on Mar 8",
        ),
        (("item2", "hft_done"),),
        "Incoming on Item 2 at 1:47 a.m. CST on Mar 8, before the clocks went forward.",
        "The TARGET PHONE is Item 2 (paragraph 2), not HALLORAN's Item 1, which holds the sent "
        "copy and prints it as 7:47:10 AM(UTC+0). The sheet names Item 2.",
        (("item1", "hft_done"),),
        "defined terms (SUBJECT-1, TARGET PHONE), a relative time",
    ),
    C(
        "C06",
        "communication",
        "affidavit",
        "unproven",
        "similar_quote",
        'The next day, HAL warned the DRIVER by text message to "stay off the phone till tuesday".',
        ("HALLORAN's SMS account sent the message to OKAFOR on Mar 15",),
        (("item1", "ho_tmrw"), ("item1", "ho_tmrw2")),
        "No message with these words is on any phone. The nearest HALLORAN-OKAFOR exchange is on "
        "Mar 14 ('u around tmrw?'). The reports are curated, so not found does not mean not sent.",
        "That morning HALLORAN texted his foreman 'stay off the roof till tuesday, its icing up'. "
        "A repair that quotes those words passes the sender; the sheet quotes the claim's words.",
        (("item1", "bz_roof"),),
        "alias (HAL), a role (the DRIVER), a relative date ('the next day' after C31's Mar 14), "
        "indirect speech",
    ),
    # ------------------------------------------------------------ identity
    C(
        "C07",
        "identity",
        "plain",
        "supported",
        "contact_name",
        'Item 1 contains a contact saved as "Rocco" with the number +1 (773) 555-0187.',
        ("Item 1's contact list has an entry named 'Rocco' with +17735550187",),
        (("item1", "contact:Rocco"),),
        "Observed in Item 1's contacts. CW-1 also signs a text 'rocco' to HALLORAN.",
        "Item 3 also has a 'Rocco', with +17735550133 (Rocco Vitale). The sheet names Item 1.",
        (("item3", "contact:Rocco"),),
    ),
    C(
        "C08",
        "identity",
        "plain",
        "supported",
        "second_number",
        'Item 2 contains a contact saved as "Hal 2" with the number +1 (312) 555-0199.',
        ("Item 2's contact list has an entry named 'Hal 2' with +13125550199",),
        (("item2", "contact:Hal 2"), ("item2", "p_new2")),
        "Observed in Item 2's contacts; the number wrote 'new number, its hal' to FERRO.",
        "Item 2 also saves HALLORAN's main number, +13125550141, as 'Owen H'.",
        (("item2", "contact:Owen H"),),
    ),
    C(
        "C09",
        "identity",
        "plain",
        "unproven",
        "second_number",
        'Item 3 contains a contact saved as "Hal" with the number +1 (312) 555-0199.',
        ("Item 3's contact list has an entry named 'Hal' with +13125550199",),
        (("item3", "contact:Hal"), ("item3", "contact:H")),
        "Item 3's 'Hal' holds +13125550141 (HALLORAN's main number) and +13125550199 is saved "
        "as 'H'. No entry 'Hal' with 0199 is in the report; contact lists can be edited and the "
        "report is curated, so this is not shown, not ruled out.",
        "A reading that takes 'Hal' with the number it holds (0141) passes; the sheet names the "
        "PREPAID's number, as the claim does.",
        (("item3", "contact:Hal"),),
    ),
    C(
        "C10",
        "identity",
        "affidavit",
        "supported",
        "same_name",
        'The TARGET PHONE shows the DRIVER\'s Telegram account under two names, "dez" and, from '
        'mid-March, "D.O."; both names belong to one account.',
        ("On Telegram, 'dez' and 'D.O.' resolve to one account id (8204103)",),
        (("item2", "ft_plan"), ("item2", "ft_news")),
        "Every row of the conversation on Item 2 carries Telegram user id 8204103, OKAFOR's own "
        "account on Item 3; the name changes from 'dez' to 'D.O.' on Mar 15.",
        "Item 2 also saves FERRO's cousin Desiree's phone number as 'Dez'. The sheet names "
        "Telegram and Item 2.",
        (("item2", "contact:Dez"),),
        "defined terms (TARGET PHONE, DRIVER), an approximate date ('mid-March')",
    ),
    C(
        "C11",
        "identity",
        "affidavit",
        "supported",
        "second_phone",
        'SUBJECT-2 saved SUBJECT-3\'s number in the TARGET PHONE as "Desmond O".',
        ("Item 2's contact list has an entry named 'Desmond O' with +17735550176",),
        (("item2", "contact:Desmond O"),),
        "Observed in Item 2's contacts; +17735550176 is Item 3's own number.",
        "Item 1 saves OKAFOR as 'Dez', and Item 2's 'Dez' is someone else. The sheet names Item 2.",
        (("item1", "contact:Dez"), ("item2", "contact:Dez")),
        "defined terms (SUBJECT-2, SUBJECT-3, TARGET PHONE)",
    ),
    C(
        "C12",
        "identity",
        "affidavit",
        "contradicted",
        "second_number",
        'The BUYER wrote to FERRO from one Instagram account throughout, shown as both "kip.'
        'flips.chi" and "kipflips.chi".',
        ("On Instagram, 'kip.flips.chi' and 'kipflips.chi' are one account",),
        (("item2", "kp01"), ("item2", "kf_offer")),
        "They are two accounts: two usernames, two conversations with ferro.finds. Instagram "
        "usernames are the account's identifier, so one account cannot be both.",
        "One buyer may use two accounts; a reading that merges them by the person passes. The "
        "sheet names the two handles as the claim does.",
        (("item2", "kp01"),),
        "defined term (BUYER), a reference back to paragraph 3",
    ),
    # ------------------------------------------------------------ timing
    C(
        "C13",
        "timing",
        "plain",
        "supported",
        "near_window",
        "At about 3:20 a.m. on March 8, 2026, OKAFOR called HALLORAN; the call lasted about four "
        "minutes.",
        ("A call of about four minutes between OKAFOR and HALLORAN at about 3:20 a.m. CDT, Mar 8",),
        (("item3", "cl_0321"), ("item1", "cl_0321")),
        "Outgoing on Item 3 at 3:21:30 a.m. CDT, 245 s; incoming on Item 1.",
        "Item 3 prints it as 2:21:30 AM(UTC-6), an hour behind the phone after the clocks went "
        "forward; Item 1 prints 8:21:30 AM(UTC+0). A window built on either print misses it.",
        (("item3", "cl_0321"),),
    ),
    C(
        "C14",
        "timing",
        "plain",
        "supported",
        "near_window",
        "At about 10:40 p.m. on March 21, 2026, FERRO called OKAFOR; the call lasted about one "
        "minute.",
        ("A call of about one minute between FERRO and OKAFOR at about 10:40 p.m. CDT, Mar 21",),
        (("item2", "cl_2241"), ("item3", "cl_2241")),
        "Outgoing on Item 2 at 10:41:05 PM(UTC-5), 58 s.",
        "Item 3 prints that call as 9:41:05 PM(UTC-6), and an earlier FERRO call of 75 s at 9:41 "
        "p.m. CDT prints as 8:41:30 PM(UTC-6) on Item 3 and 9:41:30 PM(UTC-5) on Item 2. A window "
        "read off Item 3's print at 9:40 p.m. passes on the wrong call.",
        (("item3", "cl_2141"), ("item2", "cl_2141")),
    ),
    C(
        "C15",
        "timing",
        "plain",
        "contradicted",
        "near_window",
        'At 12:15 a.m. on March 19, 2026, HALLORAN texted OKAFOR "need u at 6 tmrw, bring gloves".',
        ("The message was sent at 12:15 a.m. on Mar 19, Chicago time",),
        (("item1", "ho_gloves"), ("item3", "ho_gloves")),
        "Sent at 7:15 p.m. CDT on Mar 18. Item 1 prints 3/19/2026 12:15:40 AM(UTC+0), which is "
        "where the claim's time comes from; every copy is outside the stated minute.",
        "The printed UTC value is the wrong window; the sheet names 12:15 a.m. Chicago time.",
        (("item1", "ho_gloves"),),
    ),
    C(
        "C16",
        "timing",
        "affidavit",
        "supported",
        "second_number",
        "Within half an hour after the KEDZIE YARD theft, the DRIVER called the PREPAID, a call "
        "of a little under three minutes.",
        ("A call of 150 to 179 s between OKAFOR and the PREPAID from 10:30 to 11 p.m., Mar 21",),
        (("item3", "cl_2258"),),
        "Outgoing on Item 3 to +13125550199 at 10:58:10 p.m. CDT, 165 s.",
        "At 11:10 p.m. the DRIVER called HALLORAN's main number for 170 s. A repair that names "
        "HALLORAN's phone accounts instead of the PREPAID passes on that call if its window is "
        "wider; the sheet names the PREPAID.",
        (("item3", "cl_2310"),),
        "defined terms (KEDZIE YARD, DRIVER, PREPAID), relative and approximate time, a duration "
        "in "
        "words",
    ),
    C(
        "C17",
        "timing",
        "affidavit",
        "supported",
        "near_window",
        "At about a quarter to midnight on the night before the SEARCH, FERRO sent HAL a WhatsApp "
        'message reading "they might come tmrw. clean the van".',
        ("FERRO sent the message to HALLORAN at about 11:45 p.m. on Mar 25",),
        (("item2", "hw_mid"),),
        "Outgoing on Item 2 at 11:46:12 PM(UTC-5) on Mar 25.",
        "Item 1 prints the copy as 3/26/2026 4:46:12 AM(UTC+0): the day of the SEARCH itself. "
        "The sheet names Mar 25, Chicago time.",
        (("item1", "hw_mid"),),
        "defined term (SEARCH), alias (HAL), a relative date, an approximate time in words",
    ),
    C(
        "C18",
        "timing",
        "affidavit",
        "unproven",
        "contact_name",
        "Within fifteen minutes of the KEDZIE YARD theft, SUBJECT-3 spoke by phone with CW-1.",
        ("A call between OKAFOR and +17735550187 from 10:15 to 10:45 p.m., Mar 21",),
        (("item3", "cl_vit"), ("item3", "contact:Rocco"), ("item1", "contact:Rocco")),
        "No call or message between OKAFOR and CW-1's number is on any phone. The only call in "
        "the window is to +17735550133, which Item 3 saves as 'Rocco'; Item 1 saves CW-1's "
        "number as 'Rocco'. The reports are curated, so not shown, not ruled out.",
        "A reading that takes Item 3's 'Rocco' for CW-1 passes on Rocco Vitale's call; the sheet "
        "names CW-1's number.",
        (("item3", "cl_vit"),),
        "defined terms (KEDZIE YARD, SUBJECT-3, CW-1), numbers in words",
        cross_device=True,
    ),
    # ------------------------------------------------------------ content meaning
    C(
        "C19",
        "content_meaning",
        "plain",
        "supported",
        "similar_quote",
        'On March 9, 2026, HALLORAN texted FERRO "the coils are under the blue tarp"; in that '
        'exchange, "the coils" meant copper wire.',
        (
            "HALLORAN's SMS account sent the message to FERRO on Mar 9",
            "In that exchange 'the coils' means copper wire",
        ),
        (("item1", "hf_coils"), ("item1", "hf_coils2"), ("item1", "hf_coils3")),
        "The exchange fixes the meaning: FERRO asks 'the copper ones?' and HALLORAN answers 'ya "
        "the copper, all 9'.",
        "That evening FERRO wrote to her sister 'the coils are under the porch' about something "
        "else. The sheet quotes the claimed message and names HALLORAN and FERRO.",
        (("item2", "ms_coils"),),
    ),
    C(
        "C20",
        "content_meaning",
        "plain",
        "unproven",
        "same_name",
        'On March 13, 2026, FERRO texted HALLORAN "bring the 3 heavy ones fri", referring to the '
        "generators taken from the BELMONT SITE.",
        (
            "FERRO's SMS account sent the message to HALLORAN on Mar 13",
            "'the 3 heavy ones' are generators taken from the BELMONT SITE",
        ),
        (("item2", "hf_heavy"), ("item2", "hf_heavy2")),
        "The message is observed. Nothing in the case says what the heavy ones are; two "
        "generators were taken, not three. The meaning is not fixed.",
        "Ninety minutes later FERRO asked the other Owen (her neighbour, 'Owen upstairs') to "
        "'bring the 2 heavy boxes down sat'. The sheet names HALLORAN.",
        (("item2", "pr_heavy"),),
    ),
    C(
        "C21",
        "content_meaning",
        "plain",
        "contradicted",
        "similar_quote",
        'On March 16, 2026, OKAFOR texted FERRO "that welder guy talks too much", warning her that '
        "a buyer was working with police.",
        (
            "OKAFOR's SMS account sent the message to FERRO on Mar 16",
            "The words warn that a buyer was working with police",
        ),
        (("item3", "fo_welder"), ("item2", "fo_welder")),
        "FERRO sent it to OKAFOR (outgoing on Item 2, incoming on Item 3); OKAFOR only answered "
        "'word'. Observed data rules out the stated sender; the meaning is not reached.",
        "The next day OKAFOR texted his tow contact 'that tow guy talks too much lol'. A repair "
        "that follows the data's sender (FERRO) passes; the sheet names OKAFOR, as the claim does.",
        (("item3", "gu_talk"),),
    ),
    C(
        "C22",
        "content_meaning",
        "affidavit",
        "supported",
        "similar_quote",
        'Two days later, HAL told the DRIVER on Telegram that the nine "blankets" were "at the '
        'unit", by which he meant the nine spools of wire, wrapped in moving blankets.',
        (
            "HALLORAN's Telegram account sent 'the 9 blankets are at the unit' to OKAFOR on Mar 11",
            "'blankets' means the spools wrapped in moving blankets",
        ),
        (("item3", "ht_blank"), ("item3", "ht_wrap"), ("item3", "ht_wrap2")),
        "On Mar 8 the DRIVER wrote 'wrap the spools in the moving blankets so they dont shine' "
        "and HAL answered 'ya blankets it is'; on Mar 11 HAL wrote 'the 9 blankets are at the "
        "unit'. The thread fixes the meaning.",
        "On Mar 12 OKAFOR's mother wrote 'i left the blankets at your unit, the grey ones'. The "
        "sheet quotes HAL's message.",
        (("item3", "mm_blank"),),
        "alias (HAL), a role (the DRIVER), a relative date ('two days later' after C19's Mar 9), "
        "paraphrase, a number in words",
    ),
    C(
        "C23",
        "content_meaning",
        "affidavit",
        "supported",
        "second_number",
        'Two days before the SEARCH, the BUYER offered FERRO "1.8 for the lot", which in that '
        "conversation meant $1,800 for four spools of copper wire.",
        (
            "kipflips.chi sent '1.8 for the lot, cash' to FERRO's ferro.finds on Mar 24",
            "'1.8 for the lot' means $1,800 for four spools of copper wire",
        ),
        (("item2", "kf_offer"), ("item2", "kf_lot"), ("item2", "kf_ok")),
        "FERRO's 'lot is 4 spools 12 gauge copper, 250 ft each' comes before the offer and her "
        "'1800 works. sat' after it. The conversation fixes the meaning.",
        "The same buyer also wrote to ferro.finds as kip.flips.chi, about a lamp. The BUYER is "
        "kipflips.chi (paragraph 3); the sheet names that account.",
        (("item2", "kp01"),),
        "defined terms (SEARCH, BUYER), a relative date, a number written as the message has it",
    ),
    C(
        "C24",
        "content_meaning",
        "affidavit",
        "unproven",
        "same_name",
        "On St. Patrick's Day, FERRO's sister wrote to her that \"owen dropped off the stuff\", "
        "meaning that HALLORAN had brought stolen tools to FERRO's home.",
        (
            "Marisol's WhatsApp sent the message to FERRO on Mar 17",
            "'owen' is HALLORAN and 'the stuff' is stolen tools",
        ),
        (("item2", "ms_owen"), ("item2", "contact:Owen H"), ("item2", "contact:Owen upstairs")),
        "The message is observed. Which Owen, and what stuff, is not fixed: FERRO's phone holds "
        "two Owens, and the other one (her upstairs neighbour) texted her that day 'dropped off "
        "ur package by the door'.",
        "A reading that takes 'owen' for HALLORAN without asking passes the meaning; the sheet "
        "leaves the meaning to the expert.",
        (("item2", "pr_pkg"),),
        "a date by its name, a role (FERRO's sister), indirect speech",
    ),
    # ------------------------------------------------------------ count
    C(
        "C25",
        "count",
        "plain",
        "supported",
        "near_window",
        "Between February 23 and March 1, 2026, Item 1 recorded 8 WhatsApp messages exchanged "
        "between HALLORAN and FERRO.",
        ("Item 1 holds exactly 8 WhatsApp messages between them Feb 23 to Mar 1, Chicago time",),
        tuple(("item1", f"hw0{i}") for i in range(1, 9)),
        "Eight rows on Item 1 on Chicago dates Feb 24 to Mar 1.",
        "Three messages on the evening of Feb 22 print as Feb 23 (UTC+0), and the two on the "
        "evening of Mar 1 print as Mar 2: a count on printed dates gives 9.",
        (("item1", "hw00a"), ("item1", "hw00b"), ("item1", "hw00c")),
    ),
    C(
        "C26",
        "count",
        "plain",
        "supported",
        "second_phone",
        "From March 9 through March 14, 2026, Item 3 recorded 6 Telegram messages exchanged "
        "between OKAFOR and HALLORAN.",
        ("Item 3 holds exactly 6 Telegram messages between them Mar 9 to Mar 14",),
        tuple(
            ("item3", k) for k in ("ht_10a", "ht_10b", "ht_blank", "ht_blank2", "ht_13a", "ht_13b")
        ),
        "Six rows on Item 3.",
        "Item 1 holds one more in the window (Mar 12, '?'), which Item 3's report does not: a "
        "count on Item 1 gives 7. The sheet names Item 3.",
        (("item1", "ht_12"),),
    ),
    C(
        "C27",
        "count",
        "plain",
        "contradicted",
        "near_window",
        "On March 21, 2026, Item 2 recorded 3 SMS messages exchanged between FERRO and OKAFOR.",
        ("Item 2 holds exactly 3 SMS messages between them on Mar 21, Chicago time",),
        tuple(("item2", f"fo_21{c}") for c in "abcde"),
        "Item 2 holds five on Mar 21 local time, so exactly three is ruled out.",
        "Two of the five were sent after 7 p.m. CDT and fall on Mar 22 in UTC; a UTC day counts "
        "three and passes. The sheet names the Chicago day.",
        (("item2", "fo_21d"), ("item2", "fo_21e")),
    ),
    C(
        "C28",
        "count",
        "affidavit",
        "supported",
        "second_number",
        "During the work week before the BELMONT SITE theft, Monday through Friday, the PREPAID "
        "and "
        "the DRIVER exchanged eleven text messages, all recorded on SUBJECT-3's phone.",
        ("Item 3 holds exactly 11 SMS messages between the PREPAID and OKAFOR, Mar 2 to Mar 6",),
        tuple(
            ("item3", k)
            for k in ("p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08", "p_ladder", "p10")
        )
        + (("item3", "p11"),),
        "Eleven rows on Item 3 from Monday Mar 2 through Friday Mar 6.",
        "HALLORAN's own number exchanged six texts with the DRIVER that week; a repair that names "
        "HALLORAN's phone accounts counts those. The PREPAID's next text is on Saturday Mar 7, "
        "outside the work week. The sheet names the PREPAID and Item 3.",
        (("item3", "ho_meet"), ("item3", "ho_drill"), ("item3", "p_alley")),
        "defined terms (BELMONT SITE, PREPAID, DRIVER, SUBJECT-3), a relative range, a number in "
        "words",
    ),
    C(
        "C29",
        "count",
        "affidavit",
        "contradicted",
        "second_phone",
        "Between March 16 and March 20, 2026, SUBJECT-2 and HAL exchanged only four Telegram "
        "messages on the TARGET PHONE.",
        ("Item 2 holds exactly 4 Telegram messages between FERRO and HALLORAN, Mar 16 to Mar 20",),
        tuple(
            ("item2", k) for k in ("hft_16a", "hft_16b", "hft_18a", "hft_18b", "hft_19a", "hft_19b")
        ),
        "Item 2 holds six, so 'only four' is ruled out.",
        "Item 1's report holds only four of them (not the two on Mar 18): a count on HALLORAN's "
        "phone passes. The TARGET PHONE is Item 2.",
        tuple(("item1", k) for k in ("hft_16a", "hft_16b", "hft_19a", "hft_19b")),
        "defined terms (SUBJECT-2, TARGET PHONE), alias (HAL), a number in words",
    ),
    C(
        "C30",
        "count",
        "affidavit",
        "unproven",
        "near_window",
        "On the night of the BELMONT SITE theft, between 11 p.m. and 3 a.m., SUBJECT-1 and "
        "SUBJECT-2 exchanged at least a dozen text messages, as recorded on Item 1.",
        ("Item 1 holds at least 12 SMS messages between them from 11 p.m. Mar 7 to 3 a.m. Mar 8",),
        tuple(("item1", f"hn0{i}") for i in range(1, 10)),
        "11 p.m. to 3 a.m. that night is three hours, because the clocks went forward at 2 a.m. "
        "Item 1 holds nine texts in it. Fewer than claimed is not a contradiction (curated "
        "report), "
        "so unproven.",
        "Three more texts between 3 and 4 a.m. CDT fall inside a window that forgets the clock "
        "change (05:00 to 09:00 UTC) and make twelve. The sheet names wall-clock 11 p.m. to 3 a.m.",
        (("item1", "hn10"), ("item1", "hn11"), ("item1", "hn12")),
        "defined terms (BELMONT SITE, SUBJECT-1, SUBJECT-2), a number in words",
    ),
    # ------------------------------------------------------------ absence
    C(
        "C31",
        "absence",
        "plain",
        "contradicted",
        "near_window",
        "HALLORAN and OKAFOR had no contact of any kind on March 14, 2026.",
        ("No message or call between them on Mar 14, Chicago time",),
        (("item1", "ho_tmrw"), ("item3", "ho_tmrw")),
        "HALLORAN texted OKAFOR 'u around tmrw?' at 9:30 p.m. CDT on Mar 14.",
        "Item 1 prints it as 3/15/2026 2:30:18 AM(UTC+0), and nothing else between them falls on "
        "Mar 14 in UTC: a UTC day finds no contact. The sheet names the Chicago day.",
        (("item1", "ho_tmrw"),),
    ),
    C(
        "C32",
        "absence",
        "plain",
        "contradicted",
        "second_number",
        "FERRO and HALLORAN had no contact of any kind between March 27 and March 29, 2026.",
        (
            "No contact between FERRO and HALLORAN's phone accounts, Mar 27 to 29",
            "No contact between FERRO and the PREPAID, HALLORAN's second number, Mar 27 to 29",
        ),
        (("item2", "p_me"), ("item2", "p_me2"), ("item2", "contact:Hal 2"), ("item2", "p_new2")),
        "HALLORAN's own accounts are silent, but the PREPAID wrote to FERRO on Mar 28 'its me. "
        "dont use the other number for a while', and she answered. By paragraph 3 the PREPAID is "
        "HALLORAN's.",
        "A reading that takes HALLORAN as his phone's accounts only finds none (unproven). The "
        "sheet names both his phone accounts and the PREPAID.",
        (("item2", "p_me"),),
    ),
    C(
        "C33",
        "absence",
        "plain",
        "unproven",
        "contact_name",
        "OKAFOR and CW-1 had no contact of any kind between March 1 and March 31, 2026.",
        ("No message or call between OKAFOR and +17735550187 in March",),
        (("item3", "contact:Rocco"), ("item1", "contact:Rocco")),
        "No record between OKAFOR and CW-1's number is on any phone; the reports are curated, so "
        "the absence cannot be shown.",
        "OKAFOR has calls and texts all month with a 'Rocco' (Item 3), who is Rocco Vitale at "
        "+17735550133; Item 1 saves CW-1's number as 'Rocco'. Taking one Rocco for the other "
        "contradicts the claim wrongly. The sheet names CW-1's number.",
        (("item3", "cl_vit"),),
        cross_device=True,
    ),
    C(
        "C34",
        "absence",
        "affidavit",
        "unproven",
        "near_window",
        "In the first hour after the clocks went forward that night, the DRIVER and SUBJECT-2 had "
        "no contact.",
        ("No message or call between OKAFOR and FERRO from 3 to 4 a.m. CDT, Mar 8",),
        (("item3", "cl_0412"), ("item2", "ft_load")),
        "Nothing between them from 3 to 4 a.m. CDT; the nearest records are the 12:52 a.m. "
        "Telegram and a 4:12 a.m. call. Curated reports cannot show an absence, so unproven.",
        "Item 3 prints the 4:12 a.m. call as 3:12:40 AM(UTC-6), inside the hour on its face; a "
        "window read off Item 3's print contradicts the claim wrongly.",
        (("item3", "cl_0412"),),
        "a role (the DRIVER), a defined term (SUBJECT-2), a time given by an event",
    ),
    C(
        "C35",
        "absence",
        "affidavit",
        "contradicted",
        "same_name",
        "In the days leading up to the SEARCH, from Monday through Wednesday, FERRO had no contact "
        "with DEZ.",
        ("No message or call between FERRO and OKAFOR, Mar 23 to 25",),
        (("item2", "fw_600"), ("item2", "fw_6002"), ("item2", "fw_thurs"), ("item2", "fw_thurs2")),
        "FERRO and OKAFOR exchanged WhatsApp messages on Mar 23 and Mar 24.",
        "DEZ is OKAFOR (paragraph 2). Item 2's 'Dez' is FERRO's cousin, who has no contact with "
        "her those days: that reading finds none. The sheet names OKAFOR.",
        (("item2", "contact:Dez"),),
        "alias (DEZ), a defined term (SEARCH), relative weekdays",
    ),
    C(
        "C36",
        "absence",
        "affidavit",
        "unproven",
        "second_phone",
        "After the SEARCH, SUBJECT-1's phone shows no contact with SUBJECT-3 for the rest of "
        "March.",
        ("Item 1 holds no message or call between HALLORAN and OKAFOR, Mar 27 to 31",),
        (("item3", "ho_good"),),
        "Item 1's report holds none, but a curated report cannot show that the phone held none, so "
        "unproven. Item 3 holds a text from OKAFOR to HALLORAN on Mar 29 that Item 1's report "
        "does not.",
        "The claim is about SUBJECT-1's phone. A repair with no phone named finds the Item 3 copy "
        "and contradicts it; the sheet names Item 1.",
        (("item3", "ho_good"),),
        "defined terms (SEARCH, SUBJECT-1, SUBJECT-3), a relative range",
    ),
    # ------------------------------------------------------------ role
    C(
        "C37",
        "role",
        "plain",
        "supported",
        "second_number",
        "FERRO handled the sale of the copper wire to the Instagram user kipflips.chi.",
        (
            "FERRO's ferro.finds wrote the terms and the acceptance to kipflips.chi",
            "That makes FERRO the one who handled the sale",
        ),
        (("item2", "kf_lot"), ("item2", "kf_offer"), ("item2", "kf_ok")),
        "ferro.finds set out the lot ('4 spools 12 gauge copper, 250 ft each') and accepted the "
        "offer ('1800 works. sat'). The conversation shows FERRO's account handling it.",
        "The buyer's other account, kip.flips.chi, bought a lamp from ferro.finds; the sheet "
        "names kipflips.chi.",
        (("item2", "kp02"),),
    ),
    C(
        "C38",
        "role",
        "plain",
        "contradicted",
        "same_name",
        'On March 20, 2026, OKAFOR set the pickup time, texting FERRO "pickup 10:15, not before".',
        (
            "OKAFOR's SMS account sent 'pickup 10:15, not before' to FERRO on Mar 20",
            "OKAFOR set the time",
        ),
        (("item2", "fo_pickup"), ("item3", "fo_pickup")),
        "FERRO sent it to OKAFOR, who answered 'k'. Observed data rules out the stated sender.",
        "That morning Item 2's 'Dez' (FERRO's cousin) asked 'pickup at 3:15 today?'. Taking that "
        "'Dez' for OKAFOR confuses two people; the sheet names OKAFOR.",
        (("item2", "dz_pick"),),
    ),
    C(
        "C39",
        "role",
        "plain",
        "unproven",
        "none",
        "HALLORAN recruited OKAFOR to drive for him.",
        ("HALLORAN recruited OKAFOR",),
        (("item1", "ho_driver"), ("item1", "ho_driver2")),
        "The record shows OKAFOR offering himself ('u still need a driver? i can do weekends') "
        "and HALLORAN answering 'maybe. talk sat'. Who recruited whom is interpretation.",
    ),
    C(
        "C40",
        "role",
        "affidavit",
        "supported",
        "same_name",
        "On the night of the KEDZIE YARD theft, DEZ served as the DRIVER, telling his girlfriend "
        'that evening that he was "driving for nadia tonight".',
        (
            "OKAFOR's SMS account sent 'driving for nadia tonight, back late' to Tash on Mar 21",
            "OKAFOR drove that night",
        ),
        (("item3", "tg_drive"),),
        "OKAFOR wrote to his girlfriend at 7:40 p.m. CDT on Mar 21 'driving for nadia tonight, "
        "back late'. His own words fix the role.",
        "DEZ is OKAFOR (paragraph 2); Item 2's 'Dez' is someone else. The sheet names OKAFOR.",
        (("item2", "contact:Dez"),),
        "alias (DEZ), defined terms (KEDZIE YARD, DRIVER), a role (his girlfriend), indirect "
        "speech",
    ),
    C(
        "C41",
        "role",
        "affidavit",
        "contradicted",
        "similar_quote",
        'SUBJECT-2 decided where the spools would be kept that night, sending HAL to "the unit on '
        'pulaski".',
        (
            "FERRO sent HALLORAN the words 'the unit on pulaski'",
            "FERRO chose where the spools were kept",
        ),
        (("item1", "hf_pul"), ("item2", "hf_pul")),
        "HALLORAN wrote 'taking them to the unit on pulaski after' to FERRO, who answered 'ok'. "
        "No copy came from FERRO. Observed data rules out the stated sender.",
        "FERRO wrote to her sister 'moms boxes are at the pulaski unit' (other words, another "
        "thread); the sheet quotes the claim's words.",
        (("item2", "ms_pul"),),
        "defined terms (SUBJECT-2), alias (HAL), 'that night' referring back, paraphrase",
    ),
    C(
        "C42",
        "role",
        "affidavit",
        "unproven",
        "similar_quote",
        "In the hours before the BELMONT SITE theft, HAL acted as a lookout, reporting by text "
        "that "
        "the site was clear.",
        ("HALLORAN acted as a lookout and reported the site clear",),
        (("item1", "bz_clear"), ("item1", "contact:Benny NGE")),
        "The only such text is HALLORAN's 'site is clear, everyone left at 5' at 6:40 p.m., to "
        "his foreman ('Benny NGE'), not to FERRO or the DRIVER. It does not show a lookout.",
        "A repair that quotes the foreman text passes a sender check; the sheet has only the role "
        "row, which no check tests.",
        (("item1", "bz_clear"),),
        "defined term (BELMONT SITE), alias (HAL), paraphrase, a relative time",
    ),
    # ------------------------------------------------------------ event
    C(
        "C43",
        "event",
        "plain",
        "supported",
        "similar_quote",
        "On March 3, 2026, HALLORAN and OKAFOR arranged by text to meet at 8 p.m. on Thursday, "
        "March 5, 2026, behind the laundromat on Fullerton.",
        (
            "HALLORAN proposed the meeting by SMS on Mar 3",
            "'thursday' sent on Tuesday Mar 3 is Mar 5",
            "OKAFOR agreed",
        ),
        (("item1", "ho_meet"), ("item1", "ho_meet2"), ("item3", "ho_meet")),
        "'meet behind the laundromat on fullerton thursday 8pm' from HALLORAN, 'ok' from OKAFOR.",
        "The next day OKAFOR texted his tow contact 'leave it behind the laundromat on "
        "fullerton'; the sheet quotes HALLORAN's message.",
        (("item3", "gu_laund"),),
    ),
    C(
        "C44",
        "event",
        "plain",
        "supported",
        "same_name",
        "On March 23, 2026, FERRO asked HALLORAN by text to move the welder out of her garage, and "
        "HALLORAN agreed.",
        ("FERRO asked by SMS on Mar 23", "HALLORAN answered that he would"),
        (("item2", "hf_weld"), ("item2", "hf_weld2")),
        "'need the welder out of my garage by tmrw' from FERRO, 'ok ill grab it tonight' from "
        "HALLORAN.",
        "That morning FERRO asked the other Owen 'need the bike out of the hallway by tmrw'.",
        (("item2", "pr_bike"),),
    ),
    C(
        "C45",
        "event",
        "plain",
        "unproven",
        "same_name",
        "On March 12, 2026, FERRO and OKAFOR spoke by phone for about ten minutes.",
        ("A call of about ten minutes between FERRO and OKAFOR on Mar 12",),
        (("item2", "cl_0312"), ("item2", "cl_dz"), ("item2", "contact:Dez")),
        "Their only call that day lasted 45 s. The ten-minute call (612 s) is with Item 2's "
        "'Dez', FERRO's cousin. No such call between them is in the reports; not shown.",
        "Taking Item 2's 'Dez' for DEZ (OKAFOR) passes on the cousin's call; the sheet names "
        "OKAFOR.",
        (("item2", "cl_dz"),),
    ),
    C(
        "C46",
        "event",
        "affidavit",
        "supported",
        "near_window",
        "Shortly before 5 a.m. the morning after the theft, the DRIVER let SUBJECT-2 know on "
        'Telegram that the van was "back at gus".',
        ("OKAFOR's Telegram sent 'home. van is back at gus' to FERRO, 4:30 to 5 a.m., Mar 8",),
        (("item2", "ft_gus"), ("item3", "ft_gus")),
        "Outgoing on Item 3 at 4:48 a.m. CDT, incoming on Item 2 (printed 4:48:26 AM(UTC-5)).",
        "Item 3 prints it as 3:48:26 AM(UTC-6), outside the stated time on its face.",
        (("item3", "ft_gus"),),
        "a role (the DRIVER), defined term (SUBJECT-2), a relative time, indirect speech",
    ),
    C(
        "C47",
        "event",
        "affidavit",
        "supported",
        "similar_quote",
        "Two days after the KEDZIE YARD theft, FERRO paid the DRIVER, telling him by WhatsApp that "
        '"ur 600 is in the envelope under the mat".',
        (
            "FERRO's WhatsApp sent the message to OKAFOR on Mar 23",
            "The money was left and he got it",
        ),
        (("item2", "fw_600"), ("item2", "fw_6002"), ("item3", "fw_600")),
        "'ur 600 is in the envelope under the mat' from FERRO, and 'got it, thx' from OKAFOR half "
        "an hour later.",
        "That evening FERRO wrote to her sister 'the 60 i owe u is in the envelope by the door'.",
        (("item2", "ms_60"),),
        "defined terms (KEDZIE YARD, DRIVER), a relative date, indirect speech",
    ),
    C(
        "C48",
        "event",
        "affidavit",
        "contradicted",
        "second_phone",
        "After the SEARCH, FERRO cut off all contact with the DRIVER for the rest of the month.",
        ("No message or call between FERRO and OKAFOR, Mar 27 to 31",),
        (("item3", "fw_house"),),
        "On Mar 28 FERRO wrote to OKAFOR on WhatsApp 'u ok? dont come by the house'; Item 3 holds "
        "it. Contact was not cut off.",
        "Item 2's report does not hold the message: a repair limited to FERRO's phone finds none. "
        "The sheet searches both phones.",
        (("item3", "fw_house"),),
        "defined terms (SEARCH, DRIVER), a relative range",
    ),
)

# One line per claim for the signing sheet.
SUMMARY: dict[str, str] = {
    "C01": "Sent 8:12 p.m. CST Feb 18; Item 1 prints Feb 19 (UTC+0).",
    "C02": "Observed on Items 2 and 3, Mar 4.",
    "C03": "Sent by Item 2's 'Dez' (FERRO's cousin, +17735550164), not OKAFOR.",
    "C04": "The PREPAID's text on Item 3, 7:15 p.m. Mar 6.",
    "C05": "Item 2 (the TARGET PHONE) received it at 1:47 a.m. CST Mar 8.",
    "C06": "No such text anywhere; the foreman got 'stay off the roof till tuesday'.",
    "C07": "Item 1's 'Rocco' holds +17735550187; Item 3's 'Rocco' is another number.",
    "C08": "Item 2's 'Hal 2' holds +13125550199.",
    "C09": "Item 3's 'Hal' holds 0141; 0199 is saved as 'H'. Not shown (contact lists edit).",
    "C10": "One Telegram id, 8204103, renamed 'dez' -> 'D.O.' on Mar 15.",
    "C11": "Item 2's 'Desmond O' holds +17735550176.",
    "C12": "kip.flips.chi and kipflips.chi are two accounts.",
    "C13": "3:21 a.m. CDT, 245 s; Item 3 prints 2:21 AM(UTC-6).",
    "C14": "10:41 p.m. CDT, 58 s; the 9:41 p.m. call is a decoy.",
    "C15": "Sent 7:15 p.m. Mar 18; 12:15 AM is the printed UTC value.",
    "C16": "10:58 p.m., 165 s, to the PREPAID (Item 3).",
    "C17": "11:46 p.m. Mar 25; Item 1 prints Mar 26.",
    "C18": "No CW-1 call; the 10:36 p.m. call is to Item 3's 'Rocco' (Vitale).",
    "C19": "'the copper ones?' / 'ya the copper, all 9' fix the meaning.",
    "C20": "Observed; 'heavy ones' is not fixed (and two generators, not three).",
    "C21": "FERRO sent it, not OKAFOR.",
    "C22": "Mar 8: 'wrap the spools in the moving blankets' fixes 'blankets'.",
    "C23": "'lot is 4 spools ...' and '1800 works' fix '1.8'.",
    "C24": "Two Owens on Item 2; 'the stuff' not fixed.",
    "C25": "8 on Chicago dates; printed dates give 9.",
    "C26": "6 on Item 3; Item 1 has 7.",
    "C27": "5 on Mar 21 local; a UTC day gives 3.",
    "C28": "11 PREPAID-DRIVER texts Mar 2-6 on Item 3.",
    "C29": "6 on Item 2; Item 1 shows 4.",
    "C30": "9 in 11 p.m.-3 a.m. (three hours, DST); 12 only if the jump is forgotten.",
    "C31": "9:30 p.m. CDT Mar 14 text; Item 1 prints Mar 15.",
    "C32": "The PREPAID wrote to FERRO on Mar 28.",
    "C33": "No CW-1 record; Item 3's 'Rocco' is Vitale. Curated, so not shown.",
    "C34": "None 3-4 a.m. CDT; Item 3 prints the 4:12 call as 3:12.",
    "C35": "FERRO-OKAFOR WhatsApp on Mar 23 and 24.",
    "C36": "None on Item 1 (curated); Item 3 holds a Mar 29 text.",
    "C37": "ferro.finds set the terms and accepted the offer.",
    "C38": "FERRO sent 'pickup 10:15, not before'.",
    "C39": "OKAFOR offered himself; recruitment is interpretation.",
    "C40": "His own text: 'driving for nadia tonight, back late'.",
    "C41": "HALLORAN wrote 'the unit on pulaski', not FERRO.",
    "C42": "'site is clear' went to his foreman; no lookout shown.",
    "C43": "Proposal and 'ok' on Mar 3; Thursday is Mar 5.",
    "C44": "Request and 'ok ill grab it tonight' on Mar 23.",
    "C45": "Only a 45 s call; the 10-minute call is the cousin's.",
    "C46": "4:48 a.m. CDT; Item 3 prints 3:48 AM(UTC-6).",
    "C47": "Message and 'got it, thx' on Mar 23.",
    "C48": "FERRO's Mar 28 WhatsApp, on Item 3 only.",
}

# Affidavit layout: (page, paragraph parts). A part is plain text or a claim id. Paragraphs are
# numbered from 1 in this order.
AFFIDAVIT: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            "I, Investigator R. Calloway of the Lakeshore Regional Property Crimes Unit (a "
            "fictional agency), make this affidavit from my training, experience and review of "
            "the evidence described below.",
        ),
    ),
    (
        1,
        (
            "This affidavit is based on forensic extraction reports for three phones. Item 1 is an "
            'Apple iPhone 15 seized from OWEN HALLORAN ("HALLORAN" or "SUBJECT-1"), known to '
            'his associates as "HAL". Item 2 (the "TARGET PHONE") is a Google Pixel 8 seized from '
            'NADIA FERRO ("FERRO" or "SUBJECT-2"). Item 3 is a Motorola moto g seized from '
            'DESMOND OKAFOR ("OKAFOR" or "SUBJECT-3"), known as "DEZ", who drove for HALLORAN and '
            'FERRO (the "DRIVER") during the events described below.',
        ),
    ),
    (
        1,
        (
            'A cooperating witness ("CW-1") used the phone number +1 (773) 555-0187. HALLORAN '
            'also used a prepaid phone number, +1 (312) 555-0199 (the "PREPAID"). An Instagram '
            "user who wrote to FERRO's resale account as kipflips.chi is referred to below as the "
            '"BUYER".',
        ),
    ),
    (
        1,
        (
            "On the night of Saturday, March 7, 2026, into the early hours of Sunday, March 8, "
            "2026 (the night the clocks went forward), nine spools of copper wire, two generators "
            "and a pallet of power tools were taken from a construction site at 4400 West Belmont "
            'Avenue (the "BELMONT SITE").',
        ),
    ),
    (
        1,
        (
            "On Saturday, March 21, 2026, at about 10:30 p.m., a towable light tower and a welder "
            'were taken from an equipment rental yard on Kedzie Avenue (the "KEDZIE YARD").',
        ),
    ),
    (
        1,
        (
            "On Thursday, March 26, 2026, officers searched FERRO's storage unit on North Pulaski "
            'Road (the "SEARCH") and recovered four spools of copper wire.',
        ),
    ),
    (1, ("All times in this affidavit are Chicago time.",)),
    (2, ("C39", "C01", "C25")),
    (2, ("C07", "C08", "C09", "C11")),
    (2, ("C43", "C02", "C28", "C04")),
    (2, ("C42", "C41", "C30", "C05", "C13", "C34", "C46")),
    (3, ("C19", "C22", "C26", "C03")),
    (3, ("C45", "C20", "C31", "C06", "C10")),
    (3, ("C21", "C29", "C24", "C15")),
    (3, ("C38", "C40", "C14", "C18", "C16", "C27")),
    (4, ("C47", "C44", "C35", "C23", "C37", "C12", "C17")),
    (4, ("C32", "C36", "C48", "C33")),
    (
        4,
        (
            "Based on the above, I believe there is probable cause that HALLORAN, FERRO and OKAFOR "
            "took part in the thefts described above and in the sale of the stolen property.",
        ),
    ),
)


# ---------------------------------------------------------------- DRAFT assumption sheet

HAL, FER, OKA = "person:halloran", "person:ferro", "person:okafor"
ITEM1, ITEM2, ITEM3 = "dev:item1", "dev:item2", "dev:item3"
PRE2 = "acct:item2:SMS:+13125550199"  # the PREPAID, as Item 2 logs it
PRE3 = "acct:item3:SMS:+13125550199"  # the PREPAID, as Item 3 logs it
CW1 = "acct:item1:SMS:+17735550187"  # CW-1's number (paragraph 3), as Item 1 logs it
OKA_ON_ITEM2 = "acct:item2:SMS:+17735550176"
KIP2 = "acct:item2:Instagram:kipflips.chi"  # the BUYER
MARI = "acct:item2:WhatsApp:13125550107@s.whatsapp.net"  # FERRO's sister
TASH = "acct:item3:SMS:+17735550145"  # OKAFOR's girlfriend

Expect = Literal["pass", "fail", "inconclusive"] | None


def window(start: str, end_exclusive: str, raw: str, tz: str = TZ) -> dict[str, str]:
    """Wall-clock [start, end_exclusive) in tz -> the contract's inclusive UTC TimeWindow.

    The same arithmetic as core.audit.assumptions.local_window and the case03 sheet.
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


Q01 = "need the big van sat, 6am"
Q02 = "address is 2210 n kildare, side gate"
Q03 = "the yellow ones are in my garage"
Q04 = "bring the long ladder and both dollies"
Q05 = "all 9 at the unit. go to bed"
Q06 = "stay off the phone till tuesday"
Q15 = "need u at 6 tmrw, bring gloves"
Q17 = "they might come tmrw. clean the van"
Q19 = "the coils are under the blue tarp"
Q20 = "bring the 3 heavy ones fri"
Q21 = "that welder guy talks too much"
Q22 = "the 9 blankets are at the unit"
Q23 = "1.8 for the lot"
Q24 = "owen dropped off the stuff"
Q37_LOT = "lot is 4 spools 12 gauge copper, 250 ft each"
Q37_OK = "1800 works. sat"
Q38 = "pickup 10:15, not before"
Q40 = "driving for nadia tonight"
Q41 = "the unit on pulaski"
Q43 = "meet behind the laundromat on fullerton thursday 8pm"
Q44_ASK = "need the welder out of my garage by tmrw"
Q44_OK = "ok ill grab it tonight"
Q46 = "back at gus"
Q47 = "ur 600 is in the envelope under the mat"

KEDZIE_NIGHT = window(
    "2026-03-21T17:00:00", "2026-03-22T06:00:00", "On the night of the KEDZIE YARD theft"
)
AFTER_SEARCH = window(
    "2026-03-27", "2026-04-01", "After the SEARCH, for the rest of March (March 27 to 31, 2026)"
)

SHEET: tuple[ClaimSpec, ...] = (
    # ------------------------------------------------------------ communication
    ClaimSpec(
        "C01",
        (
            A(
                "sender",
                P(quoted_text=Q01, person_ids=[HAL], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q01,
                    person_ids=[HAL, FER],
                    channels=["SMS"],
                    window=day("2026-02-18", "On February 18, 2026"),
                ),
                "pass",
                "8:12 p.m. CST Feb 18; Item 1 prints 2/19 2:12:40 AM(UTC+0).",
            ),
        ),
    ),
    ClaimSpec(
        "C02",
        (
            A(
                "sender",
                P(quoted_text=Q02, person_ids=[FER], channels=["WhatsApp"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q02,
                    person_ids=[FER, OKA],
                    channels=["WhatsApp"],
                    window=day("2026-03-04", "On March 4, 2026"),
                ),
                "pass",
                "2:40 p.m. CST Mar 4.",
            ),
        ),
    ),
    ClaimSpec(
        "C03",
        (
            A(
                "sender",
                P(quoted_text=Q03, person_ids=[OKA], channels=["SMS"]),
                "fail",
                "The one copy came from +17735550164, Item 2's 'Dez' (FERRO's cousin), not from "
                "OKAFOR's +17735550176.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q03,
                    channels=["SMS"],
                    device_ids=[ITEM2],
                    window=day("2026-03-10", "On March 10, 2026"),
                ),
                "pass",
                "11:05 a.m. CDT Mar 10, on Item 2.",
            ),
        ),
        gaps=("That FERRO received it is shown by the time row's phone (Item 2), not by a party.",),
    ),
    ClaimSpec(
        "C04",
        (
            A(
                "sender",
                P(quoted_text=Q04, account_ids=[PRE3], channels=["SMS"]),
                "pass",
                "Incoming on Item 3 from the PREPAID (paragraph 3).",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q04,
                    person_ids=[OKA],
                    account_ids=[PRE3],
                    channels=["SMS"],
                    window=window(
                        "2026-03-06T17:00:00",
                        "2026-03-07T00:00:00",
                        "On the evening before the BELMONT SITE theft (March 6, 2026, 5 p.m. to "
                        "midnight)",
                    ),
                ),
                "pass",
                "7:15 p.m. CST Mar 6 (printed 7:15:22 PM(UTC-6)).",
            ),
            A(
                "authorship",
                P(quoted_text=Q04, person_ids=[HAL], account_ids=[PRE3], channels=["SMS"]),
                None,
                "That HALLORAN typed it rests on paragraph 3's PREPAID; tested as a contact in "
                "C08.",
                is_core=False,
            ),
        ),
    ),
    ClaimSpec(
        "C05",
        (
            A(
                "sender",
                P(quoted_text=Q05, person_ids=[HAL], channels=["Telegram"]),
                "pass",
                "SUBJECT-1 is HALLORAN; his Telegram sent it.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q05,
                    person_ids=[HAL, FER],
                    device_ids=[ITEM2],
                    channels=["Telegram"],
                    window=window(
                        "2026-03-08T00:00:00",
                        "2026-03-08T06:00:00",
                        "In the early hours after the theft (March 8, 2026, midnight to 6 a.m.)",
                    ),
                ),
                "pass",
                "The TARGET PHONE is Item 2 (paragraph 2). 1:47 a.m. CST Mar 8.",
            ),
        ),
    ),
    ClaimSpec(
        "C06",
        (
            A(
                "sender",
                P(quoted_text=Q06, person_ids=[HAL], channels=["SMS"]),
                "inconclusive",
                "No message with these words on any phone.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q06,
                    person_ids=[HAL, OKA],
                    channels=["SMS"],
                    window=day("2026-03-15", "The next day (Sunday, March 15, 2026)"),
                ),
                "inconclusive",
                "'The next day' follows C31's March 14. Not found.",
            ),
        ),
    ),
    # ------------------------------------------------------------ identity
    ClaimSpec(
        "C07",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM1], quoted_text="Rocco", account_ids=[CW1]),
                "pass",
                "Item 1's 'Rocco' holds +17735550187.",
            ),
        ),
    ),
    ClaimSpec(
        "C08",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM2], quoted_text="Hal 2", account_ids=[PRE2]),
                "pass",
                "Item 2's 'Hal 2' holds +13125550199.",
            ),
        ),
    ),
    ClaimSpec(
        "C09",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM3], quoted_text="Hal", account_ids=[PRE3]),
                "inconclusive",
                "Item 3's 'Hal' holds +13125550141; a missing entry is never a fail.",
            ),
        ),
    ),
    ClaimSpec(
        "C10",
        (
            A(
                "same_account",
                P(channels=["Telegram"], handles=["dez", "D.O."], device_ids=[ITEM2]),
                "pass",
                "Both names resolve to Telegram user id 8204103 (OKAFOR's own account on Item 3).",
            ),
        ),
    ),
    ClaimSpec(
        "C11",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM2], quoted_text="Desmond O", account_ids=[OKA_ON_ITEM2]),
                "pass",
                "The TARGET PHONE is Item 2.",
            ),
        ),
    ),
    ClaimSpec(
        "C12",
        (
            A(
                "same_account",
                P(
                    channels=["Instagram"],
                    handles=["kip.flips.chi", "kipflips.chi"],
                    device_ids=[ITEM2],
                ),
                "fail",
                "Two usernames, two accounts.",
            ),
        ),
    ),
    # ------------------------------------------------------------ timing
    ClaimSpec(
        "C13",
        (
            A(
                "record_time",
                P(
                    person_ids=[OKA, HAL],
                    channels=["call"],
                    duration_s=[210, 270],
                    window=window(
                        "2026-03-08T03:12:00",
                        "2026-03-08T03:29:00",
                        "At about 3:20 a.m. on March 8, 2026",
                    ),
                ),
                "pass",
                "3:21:30 a.m. CDT, 245 s. Item 3 prints 2:21:30 AM(UTC-6).",
            ),
        ),
        gaps=(
            "No template says who placed a call; Item 3 logs it as outgoing, as the claim says.",
        ),
    ),
    ClaimSpec(
        "C14",
        (
            A(
                "record_time",
                P(
                    person_ids=[FER, OKA],
                    channels=["call"],
                    duration_s=[40, 80],
                    window=window(
                        "2026-03-21T22:32:00",
                        "2026-03-21T22:49:00",
                        "At about 10:40 p.m. on March 21, 2026",
                    ),
                ),
                "pass",
                "10:41:05 p.m. CDT, 58 s. The 9:41 p.m. call (75 s) is outside.",
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
                P(quoted_text=Q15, person_ids=[HAL], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q15,
                    person_ids=[HAL, OKA],
                    channels=["SMS"],
                    window=window(
                        "2026-03-19T00:15:00",
                        "2026-03-19T00:16:00",
                        "At 12:15 a.m. on March 19, 2026",
                    ),
                ),
                "fail",
                "Sent 7:15:40 p.m. CDT Mar 18; 12:15:40 AM is Item 1's UTC+0 print.",
            ),
        ),
    ),
    ClaimSpec(
        "C16",
        (
            A(
                "record_time",
                P(
                    person_ids=[OKA],
                    account_ids=[PRE3],
                    channels=["call"],
                    duration_s=[150, 179],
                    window=window(
                        "2026-03-21T22:30:00",
                        "2026-03-21T23:00:00",
                        "Within half an hour after the KEDZIE YARD theft (10:30 to 11 p.m., March "
                        "21, 2026)",
                    ),
                ),
                "pass",
                "10:58:10 p.m. CDT, 165 s, to +13125550199.",
            ),
        ),
        gaps=(
            "No template says who placed a call; Item 3 logs it as outgoing, as the claim says.",
        ),
    ),
    ClaimSpec(
        "C17",
        (
            A(
                "sender",
                P(quoted_text=Q17, person_ids=[FER], channels=["WhatsApp"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q17,
                    person_ids=[FER, HAL],
                    channels=["WhatsApp"],
                    window=window(
                        "2026-03-25T23:37:00",
                        "2026-03-25T23:54:00",
                        "At about a quarter to midnight on the night before the SEARCH (March 25, "
                        "2026)",
                    ),
                ),
                "pass",
                "11:46:12 p.m. CDT Mar 25; Item 1 prints 3/26 4:46:12 AM(UTC+0).",
            ),
        ),
    ),
    ClaimSpec(
        "C18",
        (
            A(
                "record_time",
                P(
                    person_ids=[OKA],
                    account_ids=[CW1],
                    channels=["call"],
                    window=window(
                        "2026-03-21T22:15:00",
                        "2026-03-21T22:46:00",
                        "Within fifteen minutes of the KEDZIE YARD theft (10:15 to 10:45 p.m., "
                        "March 21, 2026)",
                    ),
                ),
                "inconclusive",
                "No call with CW-1's number; the 10:36 p.m. call is to Item 3's 'Rocco', "
                "+17735550133.",
            ),
        ),
    ),
    # ------------------------------------------------------------ content meaning
    ClaimSpec(
        "C19",
        (
            A(
                "sender",
                P(quoted_text=Q19, person_ids=[HAL], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q19,
                    person_ids=[HAL, FER],
                    channels=["SMS"],
                    window=day("2026-03-09", "On March 9, 2026"),
                ),
                "pass",
                "10:30 a.m. CDT Mar 9.",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q19,
                    person_ids=[HAL, FER],
                    channels=["SMS"],
                    window=day("2026-03-09", "On March 9, 2026"),
                ),
                None,
                "'the copper ones?' / 'ya the copper, all 9' in the same exchange.",
            ),
        ),
    ),
    ClaimSpec(
        "C20",
        (
            A(
                "sender",
                P(quoted_text=Q20, person_ids=[FER], channels=["SMS"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q20,
                    person_ids=[FER, HAL],
                    channels=["SMS"],
                    window=day("2026-03-13", "On March 13, 2026"),
                ),
                "pass",
                "4:20 p.m. CDT Mar 13.",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q20,
                    person_ids=[FER, HAL],
                    channels=["SMS"],
                    window=day("2026-03-13", "On March 13, 2026"),
                ),
                None,
                "Whether 'the 3 heavy ones' are the BELMONT SITE generators; nothing fixes it.",
            ),
        ),
    ),
    ClaimSpec(
        "C21",
        (
            A(
                "sender",
                P(quoted_text=Q21, person_ids=[OKA], channels=["SMS"]),
                "fail",
                "FERRO sent it to OKAFOR.",
            ),
            A(
                "record_time",
                P(quoted_text=Q21, channels=["SMS"], window=day("2026-03-16", "On March 16, 2026")),
                "pass",
                "4:10 p.m. CDT Mar 16.",
            ),
            A(
                "meaning",
                P(quoted_text=Q21, channels=["SMS"]),
                None,
                "That the words warn of a buyer working with police.",
            ),
        ),
    ),
    ClaimSpec(
        "C22",
        (
            A(
                "sender",
                P(quoted_text=Q22, person_ids=[HAL], channels=["Telegram"]),
                "pass",
                "HAL is HALLORAN; outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q22,
                    person_ids=[HAL, OKA],
                    channels=["Telegram"],
                    window=day("2026-03-11", "Two days later (March 11, 2026)"),
                ),
                "pass",
                "'Two days later' follows C19's March 9. 9:20 p.m. CDT Mar 11.",
            ),
            A(
                "meaning",
                P(quoted_text=Q22, person_ids=[HAL, OKA], channels=["Telegram"]),
                None,
                "The Mar 8 'wrap the spools in the moving blankets' fixes 'blankets'.",
            ),
        ),
    ),
    ClaimSpec(
        "C23",
        (
            A(
                "sender",
                P(quoted_text=Q23, account_ids=[KIP2], channels=["Instagram"]),
                "pass",
                "The BUYER is kipflips.chi (paragraph 3).",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q23,
                    person_ids=[FER],
                    account_ids=[KIP2],
                    channels=["Instagram"],
                    window=day("2026-03-24", "Two days before the SEARCH (March 24, 2026)"),
                ),
                "pass",
                "3:05 p.m. CDT Mar 24.",
            ),
            A(
                "meaning",
                P(
                    quoted_text=Q23,
                    person_ids=[FER],
                    account_ids=[KIP2],
                    channels=["Instagram"],
                    window=day("2026-03-24", "Two days before the SEARCH (March 24, 2026)"),
                ),
                None,
                "'lot is 4 spools ...' before and '1800 works. sat' after fix the meaning.",
            ),
        ),
    ),
    ClaimSpec(
        "C24",
        (
            A(
                "sender",
                P(quoted_text=Q24, account_ids=[MARI], channels=["WhatsApp"]),
                "pass",
                "FERRO's sister ('Mari') sent it.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q24,
                    person_ids=[FER],
                    account_ids=[MARI],
                    channels=["WhatsApp"],
                    window=day("2026-03-17", "On St. Patrick's Day (March 17, 2026)"),
                ),
                "pass",
                "6:20 p.m. CDT Mar 17.",
            ),
            A(
                "meaning",
                P(quoted_text=Q24, channels=["WhatsApp"]),
                None,
                "Which Owen, and what stuff; not fixed.",
            ),
        ),
        gaps=("That the sister is Marisol Ferro is the contact name 'Mari', not tested.",),
    ),
    # ------------------------------------------------------------ count
    ClaimSpec(
        "C25",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM1],
                    person_ids=[HAL, FER],
                    channels=["WhatsApp"],
                    expected_count=8,
                    count_op="eq",
                    window=window(
                        "2026-02-23", "2026-03-02", "Between February 23 and March 1, 2026"
                    ),
                ),
                "pass",
                "Eight on Chicago dates; printed dates give nine.",
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
                    person_ids=[OKA, HAL],
                    channels=["Telegram"],
                    expected_count=6,
                    count_op="eq",
                    window=window(
                        "2026-03-09", "2026-03-15", "From March 9 through March 14, 2026"
                    ),
                ),
                "pass",
                "Six on Item 3; Item 1 holds seven.",
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
                    person_ids=[FER, OKA],
                    channels=["SMS"],
                    expected_count=3,
                    count_op="eq",
                    window=day("2026-03-21", "On March 21, 2026"),
                ),
                "fail",
                "Five on the Chicago day.",
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
                    person_ids=[OKA],
                    account_ids=[PRE3],
                    channels=["SMS"],
                    expected_count=11,
                    count_op="eq",
                    window=window(
                        "2026-03-02",
                        "2026-03-07",
                        "During the work week before the BELMONT SITE theft, Monday through "
                        "Friday (March 2 to 6, 2026)",
                    ),
                ),
                "pass",
                "Eleven between the PREPAID and OKAFOR on Item 3 (SUBJECT-3's phone).",
            ),
        ),
    ),
    ClaimSpec(
        "C29",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM2],
                    person_ids=[FER, HAL],
                    channels=["Telegram"],
                    expected_count=4,
                    count_op="eq",
                    window=window(
                        "2026-03-16", "2026-03-21", "Between March 16 and March 20, 2026"
                    ),
                ),
                "fail",
                "Six on the TARGET PHONE (Item 2).",
            ),
        ),
    ),
    ClaimSpec(
        "C30",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM1],
                    person_ids=[HAL, FER],
                    channels=["SMS"],
                    expected_count=12,
                    count_op="ge",
                    window=window(
                        "2026-03-07T23:00:00",
                        "2026-03-08T03:00:00",
                        "On the night of the BELMONT SITE theft, between 11 p.m. and 3 a.m.",
                    ),
                ),
                "inconclusive",
                "Nine in the three real hours; fewer than claimed is never a fail.",
            ),
        ),
    ),
    # ------------------------------------------------------------ absence
    ClaimSpec(
        "C31",
        (
            A(
                "no_contact",
                P(person_ids=[HAL, OKA], window=day("2026-03-14", "on March 14, 2026")),
                "fail",
                "The 9:30 p.m. CDT text.",
            ),
        ),
    ),
    ClaimSpec(
        "C32",
        (
            A(
                "no_contact",
                P(
                    person_ids=[FER, HAL],
                    window=window(
                        "2026-03-27", "2026-03-30", "between March 27 and March 29, 2026"
                    ),
                ),
                "inconclusive",
                "None with HALLORAN's phone accounts; curated reports.",
            ),
            A(
                "no_contact",
                P(
                    person_ids=[FER],
                    account_ids=[PRE2],
                    window=window(
                        "2026-03-27", "2026-03-30", "between March 27 and March 29, 2026"
                    ),
                ),
                "fail",
                "The PREPAID (HALLORAN's, paragraph 3) wrote to FERRO on Mar 28.",
            ),
        ),
    ),
    ClaimSpec(
        "C33",
        (
            A(
                "no_contact",
                P(
                    person_ids=[OKA],
                    account_ids=[CW1],
                    window=window("2026-03-01", "2026-04-01", "between March 1 and March 31, 2026"),
                ),
                "inconclusive",
                "None found; curated reports. Item 3's 'Rocco' is another number.",
            ),
        ),
    ),
    ClaimSpec(
        "C34",
        (
            A(
                "no_contact",
                P(
                    person_ids=[OKA, FER],
                    window=window(
                        "2026-03-08T03:00:00",
                        "2026-03-08T04:00:00",
                        "In the first hour after the clocks went forward that night (3 to 4 a.m. "
                        "CDT, March 8, 2026)",
                    ),
                ),
                "inconclusive",
                "None in the hour; the 4:12 a.m. call prints 3:12 AM(UTC-6) on Item 3.",
            ),
        ),
    ),
    ClaimSpec(
        "C35",
        (
            A(
                "no_contact",
                P(
                    person_ids=[FER, OKA],
                    window=window(
                        "2026-03-23",
                        "2026-03-26",
                        "In the days leading up to the SEARCH, from Monday through Wednesday "
                        "(March 23 to 25, 2026)",
                    ),
                ),
                "fail",
                "DEZ is OKAFOR (paragraph 2). WhatsApp on Mar 23 and 24.",
            ),
        ),
    ),
    ClaimSpec(
        "C36",
        (
            A(
                "no_contact",
                P(person_ids=[HAL, OKA], device_ids=[ITEM1], window=AFTER_SEARCH),
                "inconclusive",
                "None on Item 1 (SUBJECT-1's phone); curated. Item 3 holds a Mar 29 text.",
            ),
        ),
    ),
    # ------------------------------------------------------------ role
    ClaimSpec(
        "C37",
        (
            A(
                "sender",
                P(quoted_text=Q37_LOT, person_ids=[FER], channels=["Instagram"]),
                "pass",
                "ferro.finds is an owner account of Item 2.",
            ),
            A(
                "sender",
                P(quoted_text=Q37_OK, person_ids=[FER], channels=["Instagram"]),
                "pass",
                "The acceptance, from ferro.finds.",
            ),
            A(
                "role",
                P(person_ids=[FER], account_ids=[KIP2], channels=["Instagram"]),
                None,
                "That FERRO handled the sale; the conversation shows her account setting terms.",
            ),
        ),
    ),
    ClaimSpec(
        "C38",
        (
            A(
                "sender",
                P(quoted_text=Q38, person_ids=[OKA], channels=["SMS"]),
                "fail",
                "FERRO sent it.",
            ),
            A(
                "record_time",
                P(quoted_text=Q38, channels=["SMS"], window=day("2026-03-20", "On March 20, 2026")),
                "pass",
                "2:00 p.m. CDT Mar 20.",
            ),
            A("role", P(person_ids=[OKA]), None, "That OKAFOR set the time."),
        ),
    ),
    ClaimSpec(
        "C39",
        (
            A(
                "role",
                P(person_ids=[HAL, OKA]),
                None,
                "That HALLORAN recruited OKAFOR; OKAFOR offered himself.",
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
                P(quoted_text=Q40, person_ids=[OKA], channels=["SMS"]),
                "pass",
                "DEZ is OKAFOR; outgoing on Item 3.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q40,
                    person_ids=[OKA],
                    account_ids=[TASH],
                    channels=["SMS"],
                    window=window(
                        "2026-03-21T17:00:00",
                        "2026-03-22T00:00:00",
                        "that evening (March 21, 2026, 5 p.m. to midnight)",
                    ),
                ),
                "pass",
                "7:40 p.m. CDT Mar 21, to 'Tash'.",
            ),
            A(
                "role",
                P(person_ids=[OKA], quoted_text=Q40, window=KEDZIE_NIGHT),
                None,
                "That OKAFOR drove that night; his own words.",
            ),
        ),
        gaps=("That 'Tash' is his girlfriend is not tested (no template for kin).",),
    ),
    ClaimSpec(
        "C41",
        (
            A(
                "sender",
                P(quoted_text=Q41, person_ids=[FER], channels=["SMS"]),
                "fail",
                "HALLORAN wrote it, to FERRO.",
            ),
            A("role", P(person_ids=[FER]), None, "That FERRO chose where the spools went."),
        ),
    ),
    ClaimSpec(
        "C42",
        (
            A(
                "role",
                P(
                    person_ids=[HAL],
                    window=window(
                        "2026-03-07T18:00:00",
                        "2026-03-07T23:00:00",
                        "In the hours before the BELMONT SITE theft (March 7, 2026, 6 to 11 p.m.)",
                    ),
                ),
                None,
                "That HALLORAN acted as a lookout; the only 'site is clear' text went to his "
                "foreman.",
            ),
        ),
        gaps=("The claim paraphrases a report without quoting it; no check applies.",),
    ),
    # ------------------------------------------------------------ event
    ClaimSpec(
        "C43",
        (
            A(
                "sender",
                P(quoted_text=Q43, person_ids=[HAL], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q43,
                    person_ids=[HAL, OKA],
                    channels=["SMS"],
                    window=day("2026-03-03", "On March 3, 2026"),
                ),
                "pass",
                "12:10 p.m. CST Mar 3.",
            ),
            A(
                "weekday_date",
                P(
                    quoted_text=Q43,
                    channels=["SMS"],
                    window=day("2026-03-05", "Thursday, March 5, 2026"),
                ),
                "pass",
                "'thursday' sent on Tuesday Mar 3 is Mar 5.",
            ),
            A(
                "event",
                P(
                    person_ids=[HAL, OKA],
                    channels=["SMS"],
                    window=day("2026-03-03", "On March 3, 2026"),
                ),
                None,
                "That they arranged it: OKAFOR's 'ok'.",
            ),
        ),
        gaps=("'Behind the laundromat on Fullerton' is not tested (no template for a place).",),
    ),
    ClaimSpec(
        "C44",
        (
            A(
                "sender",
                P(quoted_text=Q44_ASK, person_ids=[FER], channels=["SMS"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "sender",
                P(quoted_text=Q44_OK, person_ids=[HAL], channels=["SMS"]),
                "pass",
                "HALLORAN's answer, outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q44_ASK,
                    person_ids=[FER, HAL],
                    channels=["SMS"],
                    window=day("2026-03-23", "On March 23, 2026"),
                ),
                "pass",
                "11:00 a.m. CDT Mar 23.",
            ),
        ),
    ),
    ClaimSpec(
        "C45",
        (
            A(
                "record_time",
                P(
                    person_ids=[FER, OKA],
                    channels=["call"],
                    duration_s=[540, 660],
                    window=day("2026-03-12", "On March 12, 2026"),
                ),
                "inconclusive",
                "Their only call that day lasted 45 s; the 612 s call is with Item 2's 'Dez'.",
            ),
        ),
    ),
    ClaimSpec(
        "C46",
        (
            A(
                "sender",
                P(quoted_text=Q46, person_ids=[OKA], channels=["Telegram"]),
                "pass",
                "The DRIVER's Telegram, outgoing on Item 3.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q46,
                    person_ids=[OKA, FER],
                    channels=["Telegram"],
                    window=window(
                        "2026-03-08T04:30:00",
                        "2026-03-08T05:00:00",
                        "Shortly before 5 a.m. the morning after the theft (March 8, 2026, 4:30 "
                        "to 5 a.m.)",
                    ),
                ),
                "pass",
                "4:48:26 a.m. CDT; Item 3 prints 3:48:26 AM(UTC-6).",
            ),
        ),
    ),
    ClaimSpec(
        "C47",
        (
            A(
                "sender",
                P(quoted_text=Q47, person_ids=[FER], channels=["WhatsApp"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q47,
                    person_ids=[FER, OKA],
                    channels=["WhatsApp"],
                    window=day(
                        "2026-03-23", "Two days after the KEDZIE YARD theft (March 23, 2026)"
                    ),
                ),
                "pass",
                "8:30 p.m. CDT Mar 23.",
            ),
            A(
                "event",
                P(
                    person_ids=[FER, OKA],
                    channels=["WhatsApp"],
                    window=day(
                        "2026-03-23", "Two days after the KEDZIE YARD theft (March 23, 2026)"
                    ),
                ),
                None,
                "That he was paid: his 'got it, thx'.",
            ),
        ),
    ),
    ClaimSpec(
        "C48",
        (
            A(
                "no_contact",
                P(person_ids=[FER, OKA], window=AFTER_SEARCH),
                "fail",
                "FERRO's Mar 28 WhatsApp, held on Item 3 only.",
            ),
        ),
    ),
)

# Claims no template can state, with the reason. None: every claim has a sheet.
NO_SHEET: dict[str, str] = {}

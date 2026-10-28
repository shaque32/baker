"""Case03 mock affidavit, DRAFT answer key and DRAFT assumption sheet. SYNTHETIC.

DRAFT ONLY. Every verdict and every assumption row below is the builder's proposal. Arsh reviews
and decides each one; nothing here is gold until a human copies it into eval/gold/. The
affidavit text is generated from this file so claim wording stays verbatim.

case03 measures a challenge step: a search for counter-evidence on claims that look close to
supported. Its 17 claims fall in four groups:

1. Counter-evidence code can find. The claim looks supported by what the fixed retrieval
   (core/audit/retrieval.py) returns; the record that undercuts it sits out of that retrieval's
   reach, where one explanation direction of core/hypotheses/explain.py points.
2. Counter-evidence only a word-variant search finds: slang, a misspelling, transliteration.
   Neither the fixed retrieval nor explain.py's literal matching reaches it.
3. Clean claims, supported, each with near-miss decoys, to measure how much a challenge step
   flags that it should not.
4. Claims written the way a model may refuse to read: a defined term ("the TARGET PHONE"), an
   alias, a relative date. The correct reading follows from the affidavit's own definitions and
   the data, and the assumption sheet writes it out.

Evidence is referenced as (device, story key); the generator resolves keys to record ids such as
'msg:item1:Chats!412'. 'contact:<name>' is a saved contact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

DRAFT_LABEL = "DRAFT (case03 builder, not signed by Arsh)"
TEMPLATES_VERSION = "1.0.0"
NY = "America/New_York"

GROUPS = {
    1: "counter-evidence code can find",
    2: "counter-evidence only a word-variant search finds",
    3: "clean, supported, with near-miss decoys",
    4: "defined terms, alias or relative date",
}

LABELING_RULES = (
    "A claim is contradicted only when observed data rules it out: the quoted message exists "
    "with another sender, or at another time, and no copy fits the claim (C06, C08).",
    "Counter-evidence that makes another account of events more likely, without ruling the "
    "claim out, complicates the claim and leaves it unproven (every group 1 and group 2 claim).",
    "A meaning claim is supported only when the case itself fixes the meaning; an agent's "
    "reading of slang or of a translation is inferred, not observed.",
    "Dates and times are judged on the phone's own clock (America/New_York), never on a "
    "printed UTC value. Item 1 prints UTC+0; Item 2 prints local time.",
    "Defined terms are read as the affidavit defines them: the TARGET PHONE is Item 1, PASHA "
    "and SUBJECT-1 are ORLOV, SUBJECT-2 is DIAZ, the SEARCH is the March 14, 2026 search.",
)

DEVICE_ATTRIBUTION = (
    "Item 1 is used by ORLOV and Item 2 by DIAZ, so the owner accounts on each phone speak for "
    "them unless the case shows otherwise. The key treats this as given, as the affidavit does. "
    "It is not proven by the data, and claims C03, C11 and C17 exist to test where it breaks."
)

# What explain.py (VERSION 1.0.0) lists that is not counter-evidence, measured with
# eval/synthetic/case03_reach.py. A challenge step that acts on these is noise.
KNOWN_NOISE = (
    "Item 2 saves ORLOV's number as 'Pasha' (C01), the Russian short form of Pavel, and his "
    "Telegram display name is 'Pasha O'. The other-user direction lists these names on claims "
    "that name ORLOV (C03, C05, C10, C13) because they share no word with Pavel Orlov. The "
    "affidavit gives PASHA as ORLOV's alias; the names are no sign of another user.",
    "C02: day-boundary lists the two late Mar 7 messages (Mar 8 in UTC), other-app lists SMS, "
    "WhatsApp and a call between them that week, curated fires on the report. None changes a "
    "Telegram count on the phone's clock.",
    "C14: clock lists the 10:05 a.m. call that Item 1 prints as 2:05:20 PM(UTC+0). The claim "
    "rests on the 2:04 p.m. call.",
    "C10, C13, C15: same-words lists messages of the conversation that share a common word "
    "('завтра', 'after', 'bring', 'tmrw'). None bears on the meaning in question.",
    "C06: other-user lists DIAZ's Telegram name 'Ruben D', because the message is DIAZ's; the "
    "failed sender check decides that claim already.",
    "C09, C13: curated fires because both reports are examiner-curated. It is true of every "
    "claim and is not specific counter-evidence.",
)

Ref = tuple[str, str]  # (device, story key)


@dataclass(frozen=True)
class DraftClaim:
    claim_id: str
    group: int
    text: str
    claim_type: str
    cross_device: bool
    verdict: str
    core_assumptions: tuple[str, ...]
    evidence: tuple[Ref, ...]  # key evidence: what a reviewer must see, counter-records too
    plant: str  # short name of what was planted (GoldClaim.trap)
    rationale: str
    counter: tuple[Ref, ...] = ()  # the counter-records (a subset of evidence)
    direction: str | None = None  # the explain.py direction that should find them (group 1)
    reach: str = ""  # why the fixed retrieval does not return the counter-records
    decoys: tuple[Ref, ...] = ()  # near misses a challenge step should pass over (group 3)


C = DraftClaim

CLAIMS: tuple[DraftClaim, ...] = (
    C(
        "C01",
        3,
        'Item 2 contains a contact saved as "Pasha" with the number +1 (718) 555-0111.',
        "identity",
        False,
        "supported",
        ("Item 2's contact list has an entry named exactly 'Pasha' with +17185550111",),
        (("item2", "contact:Pasha"),),
        "clean_contact",
        "Observed directly in the Item 2 contacts sheet. 'Pasha Tires' (+17185550106) is a "
        "different entry and number.",
        decoys=(("item2", "contact:Pasha Tires"),),
    ),
    C(
        "C02",
        3,
        "Between March 1 and March 7, 2026, Item 2 recorded 9 Telegram messages exchanged "
        "between DIAZ and ORLOV.",
        "count",
        False,
        "supported",
        (
            "Item 2 holds exactly 9 Telegram messages between DIAZ and ORLOV dated Mar 1 to Mar 7 "
            "on the phone's clock",
        ),
        tuple(("item2", f"dt_c{i}") for i in range(1, 10)),
        "clean_count",
        "Nine Telegram rows on Item 2, Mar 2 to Mar 7 local time. The last two were sent after "
        "10:30 p.m. EST on Mar 7, which is Mar 8 in UTC (Item 1 prints them as 3/8); on the "
        "phone's clock they are on Mar 7, so the count stands. SMS between them on Mar 7 is "
        "another app and not part of a Telegram count.",
        decoys=(("item1", "dt_c8"), ("item1", "dt_c9"), ("item2", "ds_bay")),
    ),
    C(
        "C03",
        2,
        'On March 7, 2026, ORLOV texted DIAZ "can u open the bay early tmrw, got 3 to drop".',
        "communication",
        False,
        "unproven",
        (
            "The message was sent from ORLOV's SMS account on Item 1 on Mar 7",
            "ORLOV, not someone else holding Item 1, wrote it",
        ),
        (("item1", "ds_bay"), ("item1", "kd_fone"), ("item1", "kd_back")),
        "misspelled_handoff",
        "The message is observed, outgoing from Item 1's SMS account on Mar 7. But the evening "
        "before, Item 1 sent Dasha 'dis kirill. usin pasha fone til sunday, mine broke', and "
        "on Sunday Mar 8 'bak on my own fone now'. Someone named Kirill says he held the phone "
        "across the time of the claimed message. That does not rule ORLOV out, so unproven.",
        counter=(("item1", "kd_fone"), ("item1", "kd_back")),
        reach="The note is in another conversation (Dasha), the day before the claim's window, "
        "and is not the nearest record to it; it shares no word with the claim. explain.py's "
        "hand-off pattern needs 'using' or 'used' and a word such as 'phone', and its "
        "introduction pattern needs 'this is' or 'it's'; 'usin', 'fone' and 'dis' match "
        "neither. Only a search that knows these spellings finds it.",
    ),
    C(
        "C04",
        1,
        "At about 11:40 p.m. on March 9, 2026, ORLOV placed a call of about two minutes from "
        "Item 1 to DIAZ.",
        "timing",
        False,
        "unproven",
        (
            "Item 1 logged a call of about two minutes between ORLOV and DIAZ at about 11:40 p.m. "
            "on Mar 9, local time",
            "ORLOV placed it (an outgoing call)",
        ),
        (("item1", "cl_740"), ("item1", "cl_1139")),
        "clock_printed_utc",
        "Item 1 prints every time in UTC+0. Its only outgoing two-minute call to DIAZ that day "
        "prints as 3/9/2026 11:40:12 PM(UTC+0), which is 7:40 p.m. on the phone's clock, "
        "before the 11:20 p.m. theft in paragraph 5. The call that does fall at about 11:40 "
        "p.m. local is DIAZ calling ORLOV (112 s, incoming). A time check on the parties passes "
        "on that incoming call, so the claim looks supported; the direction and the printed "
        "clock both say otherwise. Not ruled out (the log may be incomplete), so unproven.",
        counter=(("item1", "cl_740"),),
        direction="clock",
        reach="The claim's window is 11:32 to 11:47 p.m. local. The outgoing call is four hours "
        "earlier on the phone's clock, and an unanswered call at 9:52 p.m. sits between them, "
        "so it is not the nearest record before the window either. explain.py's clock "
        "direction reads the printed UTC+0 time as local and finds it.",
    ),
    C(
        "C05",
        3,
        'On March 11, 2026, ORLOV texted DIAZ "got 4 more, all hondas. same price?".',
        "communication",
        False,
        "supported",
        ("The message was sent from ORLOV's SMS account to DIAZ on Mar 11, local time",),
        (("item1", "ds_hondas"),),
        "clean_message",
        "Observed outgoing on Item 1 at 3:42 p.m. EDT on Mar 11 (printed 7:42 PM UTC+0). Near "
        "misses a challenge step should pass over: Kemal left his own phone in ORLOV's car "
        "(Mar 10), and ORLOV denies using Igor's phone (Mar 12). Neither says "
        "anyone else used Item 1.",
        decoys=(("item1", "ks_left"), ("item1", "lw_igor2")),
    ),
    C(
        "C06",
        4,
        'On March 12, 2026, PASHA told SUBJECT-2 on Telegram "need the lift friday after 6".',
        "communication",
        False,
        "contradicted",
        (
            "PASHA is ORLOV (paragraph 2) and SUBJECT-2 is DIAZ",
            "ORLOV's Telegram account sent the message on Mar 12",
        ),
        (("item1", "dt_lift"), ("item2", "dt_lift")),
        "alias_reversed_sender",
        "Read with paragraph 2, the claim says ORLOV wrote to DIAZ. Both phones log the message "
        "as sent by DIAZ's Telegram account (user id 7101002): outgoing on Item 2, incoming on "
        "Item 1. ORLOV only answered. Observed data rules the stated sender out.",
    ),
    C(
        "C07",
        4,
        'On the day after the SEARCH, the TARGET PHONE sent CS-1 a text message reading "not '
        'now. after the weekend".',
        "communication",
        False,
        "supported",
        (
            "The SEARCH was on Mar 14, so the day after is Mar 15 (paragraph 4)",
            "The TARGET PHONE is Item 1 and CS-1 used +17185550190 (paragraphs 2 and 3)",
            "Item 1's SMS account sent the message to +17185550190 on Mar 15",
        ),
        (("item1", "cs_now"),),
        "defined_terms",
        "Outgoing SMS on Item 1 to +17185550190 at 11:26 a.m. EDT on Mar 15 (printed 3:26 PM "
        "UTC+0). Item 1 saves that number as 'Mikey'; the affidavit says only that CS-1 used "
        "the number, which the record shows. The claim names the phone, not a person.",
    ),
    C(
        "C08",
        4,
        'Two days later, SUBJECT-2 texted the TARGET PHONE "all quiet here, dont come by".',
        "communication",
        False,
        "contradicted",
        (
            "'Two days later' is Mar 17, two days after the day after the SEARCH (C07)",
            "DIAZ's SMS account sent the message to Item 1 on Mar 17",
        ),
        (("item2", "ds_quiet"), ("item1", "ds_quiet")),
        "relative_date",
        "The message exists on both phones, sent by DIAZ at 9:10 a.m. EDT on Mar 18. 'Two days "
        "later' follows C07's 'day after the SEARCH' (Mar 15) and is Mar 17; read from the "
        "SEARCH itself it would be Mar 16. Neither is Mar 18, and no copy is dated otherwise, "
        "so the stated day is ruled out.",
    ),
    C(
        "C09",
        1,
        "After the SEARCH, ORLOV stopped messaging DIAZ on WhatsApp from March 15 through March "
        "18, 2026, in order to avoid detection by law enforcement.",
        "event",
        True,
        "unproven",
        (
            "No WhatsApp messages between ORLOV and DIAZ from Mar 15 through Mar 18",
            "The stop was chosen to avoid detection",
        ),
        (
            ("item1", "dw_away"),
            ("item1", "lw_crash"),
            ("item1", "lw_fixed"),
        ),
        "app_broken",
        "Neither phone has a WhatsApp message between them from Mar 15 through Mar 18, and on "
        "Mar 14 ORLOV wrote 'dont write me here for a while', which reads like the claim. But "
        "Item 1's WhatsApp is quiet in every conversation for those four days, while its SMS "
        "and Telegram go on; the last WhatsApp record before is ORLOV telling his sister 'this "
        "app keeps crashing since the update, half my chats wont load. just text me', and the "
        "first after is 'its working again finally'. The silence has another observed cause; "
        "the purpose is not shown, so unproven. The reports are curated, so the absence itself "
        "cannot be shown complete either.",
        counter=(("item1", "lw_crash"), ("item1", "lw_fixed")),
        direction="app_quiet",
        reach="Both records are in ORLOV's WhatsApp conversation with his sister, not with "
        "DIAZ, so the party filter drops them; the nearest records before and after the window "
        "come from the ORLOV-DIAZ conversation itself (Mar 14 'dont write me here for a "
        "while', Mar 19 'u around?'). "
        "explain.py's app-quiet direction looks at every WhatsApp conversation on Item 1 and "
        "returns the last record before and the first after the quiet stretch.",
    ),
    C(
        "C10",
        2,
        'On March 17, 2026, ORLOV wrote to his brother on Telegram, in Russian, "коробки у '
        'меня, завтра отвезу" (in English: the boxes are with me, I will take them tomorrow); '
        "the boxes in that message were the stolen catalytic converters.",
        "content_meaning",
        False,
        "unproven",
        (
            "ORLOV's Telegram account sent the Russian message on Mar 17",
            "'коробки' (the boxes) means the stolen catalytic converters",
        ),
        (
            ("item1", "mt_claim"),
            ("item1", "mt_box1"),
            ("item1", "mt_box2"),
            ("item1", "mt_box3"),
        ),
        "transliteration",
        "The message and the translation are right. The meaning is not: on Mar 9 the brother "
        "wrote, in Russian typed in Latin letters, 'pasha, mama prosit zabrat korobki s posudoj "
        "iz garazha i otvezti k nej' (mom asks you to take the boxes of dishes from the garage "
        "to her), and on Mar 19 'mama zvonila, skazala ty privez korobki. spasibo' (mom called, "
        "said you brought the boxes, thanks). The thread gives the boxes another meaning; it "
        "does not rule the claimed one out, so unproven.",
        counter=(("item1", "mt_box1"), ("item1", "mt_box2"), ("item1", "mt_box3")),
        reach="Both are in the same conversation but eight days before and two days after the "
        "claim's day, and other messages lie between them and the window. 'korobki' is the "
        "claim's 'коробки' in Latin letters, so no keyword and no whole-word match of "
        "explain.py's same-words direction connects them. Only a search that knows "
        "transliteration finds them.",
    ),
    C(
        "C11",
        1,
        "On March 19, 2026, ORLOV, using the Instagram account orlov.detailing, told the "
        'Instagram user jr.parts.nyc "come thru after 9, bring cash".',
        "communication",
        False,
        "unproven",
        (
            "orlov.detailing sent the message to jr.parts.nyc on Mar 19",
            "ORLOV personally wrote what orlov.detailing sent",
        ),
        (("item1", "jr_cash"), ("item1", "mia_kemal")),
        "shared_account_intro",
        "The message is observed, outgoing from orlov.detailing, an owner account of Item 1. "
        "The account is the detailing shop's: the day before, the same account wrote to "
        "another customer 'hi its kemal from the shop. boss is out today', and Kemal is a "
        "saved contact on Item 1. Someone other than ORLOV writes as orlov.detailing; who "
        "wrote this message is not shown, so unproven.",
        counter=(("item1", "mia_kemal"),),
        direction="other_user",
        reach="The introduction is in another conversation of the account (mia.k.nyc), the "
        "day before the window, and the nearest record before the window is jr.parts.nyc's "
        "own Mar 17 message, so neither the party ranking nor the window edge returns it. "
        "explain.py's other-user direction reads messages the claimed account sent, at any "
        "time, for a self-introduction with a name the case knows.",
    ),
    C(
        "C12",
        3,
        'On Friday, March 20, 2026, DIAZ wrote to ORLOV on Telegram "lot on varick, sunday '
        '9pm", setting a meeting for Sunday, March 22, 2026.',
        "communication",
        False,
        "supported",
        (
            "DIAZ's Telegram account sent the message to ORLOV on Mar 20",
            "'sunday', counted from Friday Mar 20, is Mar 22",
        ),
        (("item2", "dt_varick"), ("item1", "dt_varick")),
        "clean_weekday",
        "Outgoing on Item 2 at 3:15 p.m. EDT on Mar 20, incoming on Item 1 (printed 7:15 PM "
        "UTC+0); Mar 20, 2026 is a Friday and the next Sunday is Mar 22. Decoys: DIAZ's wife "
        "says 'sunday is my moms bday' on WhatsApp that morning, and Kemal complains about "
        "parking on Varick by SMS; neither is about the meeting.",
        decoys=(("item2", "aw_sunday"), ("item1", "ks_varick")),
    ),
    C(
        "C13",
        1,
        "On March 21, 2026, over WhatsApp, DIAZ agreed to ORLOV's request to hold \"the 6 "
        'pieces" at his shop until Tuesday, March 24, 2026.',
        "event",
        False,
        "unproven",
        (
            "ORLOV asked on WhatsApp to hold the 6 pieces at DIAZ's shop until Tuesday Mar 24",
            "DIAZ's reply on Mar 21 is an agreement, and it stood",
        ),
        (
            ("item1", "dw_hold"),
            ("item1", "dw_hold2"),
            ("item1", "dt_scratch"),
            ("item1", "dt_scratch2"),
        ),
        "retracted_other_app",
        "The request and DIAZ's 'ok bring them by after 8' are observed on WhatsApp at 1:05 "
        "and 1:12 p.m. EDT. At 10:15 p.m. the same day, on Telegram, DIAZ wrote 'scratch that. "
        "landlord coming by sunday. cant have them here' and ORLOV answered 'fine ill keep "
        "them in the van'. The agreement was made and withdrawn the same day; the claim's "
        "picture of pieces held at the shop until Tuesday is not shown, so unproven.",
        counter=(("item1", "dt_scratch"), ("item1", "dt_scratch2")),
        direction="other_app",
        reach="Every assumption names WhatsApp, and the retraction is on Telegram, so the "
        "channel filter drops it; the window edges and the reply companions come from WhatsApp "
        "too. explain.py's other-app direction lists the two parties' records on other apps "
        "inside the claim's window.",
    ),
    C(
        "C14",
        3,
        "At about 2:05 p.m. on March 23, 2026, DIAZ called ORLOV; the call lasted about six "
        "minutes.",
        "timing",
        False,
        "supported",
        (
            "A call of about six minutes between DIAZ and ORLOV happened at about 2:05 p.m. on Mar "
            "23, local time",
        ),
        (("item2", "cl_1404"), ("item1", "cl_1404")),
        "clean_call",
        "Outgoing on Item 2 at 2:04:30 PM(UTC-4), 370 s; incoming on Item 1 (printed 6:04:30 PM "
        "UTC+0). Decoy: a 362 s call the same morning at 10:05 a.m., which Item 1 prints as "
        "2:05:20 PM(UTC+0). Read on the phone's clock it is a different call, four hours "
        "earlier, and the claim stands on the 2:04 p.m. one.",
        decoys=(("item1", "cl_1005"),),
    ),
    C(
        "C15",
        2,
        'On March 24, 2026, DIAZ texted ORLOV "bring the paper tmrw", a demand that ORLOV bring '
        "cash payment for stolen catalytic converters.",
        "content_meaning",
        False,
        "unproven",
        (
            "DIAZ's SMS account sent the message to ORLOV on Mar 24",
            "'the paper' means cash payment for stolen catalytic converters",
        ),
        (
            ("item2", "ds_paper"),
            ("item2", "hc01"),
            ("item2", "hc02"),
            ("item2", "hc03"),
        ),
        "slang_synonym",
        "The message is observed. Its meaning is not: the day before, a buyer told DIAZ 'still "
        "want the 09 civic. need the pink slip first n we're done'; DIAZ answered 'my guy has "
        "it, ill get it to u by thursday', and on Thursday 'come by at 5, got the title for u'. "
        "'The paper' fits the car's title (a pink slip) as well as cash. Not ruled out, so "
        "unproven.",
        counter=(("item2", "hc01"), ("item2", "hc02"), ("item2", "hc03")),
        reach="The Hector thread is another conversation, a day before and two days after the "
        "claim's day, and shares no word with the claim: 'pink slip' and 'title' are other "
        "words for 'paper'. explain.py's same-words direction looks only in the claimed "
        "conversation and only for the quote's own words.",
    ),
    C(
        "C16",
        1,
        'On March 25, 2026, DIAZ, using the phone number +1 (646) 555-0170, texted ORLOV "the '
        'bushwick guy wants 6 by friday".',
        "communication",
        True,
        "unproven",
        (
            "+16465550170 sent the message to ORLOV on Mar 25",
            "DIAZ personally used +16465550170",
        ),
        (("item1", "e_bush"), ("item1", "e_bush2"), ("item2", "contact:Eddie P")),
        "saved_under_other_name",
        "The message is observed on Item 1 from +16465550170, which wrote 'new # for a bit, "
        "save it' on Mar 22, and ORLOV's reply says 'got it ruben', which points to DIAZ. But "
        "DIAZ's own phone saves +16465550170 as 'Eddie P' and holds no message or call with "
        "it. The number's user is not established, so unproven.",
        counter=(("item2", "contact:Eddie P"),),
        direction="other_user",
        reach="The contact is on Item 2, and every assumption of the claim names a channel or "
        "a window, so the retrieval returns no contact entries (it returns contacts only for an "
        "assumption with neither). explain.py's other-user direction lists the names a number "
        "is saved under on every phone and flags one that shares no word with the person.",
    ),
    C(
        "C17",
        1,
        'On March 28, 2026, DIAZ texted ORLOV "keep ur phone on tonight, might need u at 10".',
        "communication",
        False,
        "unproven",
        (
            "DIAZ's SMS account sent the message to ORLOV on Mar 28",
            "DIAZ, not someone else holding Item 2, wrote it",
        ),
        (("item2", "ds_keep"), ("item2", "tc_tito")),
        "literal_handoff",
        "The message is observed, outgoing from Item 2 on Saturday Mar 28. On Friday evening "
        "Item 2 sent DIAZ's aunt 'ma its tito. using ruben's phone this weekend, mine is "
        "broke. dont call my number'. Someone else says he held DIAZ's phone that weekend. "
        "That does not rule DIAZ out, so unproven.",
        counter=(("item2", "tc_tito"),),
        direction="other_user",
        reach="The note is in DIAZ's conversation with his aunt, the evening before the window, "
        "shares no word with the claim and is not the nearest record to it (the window edge is "
        "the Mar 25 'outside'). explain.py's other-user direction reads every message on the "
        "same phone within two days of the claimed one for a hand-off ('using ruben's phone').",
    ),
)

# One line per claim for the signing sheet.
SUMMARY: dict[str, str] = {
    "C01": "Contact 'Pasha' with +17185550111 is on Item 2.",
    "C02": "Nine Telegram rows on Item 2, Mar 1-7 local (two are Mar 8 in UTC).",
    "C03": "Kirill wrote from Item 1 the evening before: 'usin pasha fone til sunday'.",
    "C04": "The outgoing 2-min call was 7:40 p.m. (prints 11:40 PM UTC+0); 11:39 p.m. is incoming.",
    "C05": "Observed; Kemal's lost phone and the 'never used his phone' denial are decoys.",
    "C06": "PASHA is ORLOV, but DIAZ sent the message (both phones).",
    "C07": "Item 1 sent it to +17185550190 on Mar 15, the day after the SEARCH.",
    "C08": "Two days later is Mar 17; it was sent Mar 18.",
    "C09": "Item 1's WhatsApp was quiet everywhere; ORLOV wrote that the app was crashing.",
    "C10": "Translit messages say the boxes are their mother's dishes.",
    "C11": "The shop account's other user names himself: 'hi its kemal from the shop'.",
    "C12": "Friday Mar 20, 'sunday' is Mar 22; the other Sunday and Varick are decoys.",
    "C13": "DIAZ agreed on WhatsApp, then withdrew on Telegram that night.",
    "C14": "The 2:04 p.m. call, 370 s; the 10:05 a.m. one that prints 2:05 PM is a decoy.",
    "C15": "'the paper' fits the Civic's title ('pink slip', 'title') in DIAZ's other thread.",
    "C16": "DIAZ's own phone saves +16465550170 as 'Eddie P'.",
    "C17": "Item 2 sent 'its tito. using ruben's phone this weekend' the evening before.",
}

# Affidavit layout: (page, paragraph parts). A part is plain text or a claim id. Paragraphs are
# numbered from 1 in this order.
AFFIDAVIT: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            "I, Detective L. Moreno of the Metro Auto Crimes Task Force (a fictional agency), make "
            "this affidavit from my training, experience and review of the evidence below.",
        ),
    ),
    (
        1,
        (
            "This affidavit is based on forensic extraction reports for two phones. Item 1 (the "
            '"TARGET PHONE") is an Apple iPhone 14 Pro seized from PAVEL ORLOV ("ORLOV" or '
            '"SUBJECT-1"), also known as "PASHA". Item 2 is a Samsung Galaxy S23 seized from '
            'RUBEN DIAZ ("DIAZ" or "SUBJECT-2").',
        ),
    ),
    (
        1,
        (
            'A confidential source ("CS-1") used the phone number +1 (718) 555-0190 throughout '
            "the period described below.",
        ),
    ),
    (
        1,
        (
            "On March 14, 2026, officers executed a search warrant at DIAZ MUFFLER & EXHAUST, "
            '1180 Halsey Street (the "SEARCH"), and recovered four catalytic converters.',
        ),
    ),
    (
        1,
        (
            "Between February and April 2026, catalytic converters were cut from parked cars in "
            "the area, including six at the Atlantic Avenue park-and-ride at about 11:20 p.m. "
            "on March 9, 2026.",
        ),
    ),
    (1, ("C01",)),
    (1, ("C02", "C03")),
    (2, ("C04",)),
    (2, ("C05", "C06")),
    (2, ("C07", "C08")),
    (2, ("C09",)),
    (2, ("C10",)),
    (3, ("C11",)),
    (3, ("C12", "C13")),
    (3, ("C14", "C15")),
    (3, ("C16",)),
    (3, ("C17",)),
    (
        3,
        (
            "Based on the above, I believe there is probable cause that ORLOV and DIAZ "
            "conspired to receive and sell stolen catalytic converters.",
        ),
    ),
)


# ---------------------------------------------------------------- DRAFT assumption sheet

ORLOV, DIAZ = "person:orlov", "person:diaz"
ITEM1, ITEM2 = "dev:item1", "dev:item2"
ITEM1_SMS = "acct:item1:SMS:+17185550111"  # the TARGET PHONE's own SMS account
CS1_SMS = "acct:item1:SMS:+17185550190"
PASHA_ON_ITEM2 = "acct:item2:SMS:+17185550111"
E0170 = "acct:item1:SMS:+16465550170"
ODET_IG = "acct:item1:Instagram:orlov.detailing"
JR_IG = "acct:item1:Instagram:jr.parts.nyc"

Expect = Literal["pass", "fail", "inconclusive"] | None


def window(start: str, end_exclusive: str, raw: str, tz: str = NY) -> dict[str, str]:
    """Wall-clock [start, end_exclusive) in tz -> the contract's inclusive UTC TimeWindow.

    The same arithmetic as core.audit.assumptions.local_window and the case01 sheet.
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


Q03 = "can u open the bay early tmrw, got 3 to drop"
Q05 = "got 4 more, all hondas. same price?"
Q06 = "need the lift friday after 6"
Q07 = "not now. after the weekend"
Q08 = "all quiet here, dont come by"
Q10 = "коробки у меня, завтра отвезу"
Q11 = "come thru after 9, bring cash"
Q12 = "lot on varick, sunday 9pm"
Q13_ASK = "can u hold the 6 pieces at ur shop til tuesday"
Q13_OK = "ok bring them by after 8"
Q15 = "bring the paper tmrw"
Q16 = "the bushwick guy wants 6 by friday"
Q17 = "keep ur phone on tonight, might need u at 10"

SHEET: tuple[ClaimSpec, ...] = (
    ClaimSpec(
        "C01",
        (
            A(
                "contact_entry",
                P(device_ids=[ITEM2], quoted_text="Pasha", account_ids=[PASHA_ON_ITEM2]),
                "pass",
                "The contact row is observed on Item 2; 'Pasha Tires' is another entry.",
            ),
        ),
    ),
    ClaimSpec(
        "C02",
        (
            A(
                "message_count",
                P(
                    device_ids=[ITEM2],
                    person_ids=[DIAZ, ORLOV],
                    channels=["Telegram"],
                    expected_count=9,
                    count_op="eq",
                    window=window("2026-03-01", "2026-03-08", "Between March 1 and March 7, 2026"),
                ),
                "pass",
                "Nine rows on Item 2, local dates; two of them are on Mar 8 in UTC.",
            ),
        ),
    ),
    ClaimSpec(
        "C03",
        (
            A(
                "sender",
                P(quoted_text=Q03, person_ids=[ORLOV], channels=["SMS"]),
                "pass",
                "Outgoing from Item 1's SMS account (stipulated ORLOV's).",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q03,
                    person_ids=[ORLOV, DIAZ],
                    channels=["SMS"],
                    window=day("2026-03-07", "On March 7, 2026"),
                ),
                "pass",
                "10:15 a.m. EST Mar 7.",
            ),
        ),
        gaps=(
            "That ORLOV himself, not another person holding Item 1, wrote the message is the "
            "device-owner stipulation, not an assumption here; the counter-evidence disputes it.",
        ),
    ),
    ClaimSpec(
        "C04",
        (
            A(
                "record_time",
                P(
                    person_ids=[ORLOV, DIAZ],
                    channels=["call"],
                    device_ids=[ITEM1],
                    duration_s=[90, 150],
                    window=window(
                        "2026-03-09T23:32:00",
                        "2026-03-09T23:48:00",
                        "At about 11:40 p.m. on March 9, 2026",
                    ),
                ),
                "pass",
                "Passes on the 11:39 p.m. call, which is DIAZ calling ORLOV (112 s). The outgoing "
                "two-minute call prints 11:40:12 PM(UTC+0) and was at 7:40 p.m. local.",
            ),
        ),
        gaps=(
            "No template says who placed a call, so 'ORLOV placed' is untested by any check; "
            "the time check matches calls by their parties either way.",
            "'About' is read as eight minutes either side of 11:40 p.m. and 'about two minutes' "
            "as 90 to 150 s.",
        ),
    ),
    ClaimSpec(
        "C05",
        (
            A(
                "sender",
                P(quoted_text=Q05, person_ids=[ORLOV], channels=["SMS"]),
                "pass",
                "Outgoing on Item 1.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q05,
                    person_ids=[ORLOV, DIAZ],
                    channels=["SMS"],
                    window=day("2026-03-11", "On March 11, 2026"),
                ),
                "pass",
                "3:42 p.m. EDT Mar 11, printed 7:42 PM UTC+0.",
            ),
        ),
    ),
    ClaimSpec(
        "C06",
        (
            A(
                "sender",
                P(quoted_text=Q06, person_ids=[ORLOV], channels=["Telegram"]),
                "fail",
                "PASHA is ORLOV (paragraph 2). Both copies are sent by DIAZ's Telegram account "
                "7101002.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q06,
                    person_ids=[ORLOV, DIAZ],
                    channels=["Telegram"],
                    window=day("2026-03-12", "On March 12, 2026"),
                ),
                "pass",
                "5:05 p.m. EDT Mar 12. SUBJECT-2 is DIAZ.",
            ),
        ),
    ),
    ClaimSpec(
        "C07",
        (
            A(
                "sender",
                P(
                    quoted_text=Q07,
                    account_ids=[ITEM1_SMS],
                    device_ids=[ITEM1],
                    channels=["SMS"],
                ),
                "pass",
                "The TARGET PHONE is Item 1 (paragraph 2): its own SMS account sent it.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q07,
                    account_ids=[CS1_SMS],
                    device_ids=[ITEM1],
                    channels=["SMS"],
                    window=day("2026-03-15", "On the day after the SEARCH (March 15, 2026)"),
                ),
                "pass",
                "The SEARCH was Mar 14 (paragraph 4); CS-1 used +17185550190 (paragraph 3). "
                "11:26 a.m. EDT Mar 15.",
            ),
        ),
    ),
    ClaimSpec(
        "C08",
        (
            A(
                "sender",
                P(quoted_text=Q08, person_ids=[DIAZ], channels=["SMS"]),
                "pass",
                "SUBJECT-2 is DIAZ (paragraph 2): outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q08,
                    person_ids=[DIAZ],
                    device_ids=[ITEM1],
                    channels=["SMS"],
                    window=day("2026-03-17", "Two days later (March 17, 2026)"),
                ),
                "fail",
                "Two days after Mar 15 (C07) is Mar 17. The TARGET PHONE received it at 9:10 "
                "a.m. EDT on Mar 18.",
            ),
        ),
        gaps=(
            "'Two days later' is read from the sentence before it (C07). Read from the SEARCH "
            "it would be Mar 16; the message is outside both days.",
        ),
    ),
    ClaimSpec(
        "C09",
        (
            A(
                "no_contact",
                P(
                    person_ids=[ORLOV, DIAZ],
                    channels=["WhatsApp"],
                    window=window(
                        "2026-03-15", "2026-03-19", "from March 15 through March 18, 2026"
                    ),
                ),
                "inconclusive",
                "No rows on either phone, but both reports are curated, so the absence cannot "
                "be shown complete.",
            ),
            A(
                "event",
                P(
                    person_ids=[ORLOV, DIAZ],
                    channels=["WhatsApp"],
                    window=window(
                        "2026-03-15", "2026-03-19", "from March 15 through March 18, 2026"
                    ),
                ),
                None,
                "That ORLOV stopped, and why, is for a reader; Item 1's WhatsApp was quiet in "
                "every conversation and he wrote that the app was crashing.",
            ),
        ),
        gaps=("'After the SEARCH' (Mar 14) only fixes the start; the window carries it.",),
    ),
    ClaimSpec(
        "C10",
        (
            A(
                "sender",
                P(quoted_text=Q10, person_ids=[ORLOV], channels=["Telegram"]),
                "pass",
                "Outgoing on Item 1 to Misha.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q10,
                    person_ids=[ORLOV],
                    channels=["Telegram"],
                    window=day("2026-03-17", "On March 17, 2026"),
                ),
                "pass",
                "6:40 p.m. EDT Mar 17.",
            ),
            A(
                "meaning",
                P(quoted_text=Q10, channels=["Telegram"]),
                None,
                "Whether the boxes are the converters; the thread says they are dishes.",
            ),
        ),
        gaps=("That the other party is ORLOV's brother is not tested (no template for kin).",),
    ),
    ClaimSpec(
        "C11",
        (
            A(
                "sender",
                P(quoted_text=Q11, person_ids=[ORLOV], channels=["Instagram"]),
                "pass",
                "orlov.detailing is an owner account of Item 1 (stipulated ORLOV's).",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q11,
                    person_ids=[ORLOV],
                    account_ids=[JR_IG],
                    channels=["Instagram"],
                    window=day("2026-03-19", "On March 19, 2026"),
                ),
                "pass",
                "6:42 p.m. EDT Mar 19.",
            ),
            A(
                "authorship",
                P(
                    quoted_text=Q11,
                    person_ids=[ORLOV],
                    account_ids=[ODET_IG],
                    channels=["Instagram"],
                ),
                None,
                "The shop account has another user, who names himself on Mar 18.",
            ),
        ),
    ),
    ClaimSpec(
        "C12",
        (
            A(
                "sender",
                P(quoted_text=Q12, person_ids=[DIAZ], channels=["Telegram"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q12,
                    person_ids=[DIAZ, ORLOV],
                    channels=["Telegram"],
                    window=day("2026-03-20", "On Friday, March 20, 2026"),
                ),
                "pass",
                "3:15 p.m. EDT Mar 20.",
            ),
            A(
                "weekday_date",
                P(
                    quoted_text=Q12,
                    channels=["Telegram"],
                    window=day("2026-03-22", "Sunday, March 22, 2026"),
                ),
                "pass",
                "The next Sunday after Friday Mar 20 is Mar 22.",
            ),
        ),
    ),
    ClaimSpec(
        "C13",
        (
            A(
                "sender",
                P(quoted_text=Q13_ASK, person_ids=[ORLOV], channels=["WhatsApp"]),
                "pass",
                "ORLOV's request, outgoing on Item 1.",
            ),
            A(
                "sender",
                P(quoted_text=Q13_OK, person_ids=[DIAZ], channels=["WhatsApp"]),
                "pass",
                "DIAZ's reply, outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q13_OK,
                    person_ids=[DIAZ, ORLOV],
                    channels=["WhatsApp"],
                    window=day("2026-03-21", "On March 21, 2026"),
                ),
                "pass",
                "1:12 p.m. EDT Mar 21.",
            ),
            A(
                "weekday_date",
                P(
                    quoted_text=Q13_ASK,
                    channels=["WhatsApp"],
                    window=day("2026-03-24", "Tuesday, March 24, 2026"),
                ),
                "pass",
                "The next Tuesday after Saturday Mar 21 is Mar 24.",
            ),
            A(
                "meaning",
                P(quoted_text=Q13_OK, channels=["WhatsApp"]),
                None,
                "'ok bring them by after 8' as agreement to hold the pieces.",
            ),
            A(
                "event",
                P(
                    person_ids=[ORLOV, DIAZ],
                    channels=["WhatsApp"],
                    window=day("2026-03-21", "On March 21, 2026"),
                ),
                None,
                "That the agreement was made and stood; it was withdrawn on Telegram that night.",
            ),
        ),
        gaps=("'At his shop' is not tested (no template for a place).",),
    ),
    ClaimSpec(
        "C14",
        (
            A(
                "record_time",
                P(
                    person_ids=[DIAZ, ORLOV],
                    channels=["call"],
                    duration_s=[330, 390],
                    window=window(
                        "2026-03-23T13:57:00",
                        "2026-03-23T14:13:00",
                        "At about 2:05 p.m. on March 23, 2026",
                    ),
                ),
                "pass",
                "The 2:04:30 p.m. call, 370 s, on both phones.",
            ),
        ),
        gaps=(
            "No template says who placed a call; Item 2 logs it as outgoing, as the claim says.",
            "'About' is read as eight minutes either side; 'about six minutes' as 330 to 390 s.",
        ),
    ),
    ClaimSpec(
        "C15",
        (
            A(
                "sender",
                P(quoted_text=Q15, person_ids=[DIAZ], channels=["SMS"]),
                "pass",
                "Outgoing on Item 2.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q15,
                    person_ids=[DIAZ, ORLOV],
                    channels=["SMS"],
                    window=day("2026-03-24", "On March 24, 2026"),
                ),
                "pass",
                "2:30 p.m. EDT Mar 24.",
            ),
            A(
                "meaning",
                P(quoted_text=Q15, channels=["SMS"]),
                None,
                "'the paper' as cash payment; DIAZ's thread with a buyer makes it the Civic's "
                "title.",
            ),
        ),
    ),
    ClaimSpec(
        "C16",
        (
            A(
                "sender",
                P(quoted_text=Q16, account_ids=[E0170], channels=["SMS"]),
                "pass",
                "Incoming on Item 1 from +16465550170.",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q16,
                    person_ids=[ORLOV],
                    account_ids=[E0170],
                    channels=["SMS"],
                    window=day("2026-03-25", "On March 25, 2026"),
                ),
                "pass",
                "4:15 p.m. EDT Mar 25.",
            ),
            A(
                "authorship",
                P(quoted_text=Q16, person_ids=[DIAZ], account_ids=[E0170], channels=["SMS"]),
                None,
                "Who used +16465550170; DIAZ's own phone saves it as 'Eddie P'.",
            ),
        ),
    ),
    ClaimSpec(
        "C17",
        (
            A(
                "sender",
                P(quoted_text=Q17, person_ids=[DIAZ], channels=["SMS"]),
                "pass",
                "Outgoing on Item 2 (stipulated DIAZ's).",
            ),
            A(
                "record_time",
                P(
                    quoted_text=Q17,
                    person_ids=[DIAZ, ORLOV],
                    channels=["SMS"],
                    window=day("2026-03-28", "On March 28, 2026"),
                ),
                "pass",
                "4:10 p.m. EDT Mar 28.",
            ),
        ),
        gaps=(
            "That DIAZ himself, not another person holding Item 2, wrote the message is the "
            "device-owner stipulation, not an assumption here; the counter-evidence disputes it.",
        ),
    ),
)

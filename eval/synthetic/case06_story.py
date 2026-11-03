"""Case06 story. SYNTHETIC: every person, number, handle, place and event here is fictional.

case06 is a held-out set built to case05's design, blind to the step it measures: claims written
the way affidavits are written (defined terms, aliases, relative or approximate times, indirect
speech, references back, roles, numbers in words) beside plain ones, over three phones, with a
wrong reading planted for most claims: a second person with the same first name or nickname, a
second number or account for the same person, a second phone that could be meant, a near-miss
time window, one contact name used on two phones for two people, or similar words in another
thread. eval/synthetic/case06_key.py says, claim by claim, which reading is right, which wrong
candidate the data holds, and what the sheet should name.

This file holds the hand-placed part of the case: people, accounts, devices, contacts and every
message or call a claim depends on, plus seeded background chatter that never touches a thread
between two subjects, the SPARE LINE, the WORK NUMBER or the BROKER. Phone numbers use the
555-01xx range reserved for fiction (area codes 360 and 253). Times are written in US Pacific
local time with pt(); daylight saving starts at 2:00 a.m. on 2025-03-09, the night of the
TRANSFER, when the clocks jump to 3:00 a.m. The hour from 2 to 3 a.m. never happens that night,
so no record is placed in it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

DEVICE_TZ = "America/Los_Angeles"
ZONE = ZoneInfo(DEVICE_TZ)


def pt(local: str) -> datetime:
    """'2025-03-08 23:05:00' as a wall-clock time in Los Angeles -> aware UTC datetime. Never
    called with a time in the 2 a.m. hour of 2025-03-09, which does not exist."""
    naive = datetime.fromisoformat(local)
    aware = naive.replace(tzinfo=ZONE)
    back = aware.astimezone(UTC).astimezone(ZONE).replace(tzinfo=None)
    if back != naive:
        raise ValueError(f"{local} does not exist in {DEVICE_TZ}")
    return aware.astimezone(UTC)


def pacific_offset_min(utc: datetime) -> int:
    off = utc.astimezone(ZONE).utcoffset()
    return int(off.total_seconds() // 60) if off is not None else 0


CASE_START = pt("2025-02-10 00:00:00")
CASE_END = pt("2025-04-01 00:00:00")
T0 = CASE_START - timedelta(days=60)
# SUBJECT B's Telegram name: "Ren C" -> "harborlights" (claim C11)
RENAME_AT = pt("2025-03-12 12:00:00")

# ---------------------------------------------------------------- people (ground truth only)

PEOPLE = {
    "varlow": "Emmett Varlow",
    "coyle": "Renata Coyle",
    "pelloquin": "Duncan Pelloquin",
    "broker": "the BROKER (a buyer, +12535550148 and Telegram 'kelpwise'; Item 1 saves the number "
    "as 'Lars')",
    "petrakis": "Lars Petrakis (Pelloquin's cousin; Item 3 saves him as 'Lars', a second Lars)",
    "tennant": "Skip Tennant (a dock hand; Item 3 saves him as 'Skip', a second Skip)",
    "marchetti": "Duke Marchetti (Coyle's mechanic; Item 2 saves him as 'Duke', a second Duke)",
    "strade": "Emmett Strade (Coyle's brother-in-law; Item 2 saves him as 'Emmett', a second "
    "Emmett)",
    "dunmore": "Rollo Dunmore (the harbormaster; Item 3 saves him as 'Captain')",
    "grebe": "Hollis Grebe (Varlow's foreman at the boatyard)",
    "ostrowski": "Mina Ostrowski (Varlow's partner)",
    "coyle_mom": "Coyle's mother",
    "marsh": "Odile Marsh (Pelloquin's sister)",
    "lindqvist": "Rafe Lindqvist (Pelloquin's fishing friend)",
    "ig_customers": "resale customers on Instagram",
}

# ---------------------------------------------------------------- accounts


@dataclass(frozen=True)
class Acct:
    key: str
    app: str  # SMS, WhatsApp, Signal, Telegram, Instagram
    identifier: str  # phone (E.164), WhatsApp JID, Telegram user id, Instagram username
    person: str  # key into PEOPLE
    # Telegram display names as (valid_from_utc, name); later entries win.
    names: tuple[tuple[datetime, str], ...] = ()

    def name_at(self, at: datetime) -> str | None:
        current = None
        for start, name in self.names:
            if at >= start:
                current = name
        return current


def _phone(n: str, area: str = "360") -> str:
    return f"+1{area}555{n}"


def _wa(n: str, area: str = "360") -> str:
    return f"1{area}555{n}@s.whatsapp.net"


ACCOUNTS: dict[str, Acct] = {
    a.key: a
    for a in [
        # VARLOW (item1 owner); the SPARE LINE is his second number, on no seized phone as an
        # owner account (Items 2 and 3 log it)
        Acct("var_sms", "SMS", _phone("0114"), "varlow"),
        Acct("var_wa", "WhatsApp", _wa("0114"), "varlow"),
        Acct("var_sig", "Signal", _phone("0114"), "varlow"),
        Acct("var_tg", "Telegram", "8820411", "varlow", ((T0, "Em V"),)),
        Acct("spr_sms", "SMS", _phone("0163"), "varlow"),
        # COYLE (item2 owner); saltline.resale_fict is her resale page
        Acct("coy_sms", "SMS", _phone("0127", "253"), "coyle"),
        Acct("coy_wa", "WhatsApp", _wa("0127", "253"), "coyle"),
        Acct("coy_sig", "Signal", _phone("0127", "253"), "coyle"),
        Acct(
            "coy_tg", "Telegram", "8820422", "coyle", ((T0, "Ren C"), (RENAME_AT, "harborlights"))
        ),
        Acct("coy_ig", "Instagram", "saltline.resale_fict", "coyle"),
        # PELLOQUIN (item3 owner), the HAULER; the WORK NUMBER is his work line, not seized
        Acct("pel_sms", "SMS", _phone("0138"), "pelloquin"),
        Acct("pel_wa", "WhatsApp", _wa("0138"), "pelloquin"),
        Acct("pel_tg", "Telegram", "8820433", "pelloquin", ((T0, "Duncan P"),)),
        Acct("wrk_sms", "SMS", _phone("0192"), "pelloquin"),
        # the BROKER: a phone number and the KELPWISE ACCOUNT
        Acct("brk_sms", "SMS", _phone("0148", "253"), "broker"),
        Acct("brk_tg", "Telegram", "8820450", "broker", ((T0, "kelpwise"),)),
        # third parties
        Acct("pet_sms", "SMS", _phone("0173"), "petrakis"),
        Acct("ten_sms", "SMS", _phone("0184"), "tennant"),
        Acct("ten_tg", "Telegram", "8820484", "tennant", ((T0, "Skip"),)),
        Acct("mar_sms", "SMS", _phone("0151", "253"), "marchetti"),
        Acct("mar_wa", "WhatsApp", _wa("0151", "253"), "marchetti"),
        Acct("str_sms", "SMS", _phone("0159", "253"), "strade"),
        Acct("dun_sms", "SMS", _phone("0109"), "dunmore"),
        Acct("gre_sms", "SMS", _phone("0120"), "grebe"),
        Acct("min_sms", "SMS", _phone("0135"), "ostrowski"),
        Acct("min_wa", "WhatsApp", _wa("0135"), "ostrowski"),
        Acct("mom_wa", "WhatsApp", _wa("0146", "253"), "coyle_mom"),
        Acct("ody_wa", "WhatsApp", _wa("0156"), "marsh"),
        Acct("raf_sms", "SMS", _phone("0178"), "lindqvist"),
        Acct("ig1_ig", "Instagram", "tidepool.tackle_fict", "ig_customers"),
        Acct("ig2_ig", "Instagram", "rowboat.rae_fict", "ig_customers"),
        Acct("ig3_ig", "Instagram", "bilgerat.bob_fict", "ig_customers"),
    ]
}

# ---------------------------------------------------------------- devices


@dataclass(frozen=True)
class Device:
    key: str  # also the source id and the report file stem
    evidence_no: str
    owner: str
    label: str
    model: str
    os_version: str
    extraction_type: str  # ExtractionType value
    extraction_label: str  # as the report states it
    extracted_at: datetime
    # how the report prints times: 'utc' (UTC+0), 'local' (the phone's offset on each row) or
    # 'fixed-480' (always UTC-8, the examiner's display setting, so an hour behind the phone
    # once the clocks went forward on 2025-03-09)
    report_tz: str
    owner_accounts: tuple[str, ...]
    contacts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = field(default=())


DEVICES: tuple[Device, ...] = (
    Device(
        key="item1",
        evidence_no="Item 1",
        owner="varlow",
        label="Item 1: Samsung Galaxy Z Flip5 seized from Emmett Varlow",
        model="Samsung Galaxy Z Flip5 (SM-F731U)",
        os_version="Android 14",
        extraction_type="file_system",
        extraction_label="Full File System",
        extracted_at=pt("2025-04-10 10:20:00"),
        report_tz="utc",
        owner_accounts=("var_sms", "var_wa", "var_sig", "var_tg"),
        contacts=(
            ("Ren", (("Phone-Mobile", _phone("0127", "253")),)),  # COYLE
            ("Duke", (("Phone-Mobile", _phone("0138")),)),  # PELLOQUIN's own number (Item 3)
            ("Duke work", (("Phone-Mobile", _phone("0192")),)),  # the WORK NUMBER
            ("Lars", (("Phone-Mobile", _phone("0148", "253")),)),  # the BROKER
            ("Hollis", (("Phone-Mobile", _phone("0120")),)),
            ("Mina", (("Phone-Mobile", _phone("0135")),)),
        ),
    ),
    Device(
        key="item2",
        evidence_no="Item 2",
        owner="coyle",
        label="Item 2: Apple iPhone 12 mini seized from Renata Coyle",
        model="Apple iPhone 12 mini (A2176)",
        os_version="iOS 17.6",
        extraction_type="logical",
        extraction_label="Advanced Logical",
        extracted_at=pt("2025-04-10 15:05:00"),
        report_tz="local",
        owner_accounts=("coy_sms", "coy_wa", "coy_sig", "coy_tg", "coy_ig"),
        contacts=(
            ("Skip", (("Phone-Mobile", _phone("0114")),)),  # VARLOW
            ("Captain", (("Phone-Mobile", _phone("0163")),)),  # the SPARE LINE
            ("Duncan P", (("Phone-Mobile", _phone("0138")),)),  # PELLOQUIN
            ("Duke", (("Phone-Mobile", _phone("0151", "253")),)),  # Duke Marchetti, not PELLOQUIN
            ("Emmett", (("Phone-Mobile", _phone("0159", "253")),)),  # Emmett Strade, not VARLOW
            ("Mom", (("Phone-Mobile", _phone("0146", "253")),)),
        ),
    ),
    Device(
        key="item3",
        evidence_no="Item 3",
        owner="pelloquin",
        label="Item 3: Kyocera DuraForce Ultra 5G seized from Duncan Pelloquin",
        model="Kyocera DuraForce Ultra 5G (E7110)",
        os_version="Android 13",
        extraction_type="logical",
        extraction_label="Logical",
        extracted_at=pt("2025-04-11 09:45:00"),
        report_tz="fixed-480",
        owner_accounts=("pel_sms", "pel_wa", "pel_tg"),
        contacts=(
            ("Emmett V", (("Phone-Mobile", _phone("0114")),)),  # VARLOW
            ("Skip", (("Phone-Mobile", _phone("0184")),)),  # Skip Tennant, not VARLOW
            ("Skip 2", (("Phone-Mobile", _phone("0163")),)),  # the SPARE LINE
            ("Ren C", (("Phone-Mobile", _phone("0127", "253")),)),  # COYLE
            ("Captain", (("Phone-Mobile", _phone("0109")),)),  # Rollo Dunmore, not the SPARE LINE
            ("Lars", (("Phone-Mobile", _phone("0173")),)),  # Lars Petrakis, not the BROKER
            ("Odile", (("Phone-Mobile", _phone("0156")),)),
            ("Rafe", (("Phone-Mobile", _phone("0178")),)),
        ),
    ),
)

# ---------------------------------------------------------------- scripted events


@dataclass(frozen=True)
class Msg:
    key: str
    at: datetime
    sender: str  # Acct key
    to: str  # Acct key
    body: str
    lang: str = "en"
    tag: str | None = None  # examiner tag shown in the report
    skip: tuple[str, ...] = ()  # devices whose report does not hold this record


@dataclass(frozen=True)
class Call:
    key: str
    at: datetime
    caller: str
    callee: str
    duration_s: int
    answered: bool = True
    skip: tuple[str, ...] = ()


EV = "Evidence"  # examiner tag


def _m(
    key: str,
    local: str,
    sender: str,
    to: str,
    body: str,
    tag: str | None = None,
    skip: tuple[str, ...] = (),
) -> Msg:
    return Msg(key, pt(local), sender, to, body, "en", tag, skip)


def _c(
    key: str, local: str, caller: str, callee: str, dur: int, skip: tuple[str, ...] = ()
) -> Call:
    return Call(key, pt(local), caller, callee, dur, True, skip)


SCRIPTED_MESSAGES: tuple[Msg, ...] = (
    # ---- VARLOW <-> COYLE, SMS (items 1 and 2)
    # C01: 8:15 p.m. PST on Feb 19; Item 1 prints it as 2/20/2025 4:15:40 AM(UTC+0)
    _m(
        "vc_dinghy",
        "2025-02-19 20:15:40",
        "var_sms",
        "coy_sms",
        "check the dinghy dock after 9, its quiet",
        EV,
    ),
    _m("vc_dinghy2", "2025-02-19 20:22:05", "coy_sms", "var_sms", "ok"),
    # C19: the exchange fixes "big fish"
    _m(
        "vc_fish",
        "2025-02-24 11:20:15",
        "var_sms",
        "coy_sms",
        "spotted 4 big fish on the north float",
        EV,
    ),
    _m("vc_fish2", "2025-02-24 11:26:40", "coy_sms", "var_sms", "the outboards?", EV),
    _m("vc_fish3", "2025-02-24 11:28:02", "var_sms", "coy_sms", "ya 4 outboards, two are 150s", EV),
    # C20: nothing fixes "the sleeping bags"
    _m("cv_bags", "2025-03-03 14:15:30", "coy_sms", "var_sms", "keep the sleeping bags dry", EV),
    _m("cv_bags2", "2025-03-03 14:31:12", "var_sms", "coy_sms", "will do"),
    # C44
    _m(
        "cv_clear",
        "2025-03-04 09:30:20",
        "coy_sms",
        "var_sms",
        "need the motors out of the boathouse by sat",
        EV,
    ),
    _m("cv_clear2", "2025-03-04 09:44:51", "var_sms", "coy_sms", "ok ill clear it friday", EV),
    # C03: VARLOW wrote it, not COYLE
    _m(
        "vc_cowl",
        "2025-03-06 11:45:25",
        "var_sms",
        "coy_sms",
        "the white cowls are off, come see tonight",
        EV,
    ),
    _m("vc_cowl2", "2025-03-06 11:52:10", "coy_sms", "var_sms", "after 8"),
    # C24: which duke is not fixed; Item 1 prints it as 3/16/2025 2:10:30 AM(UTC+0)
    _m("cv_duke", "2025-03-15 19:10:30", "coy_sms", "var_sms", "duke wants out", EV),
    _m("cv_duke2", "2025-03-15 19:24:02", "var_sms", "coy_sms", "ok"),
    # C43: 'thursday' sent on Tuesday Mar 18 is Mar 20
    _m("vc_fuel", "2025-03-18 10:15:35", "var_sms", "coy_sms", "fuel dock thursday 6pm", EV),
    _m("vc_fuel2", "2025-03-18 10:21:08", "coy_sms", "var_sms", "ok", EV),
    # C21: 6:05 p.m. PDT on Mar 18; Item 1 prints 3/19/2025 1:05:20 AM(UTC+0)
    _m(
        "cv_guard",
        "2025-03-18 18:05:20",
        "coy_sms",
        "var_sms",
        "the guard naps after 2, every night",
        EV,
    ),
    _m("cv_guard2", "2025-03-18 18:12:44", "var_sms", "coy_sms", "good to know"),
    # C38: 6:15 p.m. PDT on Mar 21; Item 1 prints 3/22/2025 1:15:10 AM(UTC+0)
    _m(
        "vc_store",
        "2025-03-21 18:15:10",
        "var_sms",
        "coy_sms",
        "put them in 17, not the boathouse",
        EV,
    ),
    _m("vc_store2", "2025-03-21 18:20:33", "coy_sms", "var_sms", "ok 17"),
    # C23: VARLOW's own number writes to her that morning too (wrong candidate)
    _m("vc_tonight", "2025-03-22 09:10:05", "var_sms", "coy_sms", "call me tonight"),
    # ---- VARLOW <-> COYLE, WhatsApp (items 1 and 2). C32: the only contact Mar 26 to 28
    _m(
        "cv_wa27",
        "2025-03-27 10:20:15",
        "coy_wa",
        "var_wa",
        "dont use texts anymore. only here",
        EV,
    ),
    _m("cv_wa27b", "2025-03-27 10:31:40", "var_wa", "coy_wa", "ok"),
    # ---- VARLOW <-> COYLE, Signal (items 1 and 2)
    # C25: three on the evening of Feb 16, which Item 1 prints as Feb 17 (UTC) ...
    _m("sg_16a", "2025-02-16 17:10:05", "var_sig", "coy_sig", "u free this week?"),
    _m("sg_16b", "2025-02-16 17:25:40", "coy_sig", "var_sig", "tues or wed"),
    _m("sg_16c", "2025-02-16 17:41:12", "var_sig", "coy_sig", "wed then"),
    # ... eight inside Feb 17 to 23, the last two on the evening of Feb 23 (Feb 24 in UTC)
    _m("sg_17", "2025-02-17 09:05:30", "coy_sig", "var_sig", "morning"),
    _m("sg_18", "2025-02-18 12:30:02", "var_sig", "coy_sig", "busy today"),
    _m("sg_19a", "2025-02-19 13:00:44", "coy_sig", "var_sig", "did u talk to the guy"),
    _m("sg_19b", "2025-02-19 15:20:10", "var_sig", "coy_sig", "not yet"),
    _m("sg_20", "2025-02-20 10:12:00", "var_sig", "coy_sig", "tomorrow still good?"),
    _m("sg_21", "2025-02-21 11:00:25", "coy_sig", "var_sig", "call me later"),
    _m("sg_23a", "2025-02-23 16:05:18", "var_sig", "coy_sig", "u see the game"),
    _m("sg_23b", "2025-02-23 16:20:40", "coy_sig", "var_sig", "ugh"),
    # C30: the night of the TRANSFER. Wall-clock 11 p.m. to 4 a.m. is four real hours (07:00 to
    # 11:00 UTC), because 2 to 3 a.m. never came. One message before it ...
    _m("tn00", "2025-03-08 22:40:10", "coy_sig", "var_sig", "u leaving soon?"),
    # ... eleven in it ...
    _m("tn01", "2025-03-08 23:05:20", "var_sig", "coy_sig", "leaving now"),
    _m("tn02", "2025-03-08 23:40:02", "coy_sig", "var_sig", "the side door is open"),
    _m("tn03", "2025-03-09 00:10:45", "var_sig", "coy_sig", "here"),
    _m("tn04", "2025-03-09 00:35:30", "var_sig", "coy_sig", "first 2 are on"),
    _m("tn05", "2025-03-09 01:05:12", "coy_sig", "var_sig", "how many left"),
    _m("tn06", "2025-03-09 01:30:40", "var_sig", "coy_sig", "2 more"),
    _m("tn07", "2025-03-09 01:55:08", "coy_sig", "var_sig", "hurry"),
    # the clocks jump from 2 to 3 a.m. here (10:00 UTC)
    _m("tn08", "2025-03-09 03:12:30", "var_sig", "coy_sig", "all 4 are on, rolling"),
    _m("tn09", "2025-03-09 03:28:15", "coy_sig", "var_sig", "my phone just skipped an hour lol"),
    _m("tn10", "2025-03-09 03:45:50", "var_sig", "coy_sig", "at the barn, unloading"),
    _m("tn11", "2025-03-09 03:58:20", "coy_sig", "var_sig", "text me when ur home"),
    # ... and two after 4 a.m. PDT, outside it
    _m("tn12", "2025-03-09 04:10:05", "var_sig", "coy_sig", "heading home"),
    _m("tn13", "2025-03-09 04:40:30", "coy_sig", "var_sig", "night"),
    # C41: the night of the KITTIWAKE THEFT; Item 1 prints these on Mar 14 (UTC)
    _m(
        "yl_1",
        "2025-03-13 22:58:10",
        "coy_sig",
        "var_sig",
        "parked at the corner of ferrule, ill watch the road",
        EV,
    ),
    _m("yl_2", "2025-03-13 23:09:30", "coy_sig", "var_sig", "patrol car just passed, wait", EV),
    _m("yl_3", "2025-03-13 23:14:05", "coy_sig", "var_sig", "clear, go", EV),
    _m("yl_4", "2025-03-13 23:15:40", "var_sig", "coy_sig", "in", EV),
    _m("yl_5", "2025-03-13 23:41:20", "var_sig", "coy_sig", "out. heading to the barn"),
    # ---- VARLOW <-> PELLOQUIN, SMS (items 1 and 3)
    # C39: PELLOQUIN offers himself, to VARLOW (the trailer is VARLOW's; PELLOQUIN's flatbed
    # pulls it)
    _m(
        "pv_offer",
        "2025-02-14 16:40:20",
        "pel_sms",
        "var_sms",
        "if u ever need a driver to pull ur trailer im around",
    ),
    _m("pv_offer2", "2025-02-14 16:52:05", "var_sms", "pel_sms", "good to know"),
    # C31: 6:25 p.m. PST on Feb 18; Item 1 prints 2/19/2025 2:25:30 AM(UTC+0)
    _m("vp_18a", "2025-02-18 18:25:30", "var_sms", "pel_sms", "u still have the flatbed?", EV),
    _m("vp_18b", "2025-02-18 18:31:02", "pel_sms", "var_sms", "ya why", EV),
    # C05: VARLOW's own number gives the HAULER the SPARE LINE
    _m(
        "vp_new",
        "2025-02-20 12:05:10",
        "var_sms",
        "pel_sms",
        "new number for boat stuff is 360 555 0163. this one stays personal",
        EV,
    ),
    _m("vp_new2", "2025-02-20 12:11:44", "pel_sms", "var_sms", "saved"),
    # C05: VARLOW's own number writes to the HAULER that afternoon too (wrong candidate)
    _m("vp_tmrw", "2025-02-26 15:30:20", "var_sms", "pel_sms", "u around tmrw?"),
    _m("vp_tmrw2", "2025-02-26 15:41:05", "pel_sms", "var_sms", "after 3"),
    # C27: six on Mar 12, Pacific time. Item 3 prints the first two as 11:15 and 11:45 PM on
    # Mar 11 (UTC-8), so its printed Mar 12 holds four.
    _m("v12a", "2025-03-12 00:15:40", "pel_sms", "var_sms", "u up"),
    _m("v12b", "2025-03-12 00:45:10", "var_sms", "pel_sms", "ya cant sleep"),
    _m("v12c", "2025-03-12 10:05:30", "var_sms", "pel_sms", "need the trailer sat"),
    _m("v12d", "2025-03-12 14:30:12", "pel_sms", "var_sms", "it has a flat"),
    # C15: 9:40 p.m. PDT; Item 3 prints 3/12/2025 8:40:15 PM(UTC-8)
    _m(
        "pv_code",
        "2025-03-12 21:40:15",
        "pel_sms",
        "var_sms",
        "barn code is 4417 now, dont lose it",
        EV,
    ),
    _m("v12f", "2025-03-12 21:52:40", "var_sms", "pel_sms", "got it"),
    # C28: the HAULER also texts VARLOW's own number during the SURVEILLANCE (wrong candidate)
    _m("pv_s1", "2025-03-17 13:10:05", "pel_sms", "var_sms", "u see the white truck by the ramp"),
    _m("pv_s2", "2025-03-18 09:40:30", "pel_sms", "var_sms", "same truck today"),
    _m("pv_s3", "2025-03-19 16:15:12", "pel_sms", "var_sms", "its gone"),
    _m("vp_s4", "2025-03-19 16:30:00", "var_sms", "pel_sms", "use the other number"),
    # ---- VARLOW <-> PELLOQUIN, WhatsApp (items 1 and 3)
    # C40: on Item 3 only. The first message fixes which keys: the trailer's
    _m(
        "vw_keys0",
        "2025-02-27 19:12:40",
        "var_wa",
        "pel_wa",
        "left the trailer at ur place. hitch lock and trailer keys are in ur mailbox",
        EV,
        skip=("item1",),
    ),
    _m(
        "vw_keys",
        "2025-02-27 19:20:15",
        "var_wa",
        "pel_wa",
        "keys stay with u, nobody else tows it",
        EV,
        skip=("item1",),
    ),
    _m(
        "vw_keys2",
        "2025-02-27 19:26:40",
        "pel_wa",
        "var_wa",
        "got it, nobody else",
        EV,
        skip=("item1",),
    ),
    # C29: six on Item 3 from Mar 3 through Mar 7; Item 1's report holds only four
    _m("w03", "2025-03-03 08:30:05", "var_wa", "pel_wa", "u up"),
    _m("w04a", "2025-03-04 13:15:20", "pel_wa", "var_wa", "need gas money"),
    _m("w04b", "2025-03-04 13:22:41", "var_wa", "pel_wa", "sending", skip=("item1",)),
    _m("w05", "2025-03-05 10:40:12", "pel_wa", "var_wa", "flat is fixed"),
    _m("w06", "2025-03-06 15:05:33", "var_wa", "pel_wa", "sat night, late"),
    _m("w07", "2025-03-07 12:10:50", "pel_wa", "var_wa", "ok", skip=("item1",)),
    # C17: 4:31 p.m. PDT on Mar 15; Item 1 prints 3/15/2025 11:31:20 PM(UTC+0)
    _m(
        "vw_move",
        "2025-03-15 16:31:20",
        "var_wa",
        "pel_wa",
        "move the trailer behind the barn tonight",
        EV,
    ),
    _m("vw_move2", "2025-03-15 16:40:05", "pel_wa", "var_wa", "ok"),
    # C36: on Item 3 only; Item 1's report does not hold it
    _m("vw_28", "2025-03-28 11:05:40", "var_wa", "pel_wa", "u ok?", skip=("item1",)),
    _m("vw_28b", "2025-03-28 11:20:10", "pel_wa", "var_wa", "dont text me", skip=("item1",)),
    # ---- VARLOW <-> PELLOQUIN, Telegram (items 1 and 3)
    # C22: the thread fixes "the soup cans"
    _m("vt_tanks", "2025-03-03 19:40:10", "pel_tg", "var_tg", "u want the red tanks too?", EV),
    _m(
        "vt_tanks2",
        "2025-03-03 19:46:33",
        "var_tg",
        "pel_tg",
        "ya the soup cans. all 6 fuel tanks",
        EV,
    ),
    _m(
        "vt_soup",
        "2025-03-04 09:20:15",
        "var_tg",
        "pel_tg",
        "bring the soup cans to the boathouse",
        EV,
    ),
    _m("vt_soup2", "2025-03-04 09:31:02", "pel_tg", "var_tg", "all 6?", EV),
    _m("vt_soup3", "2025-03-04 09:33:40", "var_tg", "pel_tg", "all 6 tanks ya", EV),
    # C46: 4:47 a.m. PDT on Mar 9; on Item 3 only (printed 3:47:10 AM(UTC-8))
    _m(
        "pt_barn",
        "2025-03-09 04:47:10",
        "pel_tg",
        "var_tg",
        "all unloaded. trailer is back in the barn",
        EV,
        skip=("item1",),
    ),
    # ---- the WORK NUMBER ("Duke work" on Item 1) <-> VARLOW, SMS (item 1 only)
    _m(
        "wk_1",
        "2025-02-25 07:30:10",
        "wrk_sms",
        "var_sms",
        "on shift till 11, this is the work line",
    ),
    _m("wk_2", "2025-02-25 07:41:00", "var_sms", "wrk_sms", "ok"),
    # ---- the BROKER ("Lars" on Item 1) <-> VARLOW, SMS (item 1)
    _m("bv_1", "2025-02-25 18:10:20", "brk_sms", "var_sms", "still good for 2 big ones?"),
    _m("bv_2", "2025-02-25 18:22:05", "var_sms", "brk_sms", "end of the week"),
    _m("bv_3", "2025-03-10 11:00:40", "brk_sms", "var_sms", "where are the other 2"),
    _m("bv_4", "2025-03-10 11:15:10", "var_sms", "brk_sms", "soon"),
    # ---- the SPARE LINE <-> COYLE, SMS (item 2 only: the SPARE LINE is no seized phone's own)
    # C10: she saves it as "Captain"
    _m(
        "sc_new",
        "2025-02-20 12:20:30",
        "spr_sms",
        "coy_sms",
        "its skip. new number for boat stuff",
        EV,
    ),
    _m("sc_new2", "2025-02-20 12:28:05", "coy_sms", "spr_sms", "saved u as captain lol", EV),
    # C23: the exchange fixes "the twins"
    _m("sc_twins", "2025-03-22 11:40:20", "spr_sms", "coy_sms", "the twins are in 17", EV),
    _m("sc_twins2", "2025-03-22 11:46:55", "coy_sms", "spr_sms", "the 150s?", EV),
    _m(
        "sc_twins3",
        "2025-03-22 11:48:30",
        "spr_sms",
        "coy_sms",
        "ya both 150 outboards, locked up",
        EV,
    ),
    # ---- the SPARE LINE <-> PELLOQUIN, SMS (item 3 only)
    _m("sp_new", "2025-02-20 12:25:00", "spr_sms", "pel_sms", "this is the other number"),
    _m("sp_new2", "2025-02-20 12:30:40", "pel_sms", "spr_sms", "got it"),
    # C05: 7:15 p.m. PST on Wednesday Feb 26
    _m(
        "sp_straps",
        "2025-02-26 19:15:40",
        "spr_sms",
        "pel_sms",
        "bring the long straps and the dolly",
        EV,
    ),
    _m("sp_straps2", "2025-02-26 19:22:10", "pel_sms", "spr_sms", "ok"),
    # C28: one the evening before the SURVEILLANCE ...
    _m("s0", "2025-03-16 21:10:30", "pel_sms", "spr_sms", "u around tmrw"),
    # ... seven from the HAULER to the SPARE LINE from Mar 17 through Mar 19 ...
    _m("s1", "2025-03-17 08:20:10", "pel_sms", "spr_sms", "white truck at the ramp again"),
    _m("r1", "2025-03-17 08:31:00", "spr_sms", "pel_sms", "stay away from there"),
    _m("s2", "2025-03-17 14:05:44", "pel_sms", "spr_sms", "still there"),
    _m("s3", "2025-03-17 19:30:02", "pel_sms", "spr_sms", "gone now"),
    _m("s4", "2025-03-18 07:55:30", "pel_sms", "spr_sms", "back this morning"),
    _m("s5", "2025-03-18 16:40:12", "pel_sms", "spr_sms", "2 guys in it"),
    _m("s6", "2025-03-19 09:15:50", "pel_sms", "spr_sms", "same truck"),
    _m(
        "s7",
        "2025-03-19 18:20:05",
        "pel_sms",
        "spr_sms",
        "leaving the barn alone till its gone",
    ),
    _m("r2", "2025-03-19 18:35:40", "spr_sms", "pel_sms", "good"),
    # ... and one the morning after, outside it
    _m("s8", "2025-03-20 09:05:15", "pel_sms", "spr_sms", "truck is gone today"),
    # ---- COYLE <-> PELLOQUIN, WhatsApp (items 2 and 3)
    # C02
    _m(
        "cp_key",
        "2025-03-04 16:10:25",
        "coy_wa",
        "pel_wa",
        "boathouse key is on the nail in the shed",
        EV,
    ),
    _m("cp_key2", "2025-03-04 16:18:02", "pel_wa", "coy_wa", "got it"),
    # C34: 12:52 a.m. PST, before the hour; 3:05 a.m. PDT, after the jump (Item 3 prints
    # 2:05:10 AM(UTC-8), a time the phone never showed)
    _m("pc_road", "2025-03-09 00:52:30", "pel_wa", "coy_wa", "on the road"),
    _m("cp_hill", "2025-03-09 03:05:10", "coy_wa", "pel_wa", "slow down on the hill"),
    # C26: six on Item 3 from Mar 10 through Mar 14; Item 2 holds a seventh (cw12)
    _m("cw10a", "2025-03-10 10:20:05", "coy_wa", "pel_wa", "u around this week?"),
    _m("cw10b", "2025-03-10 10:31:40", "pel_wa", "coy_wa", "after 4 most days"),
    _m("cw12", "2025-03-12 19:05:30", "coy_wa", "pel_wa", "?", skip=("item3",)),
    _m(
        "cw13",
        "2025-03-13 15:00:12",
        "pel_wa",
        "coy_wa",
        "trailer has a flat, fixing it tonight",
    ),
    # C37: the exchange fixes who set the price
    _m("cp_ask", "2025-03-14 13:00:20", "pel_wa", "coy_wa", "what do i ask for the motors?", EV),
    _m(
        "cp_price",
        "2025-03-14 13:06:45",
        "coy_wa",
        "pel_wa",
        "2200 for the big ones, 900 for the kickers",
        EV,
    ),
    _m("cp_price2", "2025-03-14 13:08:10", "pel_wa", "coy_wa", "ok 2200", EV),
    # ---- COYLE <-> PELLOQUIN, Telegram (items 2 and 3). "Ren C" until Mar 12, then
    # "harborlights"
    # C06: 3:41 a.m. PDT on Mar 9; on Item 3 only (printed 2:41:30 AM(UTC-8))
    _m(
        "cp_barn",
        "2025-03-09 03:41:30",
        "coy_tg",
        "pel_tg",
        "leave the trailer at the barn, not the boathouse",
        EV,
        skip=("item2",),
    ),
    # C11: the last rows under the old name and the first under the new one
    _m("ct_a", "2025-03-11 20:30:10", "coy_tg", "pel_tg", "u up tmrw?", EV),
    _m("ct_a2", "2025-03-11 20:41:05", "pel_tg", "coy_tg", "ya"),
    _m("ct_b", "2025-03-12 16:45:20", "coy_tg", "pel_tg", "changed my name on here", EV),
    _m("ct_b2", "2025-03-12 16:50:02", "pel_tg", "coy_tg", "lol ok"),
    # ---- COYLE <-> PELLOQUIN, SMS (items 2 and 3). C35: the day after the RECOVERY
    _m("cp_took", "2025-03-26 09:15:40", "coy_sms", "pel_sms", "they took the 150s", EV),
    _m("cp_took2", "2025-03-26 09:22:05", "pel_sms", "coy_sms", "i know. dont call me", EV),
    # ---- COYLE <-> the KELPWISE ACCOUNT, Telegram (item 2)
    _m("kc_first", "2025-02-25 19:00:10", "brk_tg", "coy_tg", "heard u might have motors soon"),
    # C47: the Monday after the HARBOR THEFT
    _m(
        "kc_offer",
        "2025-03-03 10:05:10",
        "coy_tg",
        "brk_tg",
        "2 outboards, 90s, both run. 3500 for the pair",
        EV,
    ),
    _m("kc_deal", "2025-03-03 10:40:25", "brk_tg", "coy_tg", "deal, 3k for both, cash", EV),
    _m("kc_ok", "2025-03-03 10:52:02", "coy_tg", "brk_tg", "ok 3k", EV),
    # C47: the BROKER's phone number writes to her that morning too (wrong candidate)
    _m("bc_tg", "2025-03-03 10:30:15", "brk_sms", "coy_sms", "u get my telegram?"),
    _m("bc_tg2", "2025-03-03 10:35:00", "coy_sms", "brk_sms", "ya"),
    # ---- Duke Marchetti ("Duke" on Item 2) <-> COYLE (item 2). Her boat mechanic, plainly: he
    # introduces himself and his shop, and every message from him is about her skiff or his shop
    _m(
        "mc_intro",
        "2025-02-12 10:05:30",
        "mar_sms",
        "coy_sms",
        "this is duke at marchetti marine. ur skiff is in bay 2, pick up anytime",
    ),
    # C39: COYLE asks Item 2's "Duke", not PELLOQUIN, to pull her skiff to the ramp
    _m(
        "cm_recruit",
        "2025-02-15 10:30:05",
        "coy_sms",
        "mar_sms",
        "need someone with a truck to pull my skiff trailer to the ramp sat, u in?",
    ),
    _m("cm_recruit2", "2025-02-15 10:45:40", "mar_sms", "coy_sms", "sure, sat at 9"),
    # C03: similar words, about her skiff
    _m(
        "cm_cowl",
        "2025-03-06 13:20:30",
        "coy_sms",
        "mar_sms",
        "the white cowls are off the skiff, come look",
    ),
    # C12: Item 2's "Duke" sent it, not PELLOQUIN
    _m(
        "mc_lower",
        "2025-03-11 09:40:15",
        "mar_sms",
        "coy_sms",
        "the lower unit is shot, bring the skiff in monday",
        EV,
    ),
    # C24: that morning Item 2's "Duke" wants out of something else, the boat show
    _m(
        "mc_out",
        "2025-03-15 08:30:05",
        "mar_sms",
        "coy_sms",
        "i want out of the boat show booth this year, too much hassle",
    ),
    # C37: similar words from Item 2's "Duke", a repair quote for her skiff
    _m(
        "mc_price",
        "2025-03-14 18:30:10",
        "mar_wa",
        "coy_wa",
        "skiff rebuild quote: 1900 for the big one, 700 for the kicker, parts extra",
    ),
    # C43: similar words from Item 2's "Duke", a skiff appointment
    _m(
        "mc_fuel",
        "2025-03-18 08:05:00",
        "mar_sms",
        "coy_sms",
        "bring the skiff to the fuel dock thursday 8am, ill check the pump",
    ),
    # ---- Emmett Strade ("Emmett" on Item 2) <-> COYLE (item 2). C44's wrong candidate
    _m(
        "cs_kayak",
        "2025-03-04 08:10:20",
        "coy_sms",
        "str_sms",
        "need the kayaks out of the garage by sat",
    ),
    _m("cs_kayak2", "2025-03-04 08:25:00", "str_sms", "coy_sms", "ok saturday morning"),
    # ---- COYLE's mother (item 2). C20's similar words
    _m(
        "cm_bags",
        "2025-03-01 17:00:10",
        "coy_wa",
        "mom_wa",
        "keep the sleeping bags dry, rain all week at the lake",
    ),
    # ---- Hollis Grebe and Mina Ostrowski (item 1)
    # C04's similar words
    _m(
        "vg_wrap",
        "2025-03-10 08:15:30",
        "var_sms",
        "gre_sms",
        "keep the motors wrapped till the paint cures",
    ),
    # C41's similar words
    _m(
        "mv_patrol",
        "2025-03-12 21:30:05",
        "min_sms",
        "var_sms",
        "patrol car just passed our street again, u driving home?",
    ),
    # ---- PELLOQUIN's side (item 3): Lars Petrakis, Skip Tennant, Odile Marsh, Rafe Lindqvist
    # C42: Item 3's "Lars" is his cousin, not the BROKER
    _m(
        "pl_yam",
        "2025-03-16 17:20:30",
        "pel_sms",
        "pet_sms",
        "the two yamahas are ready, come get them saturday",
        EV,
    ),
    _m("pl_yam2", "2025-03-16 17:35:00", "pet_sms", "pel_sms", "thx cuz, my boat misses them"),
    # C09: Item 3's Telegram "Skip" is Skip Tennant
    _m("ts_dock", "2025-03-05 07:45:10", "ten_tg", "pel_tg", "dock 4 needs a hand sat morning", EV),
    _m("ts_dock2", "2025-03-05 07:58:30", "pel_tg", "ten_tg", "cant this sat"),
    # C22's similar words
    _m(
        "od_soup",
        "2025-03-04 08:30:40",
        "ody_wa",
        "pel_wa",
        "bring the soup cans to moms, she needs them for the drive",
    ),
    # C19's similar words
    _m(
        "rf_fish",
        "2025-02-24 18:30:20",
        "raf_sms",
        "pel_sms",
        "4 big fish off the north jetty today, come out sat",
    ),
)

SCRIPTED_CALLS: tuple[Call, ...] = (
    # C13: a 38 s call at 1:09 p.m. PST, which Item 1 prints as 2/21/2025 9:09:30 PM(UTC+0) ...
    _c("cl_0221a", "2025-02-21 13:09:30", "var_sms", "pel_sms", 38),
    # ... and the 9:12 p.m. one, 236 s, which Item 1 prints as 2/22/2025 5:12:40 AM(UTC+0)
    _c("cl_0221b", "2025-02-21 21:12:40", "var_sms", "pel_sms", 236),
    # C14: 3:14 a.m. PDT, 118 s (Item 3 prints 2:14:20 AM(UTC-8)) ...
    _c("cl_0309a", "2025-03-09 03:14:20", "var_sms", "pel_sms", 118),
    # ... and a 31 s call at 4:12 a.m. PDT, inside a window built at UTC-8 for 3:15
    _c("cl_0309b", "2025-03-09 04:12:05", "var_sms", "pel_sms", 31),
    # C16: the WORK NUMBER calls VARLOW (Item 1 only), then PELLOQUIN's own number, 22 s
    _c("cl_wrk", "2025-03-13 23:48:10", "wrk_sms", "var_sms", 68),
    _c("cl_pel0314", "2025-03-14 00:06:30", "pel_sms", "var_sms", 22),
    # C45: the only COYLE-PELLOQUIN call on Mar 16 is 45 s; the ten-minute call is with
    # Item 2's "Duke"
    _c("cl_cp16", "2025-03-16 11:20:10", "coy_sms", "pel_sms", 45),
    _c("cl_cm16", "2025-03-16 14:40:30", "coy_sms", "mar_sms", 612),
    # C48: on Item 3's call log only
    _c("cl_cp22", "2025-03-22 20:05:20", "coy_sms", "pel_sms", 140, skip=("item2",)),
    # C18: on Item 3's call log only
    _c("cl_rec", "2025-03-25 10:55:20", "pel_sms", "var_sms", 95, skip=("item1",)),
)

# Words only scripted messages may use, so background chatter can never create, break or
# crowd a claim: claim quotes, wrong-candidate words, names, places and the case's slang.
# RESERVED_STEMS match at the start of a word ("motor" also bars "motors"); RESERVED_WORDS match
# whole words or phrases only.
RESERVED_STEMS = (
    "sculpin",
    "tidewrack",
    "halyard",
    "gannet",
    "kittiwake",
    "ferrule",
    "wendle",
    "brackwater",
    "varlow",
    "coyle",
    "pelloquin",
    "emmett",
    "renata",
    "duncan",
    "skip",
    "duke",
    "lars",
    "captain",
    "hollis",
    "mina",
    "odile",
    "rafe",
    "kelpwise",
    "harborlight",
    "motor",
    "outboard",
    "yamaha",
    "kicker",
    "trailer",
    "barn",
    "boathouse",
    "dinghy",
    "float",
    "fish",
    "tarp",
    "cowl",
    "strap",
    "dolly",
    "hitch",
    "shed",
    "tank",
    "soup",
    "twin",
    "guard",
    "patrol",
    "corner",
    "fuel",
    "sleeping",
    "wrap",
    "flatbed",
    "chartplot",
    "unload",
    "truck",
    "ramp",
    "deal",
    "cash",
    "price",
    "money",
    "number",
    "phone",
    "telegram",
    "signal",
    "save",
    "sent",
    "sending",
    "watch",
    "road",
    "hill",
    "dock",
    "jetty",
    "kayak",
    "garage",
    "skiff",
    "marchetti",
    "mailbox",
    "lower unit",
    "thursday",
    "friday",
    "white",
    "gray",
    "straps",
    "nail",
)
RESERVED_WORDS = (
    "em",
    "ren",
    "key",
    "keys",
    "cans",
    "sat",
    "dry",
    "bags",
    "big",
    "boat",
    "unit",
    "line",
    "code",
    "gas",
    "flat",
    "door",
    "side door",
    "wants out",
    "come see",
    "come get",
    "u up",
    "u ok",
    "u around",
    "u see",
    "4417",
    "2200",
    "900",
    "3k",
    "3500",
    "150s",
    "90s",
    "17",
    "4",
    "6",
)

# ---------------------------------------------------------------- background chatter

WORK = (
    "running ten min late",
    "the sander needs new pads",
    "bring the moisture meter",
    "gelcoat on the hull is curing",
    "who has the shop van",
    "on my way",
    "be there in 15",
    "sounds good",
    "ok",
    "got it",
    "lunch at noon?",
    "the paint delivery is late again",
    "overtime this weekend if u want it",
    "label the bins by size",
    "compressor is acting up",
    "back in 20",
    "thanks",
    "all good",
    "which bay?",
    "after lunch",
    "can u cover my shift",
    "rain all morning, nothing dries",
    "the crane guy shows at 8",
    "need more sandpaper",
)
FAMILY = (
    "omw",
    "lol",
    "did u eat",
    "heading out",
    "call u later",
    "can u grab milk",
    "kids are asleep",
    "what time?",
    "after 7 works",
    "good morning",
    "how was work",
    "long day",
    "fog all day again",
    "happy bday!!",
    "game tonight?",
    "pick up some bread",
    "see u sunday",
    "love u",
    "text me when u get in",
    "ok",
    "haha true",
    "cant today",
    "maybe this weekend",
    "the ferry wait was awful",
    "nice",
    "yeah",
    "thx",
    "the furnace is out again",
    "dinner at dads?",
    "send pics",
    "the cat got out lol",
    "chowder or pizza",
)
MECHANIC = (
    "the part came in",
    "need a part, maybe tuesday",
    "oil change is 70",
    "ok",
    "thanks",
    "can u come by after 3",
    "the bilge pump is fine",
    "impeller looks worn",
    "be there in 30",
    "the gauge was a loose wire",
)
HARBOR = (
    "slip fees are due monday",
    "power is out on the east finger",
    "small craft advisory tonight",
    "new gate cards next week",
    "ok",
    "will do",
    "thanks",
    "pump out station is working again",
)
IG_CUSTOMER = (
    "is the life jacket still available?",
    "how much for the anchor",
    "can i pick up sunday",
    "do u ship?",
    "thanks, looks great",
    "any more rod holders coming?",
    "what time can i come by",
    "ok see u then",
)
IG_SHOP = (
    "yes, 40",
    "anchor is 25",
    "sunday after noon works",
    "local only, sorry",
    "thank u!",
    "more next week",
    "come by after 10",
    "see u then",
)
POOLS = {"work": WORK, "family": FAMILY, "mechanic": MECHANIC, "harbor": HARBOR}


@dataclass(frozen=True)
class FillerThread:
    device: str
    owner_acct: str
    other_acct: str
    n: int
    pools: tuple[str, ...]  # pool keys, chosen per message; "ig" uses the two Instagram pools
    calls: int = 0  # phone calls; only for SMS threads
    # local wall-clock (start, end) ranges this thread stays out of
    quiet: tuple[tuple[str, str], ...] = ()


# C35's wrong reading (DUKE = Item 2's "Duke") finds nothing on Mar 26 and 27
MARCHETTI_QUIET = (("2025-03-23 00:00:00", "2025-04-01 00:00:00"),)

FILLER_THREADS: tuple[FillerThread, ...] = (
    FillerThread("item1", "var_sms", "gre_sms", 150, ("work",), calls=5),
    FillerThread("item1", "var_sms", "min_sms", 70, ("family",), calls=3),
    FillerThread("item1", "var_wa", "min_wa", 120, ("family",)),
    FillerThread("item2", "coy_sms", "mar_sms", 45, ("mechanic",), calls=3, quiet=MARCHETTI_QUIET),
    FillerThread("item2", "coy_wa", "mar_wa", 40, ("mechanic",), quiet=MARCHETTI_QUIET),
    FillerThread("item2", "coy_sms", "str_sms", 45, ("family",), calls=2),
    FillerThread("item2", "coy_wa", "mom_wa", 140, ("family",)),
    FillerThread("item2", "coy_ig", "ig1_ig", 20, ("ig",)),
    FillerThread("item2", "coy_ig", "ig2_ig", 20, ("ig",)),
    FillerThread("item2", "coy_ig", "ig3_ig", 20, ("ig",)),
    # C33's wrong reading (the BROKER = Item 3's "Lars") finds contact all month
    FillerThread("item3", "pel_sms", "pet_sms", 75, ("family",), calls=5),
    FillerThread("item3", "pel_sms", "ten_sms", 45, ("work",), calls=2),
    # C09: Item 3's Telegram "Skip" is Skip Tennant
    FillerThread("item3", "pel_tg", "ten_tg", 40, ("work",)),
    FillerThread("item3", "pel_sms", "dun_sms", 40, ("harbor",)),
    FillerThread("item3", "pel_wa", "ody_wa", 130, ("family",)),
    FillerThread("item3", "pel_sms", "raf_sms", 55, ("family",), calls=2),
)


def _random_time(rng: random.Random) -> datetime:
    days = (CASE_END - CASE_START).days
    start_local = CASE_START.astimezone(ZONE).replace(tzinfo=None)
    day = start_local + timedelta(days=rng.randrange(days))
    local = day + timedelta(
        hours=rng.choice(range(8, 24)), minutes=rng.randrange(60), seconds=rng.randrange(60)
    )
    return local.replace(tzinfo=ZONE).astimezone(UTC)


def _quiet(t: FillerThread, at: datetime) -> bool:
    return any(pt(a) <= at < pt(b) for a, b in t.quiet)


def make_filler(seed: int) -> tuple[list[Msg], list[Call]]:
    rng = random.Random(seed)  # noqa: S311 - synthetic data, not crypto
    msgs: list[Msg] = []
    calls: list[Call] = []
    for t in FILLER_THREADS:
        made = 0
        while made < t.n:
            at = _random_time(rng)
            burst = min(rng.randint(2, 8), t.n - made)
            sender_is_owner = rng.random() < 0.5
            for _ in range(burst):
                if at >= CASE_END or _quiet(t, at):
                    break
                pool = rng.choice(t.pools)
                if pool == "ig":
                    body = rng.choice(IG_SHOP if sender_is_owner else IG_CUSTOMER)
                else:
                    body = rng.choice(POOLS[pool])
                sender, to = (
                    (t.owner_acct, t.other_acct)
                    if sender_is_owner
                    else (t.other_acct, t.owner_acct)
                )
                msgs.append(Msg(f"f:{t.device}:{t.other_acct}:{made:04d}", at, sender, to, body))
                made += 1
                at += timedelta(seconds=rng.randint(20, 900))
                if rng.random() < 0.6:
                    sender_is_owner = not sender_is_owner
        i = 0
        while i < t.calls:
            at = _random_time(rng)
            if _quiet(t, at):
                continue
            outgoing = rng.random() < 0.5
            caller, callee = (
                (t.owner_acct, t.other_acct) if outgoing else (t.other_acct, t.owner_acct)
            )
            answered = rng.random() < 0.8
            calls.append(
                Call(
                    f"fc:{t.device}:{t.other_acct}:{i:02d}",
                    at,
                    caller,
                    callee,
                    rng.randint(15, 400) if answered else 0,
                    answered,
                )
            )
            i += 1
    return msgs, calls

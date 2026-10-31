"""Case05 story. SYNTHETIC: every person, number, handle, place and event here is fictional.

case05 is a second held-out set built to case04's design, blind: claims written the way
affidavits are written (defined terms, aliases, relative or approximate times, indirect speech,
references back, roles, numbers in words) beside plain ones, over three phones, with a wrong
reading planted for most claims: a second person with the same first name or nickname, a second
number or account for the same person, a second phone that could be meant, a near-miss time
window, one contact name used on two phones for two people, or similar words in another thread.
eval/synthetic/case05_key.py says, claim by claim, which reading is right, which wrong candidate
the data holds, and what the signed sheet should name.

This file holds the hand-placed part of the case: people, accounts, devices, contacts and every
message or call a claim depends on, plus seeded background chatter that never touches a thread
between two subjects, the BURNER or the FENCE. Phone numbers use the 555-01xx range reserved for
fiction (area codes 303, 720 and 970). Times are written in US Mountain local time with mt();
daylight saving ends at 2:00 a.m. on 2025-11-02, the night of the LOCKER BURGLARY, when the
clocks go back to 1:00 a.m. The hour from 1 to 2 a.m. happens twice that night: mt(..., fold=1)
is the second pass (MST, UTC-7), the default the first (MDT, UTC-6).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

DEVICE_TZ = "America/Denver"
ZONE = ZoneInfo(DEVICE_TZ)


def mt(local: str, fold: int = 0) -> datetime:
    """'2025-11-01 23:05:00' as a wall-clock time in Denver -> aware UTC datetime. fold=1 picks
    the second 1 a.m. hour on 2025-11-02 (after the clocks went back)."""
    return datetime.fromisoformat(local).replace(tzinfo=ZONE, fold=fold).astimezone(UTC)


def mountain_offset_min(utc: datetime) -> int:
    off = utc.astimezone(ZONE).utcoffset()
    return int(off.total_seconds() // 60) if off is not None else 0


CASE_START = mt("2025-10-06 00:00:00")
CASE_END = mt("2025-12-01 00:00:00")
T0 = CASE_START - timedelta(days=60)
# SUBJECT-2's Telegram name on the other phones: "Ines V" -> "vee.rides" (claim C10)
RENAME_AT = mt("2025-11-09 12:00:00")

# ---------------------------------------------------------------- people (ground truth only)

PEOPLE = {
    "merrow": "Tobias Merrow",
    "varga": "Ines Varga",
    "odum": "Calvin Odum",
    "fence": "the FENCE (a buyer, +17205550129; Item 2 saves the number as 'Jory')",
    "pask": "Jory Pask (a mechanic; Item 3 saves him as 'Jory', a second Jory)",
    "rusk": "Toby Rusk (Varga's landlord; Item 2 saves him as 'Toby', a second Toby)",
    "calla": "Calla Brightwater (Varga's climbing friend; Item 2 saves her as 'Cal', a second Cal)",
    "ashgrove": "Tamsin Ashgrove (Odum's shift lead; Item 3 saves her as 'T2')",
    "brynn": "Brynn Merrow (Merrow's sister)",
    "pettibone": "Arlo Pettibone (Merrow's brother-in-law)",
    "haldane": "Shep Haldane (Merrow's crew boss)",
    "dorrie": "Dorrie Odum (Odum's sister)",
    "garrity": "Pell Garrity (Odum's friend)",
    "mama_v": "Varga's mother",
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


def _phone(n: str, area: str = "720") -> str:
    return f"+1{area}555{n}"


def _wa(n: str, area: str = "720") -> str:
    return f"1{area}555{n}@s.whatsapp.net"


ACCOUNTS: dict[str, Acct] = {
    a.key: a
    for a in [
        # MERROW (item1 owner); the BURNER is his second number, on no seized phone as an owner
        # account; tm2_tg is a second Telegram account that writes to ODUM from Nov 20 (C09)
        Acct("mer_sms", "SMS", _phone("0134"), "merrow"),
        Acct("mer_wa", "WhatsApp", _wa("0134"), "merrow"),
        Acct("mer_sig", "Signal", _phone("0134"), "merrow"),
        Acct("mer_tg", "Telegram", "6630401", "merrow", ((T0, "Toby M"),)),
        Acct("bur_sms", "SMS", _phone("0186"), "merrow"),
        Acct("tm2_tg", "Telegram", "6630488", "merrow", ((T0, "T.M."),)),
        # VARGA (item2 owner); attic.wheels_fict is her resale page
        Acct("var_sms", "SMS", _phone("0157", "303"), "varga"),
        Acct("var_wa", "WhatsApp", _wa("0157", "303"), "varga"),
        Acct("var_sig", "Signal", _phone("0157", "303"), "varga"),
        Acct("var_tg", "Telegram", "6630402", "varga", ((T0, "Ines V"), (RENAME_AT, "vee.rides"))),
        Acct("var_ig", "Instagram", "attic.wheels_fict", "varga"),
        # ODUM (item3 owner), the COURIER; odw_sms is his work cell, not seized
        Acct("odu_sms", "SMS", _phone("0168"), "odum"),
        Acct("odu_wa", "WhatsApp", _wa("0168"), "odum"),
        Acct("odu_tg", "Telegram", "6630403", "odum", ((T0, "Calvin"),)),
        Acct("odw_sms", "SMS", _phone("0153"), "odum"),
        # third parties
        Acct("fen_sms", "SMS", _phone("0129"), "fence"),
        Acct("jor_sms", "SMS", _phone("0181"), "pask"),
        Acct("rus_sms", "SMS", _phone("0139", "303"), "rusk"),
        Acct("cal_sms", "SMS", _phone("0161", "303"), "calla"),
        Acct("cal_wa", "WhatsApp", _wa("0161", "303"), "calla"),
        Acct("ash_sms", "SMS", _phone("0143"), "ashgrove"),
        Acct("bry_sms", "SMS", _phone("0117"), "brynn"),
        Acct("arl_sms", "SMS", _phone("0125", "970"), "pettibone"),
        Acct("arl_wa", "WhatsApp", _wa("0125", "970"), "pettibone"),
        Acct("shp_sms", "SMS", _phone("0131"), "haldane"),
        Acct("dor_wa", "WhatsApp", _wa("0179"), "dorrie"),
        Acct("pel_sms", "SMS", _phone("0175"), "garrity"),
        Acct("mam_wa", "WhatsApp", _wa("0193", "303"), "mama_v"),
        Acct("ig1_ig", "Instagram", "loamgravel22_fict", "ig_customers"),
        Acct("ig2_ig", "Instagram", "fatbike.fran_fict", "ig_customers"),
        Acct("ig3_ig", "Instagram", "spokes.n.sprockets_fict", "ig_customers"),
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
    # how the report prints times: 'local' (the phone's offset on each row), 'utc' (UTC+0) or
    # 'fixed-420' (always UTC-7, the examiner's display setting, so an hour behind the phone
    # until the clocks went back on 2025-11-02)
    report_tz: str
    owner_accounts: tuple[str, ...]
    contacts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = field(default=())


DEVICES: tuple[Device, ...] = (
    Device(
        key="item1",
        evidence_no="Item 1",
        owner="merrow",
        label="Item 1: Samsung Galaxy A54 seized from Tobias Merrow",
        model="Samsung Galaxy A54 5G (SM-A546U)",
        os_version="Android 15",
        extraction_type="file_system",
        extraction_label="Full File System",
        extracted_at=mt("2025-12-04 10:20:00"),
        report_tz="local",
        owner_accounts=("mer_sms", "mer_wa", "mer_sig", "mer_tg"),
        contacts=(
            ("Ines V", (("Phone-Mobile", _phone("0157", "303")),)),
            ("Cal", (("Phone-Mobile", _phone("0153")),)),  # ODUM's work cell
            ("Cal 2", (("Phone-Mobile", _phone("0168")),)),  # ODUM's own number (Item 3)
            ("Shep", (("Phone-Mobile", _phone("0131")),)),
            ("Brynn", (("Phone-Mobile", _phone("0117")),)),
            ("Arlo", (("Phone-Mobile", _phone("0125", "970")),)),
        ),
    ),
    Device(
        key="item2",
        evidence_no="Item 2",
        owner="varga",
        label="Item 2: Apple iPhone 13 seized from Ines Varga",
        model="Apple iPhone 13 (A2482)",
        os_version="iOS 18.6",
        extraction_type="logical",
        extraction_label="Advanced Logical",
        extracted_at=mt("2025-12-04 15:05:00"),
        report_tz="utc",
        owner_accounts=("var_sms", "var_wa", "var_sig", "var_tg", "var_ig"),
        contacts=(
            ("Tobias", (("Phone-Mobile", _phone("0134")),)),  # MERROW
            ("T2", (("Phone-Mobile", _phone("0186")),)),  # the BURNER
            ("Calvin O", (("Phone-Mobile", _phone("0168")),)),  # ODUM
            ("Cal", (("Phone-Mobile", _phone("0161", "303")),)),  # Calla, not ODUM
            ("Toby", (("Phone-Mobile", _phone("0139", "303")),)),  # Toby Rusk, not MERROW
            ("Jory", (("Phone-Mobile", _phone("0129")),)),  # the FENCE
            ("Mama", (("Phone-Mobile", _phone("0193", "303")),)),
        ),
    ),
    Device(
        key="item3",
        evidence_no="Item 3",
        owner="odum",
        label="Item 3: OnePlus Nord N30 seized from Calvin Odum",
        model="OnePlus Nord N30 5G (CPH2513)",
        os_version="Android 14",
        extraction_type="logical",
        extraction_label="Logical",
        extracted_at=mt("2025-12-05 09:45:00"),
        report_tz="fixed-420",
        owner_accounts=("odu_sms", "odu_wa", "odu_tg"),
        contacts=(
            ("Toby", (("Phone-Mobile", _phone("0134")),)),  # MERROW here
            ("Toby work", (("Phone-Mobile", _phone("0186")),)),  # the BURNER
            ("Ines", (("Phone-Mobile", _phone("0157", "303")),)),
            ("T2", (("Phone-Mobile", _phone("0143")),)),  # Tamsin Ashgrove, not the BURNER
            ("Jory", (("Phone-Mobile", _phone("0181")),)),  # Jory Pask, not the FENCE
            ("Dorrie", (("Phone-Mobile", _phone("0179")),)),
            ("Pell", (("Phone-Mobile", _phone("0175")),)),
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
    fold: int = 0,
) -> Msg:
    return Msg(key, mt(local, fold), sender, to, body, "en", tag, skip)


def _c(
    key: str, local: str, caller: str, callee: str, dur: int, skip: tuple[str, ...] = ()
) -> Call:
    return Call(key, mt(local), caller, callee, dur, True, skip)


SCRIPTED_MESSAGES: tuple[Msg, ...] = (
    # ---- MERROW <-> VARGA, SMS (items 1 and 2)
    # C39: VARGA offers herself
    _m(
        "mv_page",
        "2025-10-07 19:40:12",
        "var_sms",
        "mer_sms",
        "if u ever have bikes to move i can list them on my page",
    ),
    _m("mv_page2", "2025-10-07 19:52:30", "mer_sms", "var_sms", "good to know"),
    # C01: 7:25 p.m. MDT on Oct 9; Item 2 prints it as 10/10/2025 1:25:10 AM(UTC+0)
    _m(
        "mv_cam",
        "2025-10-09 19:25:10",
        "mer_sms",
        "var_sms",
        "back row at quillbarrow has no cameras",
        EV,
    ),
    _m(
        "mv_cam2",
        "2025-10-09 19:31:44",
        "var_sms",
        "mer_sms",
        "good. my cousin says the cage is back there too",
    ),
    # C19: the exchange fixes "tall ones"
    _m(
        "mv_tall",
        "2025-10-14 12:40:10",
        "mer_sms",
        "var_sms",
        "found 6 tall ones in the back row",
        EV,
    ),
    _m("mv_tall2", "2025-10-14 12:47:05", "var_sms", "mer_sms", "the emtbs?", EV),
    _m(
        "mv_tall3",
        "2025-10-14 12:49:31",
        "mer_sms",
        "var_sms",
        "ya electric mountain bikes, all 6",
        EV,
    ),
    # C20: 8:30 p.m. MST on Nov 3; Item 2 prints 11/4/2025 3:30:25 AM(UTC+0). Nothing fixes it.
    _m(
        "mv_cold",
        "2025-11-03 20:30:25",
        "mer_sms",
        "var_sms",
        "the cold ones are in the garage",
        EV,
    ),
    _m("mv_cold2", "2025-11-03 20:41:02", "var_sms", "mer_sms", "ok"),
    # C27: six on Nov 14 local time; the last two are Nov 15 in UTC
    _m("mv_14a", "2025-11-14 10:05:12", "var_sms", "mer_sms", "u up?"),
    _m("mv_14b", "2025-11-14 10:20:40", "mer_sms", "var_sms", "ya"),
    _m("mv_14c", "2025-11-14 13:30:05", "var_sms", "mer_sms", "still tonight?"),
    _m("mv_14d", "2025-11-14 15:45:22", "mer_sms", "var_sms", "still on"),
    _m("mv_14e", "2025-11-14 19:15:08", "var_sms", "mer_sms", "be careful"),
    _m("mv_14f", "2025-11-14 20:50:33", "mer_sms", "var_sms", "going dark for a bit"),
    # C23: MERROW's own number writes to her that morning too (wrong candidate)
    _m("mv_later", "2025-11-16 09:30:00", "mer_sms", "var_sms", "call me later"),
    # C44
    _m(
        "vm_move",
        "2025-11-18 10:30:20",
        "var_sms",
        "mer_sms",
        "need the road bikes out of unit 41 by thurs",
        EV,
    ),
    _m("vm_move2", "2025-11-18 10:52:44", "mer_sms", "var_sms", "ok ill move them tonight", EV),
    # C24: which "cal" is not fixed
    _m("vm_nerv", "2025-11-21 20:20:10", "var_sms", "mer_sms", "cal is getting nervous", EV),
    _m("vm_nerv2", "2025-11-21 20:31:55", "mer_sms", "var_sms", "ok"),
    # ---- MERROW <-> VARGA, Signal (items 1 and 2)
    # C25: three on the evening of Oct 12 (Oct 13 in UTC), outside the local window ...
    _m("sg00a", "2025-10-12 19:10:05", "mer_sig", "var_sig", "free this week?"),
    _m("sg00b", "2025-10-12 19:25:40", "var_sig", "mer_sig", "tues after 12"),
    _m("sg00c", "2025-10-12 19:40:12", "mer_sig", "var_sig", "k"),
    # ... seven inside it, the last two on the evening of Oct 19 (Oct 20 in UTC)
    _m("sg01", "2025-10-13 10:05:30", "var_sig", "mer_sig", "did u talk to my cousin"),
    _m("sg02", "2025-10-13 10:30:02", "mer_sig", "var_sig", "not yet"),
    _m(
        "sg03", "2025-10-15 15:00:44", "var_sig", "mer_sig", "he says most of the back row is empty"
    ),
    _m("sg04", "2025-10-15 15:20:10", "mer_sig", "var_sig", "good"),
    _m("sg05", "2025-10-17 11:00:25", "var_sig", "mer_sig", "call me tonight"),
    _m("sg06", "2025-10-19 19:05:18", "mer_sig", "var_sig", "u see the score"),
    _m("sg07", "2025-10-19 19:20:40", "var_sig", "mer_sig", "ugh"),
    # C30: the night of the LOCKER BURGLARY. Wall-clock 11 p.m. to 3 a.m. is five real hours
    # (05:00 to 10:00 UTC), because 1 to 2 a.m. came twice. Twelve messages fall in it ...
    _m("sn01", "2025-11-01 23:05:10", "mer_sig", "var_sig", "at the gate"),
    _m("sn02", "2025-11-01 23:30:42", "var_sig", "mer_sig", "cousin says the cameras reset at 11"),
    _m("sn03", "2025-11-01 23:55:03", "mer_sig", "var_sig", "in"),
    _m("sn04", "2025-11-02 00:20:30", "var_sig", "mer_sig", "?"),
    _m("sn05", "2025-11-02 00:45:12", "mer_sig", "var_sig", "cage is open"),
    # the first 1 a.m. hour (MDT, 07:00 to 08:00 UTC)
    _m("sn06", "2025-11-02 01:10:20", "mer_sig", "var_sig", "first 6 are in the van"),
    _m("sn07", "2025-11-02 01:40:05", "var_sig", "mer_sig", "go faster"),
    # the second 1 a.m. hour (MST, 08:00 to 09:00 UTC). C17: "last two are in the van"
    _m(
        "sn08",
        "2025-11-02 01:15:33",
        "var_sig",
        "mer_sig",
        "my clock just went back an hour lol",
        fold=1,
    ),
    _m(
        "sn09",
        "2025-11-02 01:34:50",
        "mer_sig",
        "var_sig",
        "last two are in the van, rolling soon",
        EV,
        fold=1,
    ),
    _m("sn10", "2025-11-02 01:50:11", "var_sig", "mer_sig", "ok", fold=1),
    _m("sn11", "2025-11-02 02:20:40", "mer_sig", "var_sig", "out. heading to the quarry"),
    _m("sn12", "2025-11-02 02:45:15", "var_sig", "mer_sig", "text me when ur home"),
    # ... and one after 3 a.m. MST, outside it
    _m("sn13", "2025-11-02 03:20:02", "mer_sig", "var_sig", "home"),
    # C32: the only contact Nov 22 to 24 is on Signal
    _m(
        "sg_only",
        "2025-11-23 16:10:20",
        "mer_sig",
        "var_sig",
        "dont text the old way. only here from now",
        EV,
    ),
    _m("sg_only2", "2025-11-23 16:15:48", "var_sig", "mer_sig", "ok"),
    # ---- MERROW <-> ODUM, SMS (items 1 and 3)
    # C31: 12:30 a.m. MDT on Oct 23; Item 3 prints 10/22/2025 11:30:15 PM(UTC-7)
    _m("mo_keys", "2025-10-23 00:30:15", "mer_sms", "odu_sms", "u up? need the van keys", EV),
    _m("mo_keys2", "2025-10-23 00:40:02", "odu_sms", "mer_sms", "under the mat"),
    # C15: 7:45 p.m. MDT; Item 3 prints 10/24/2025 6:45:30 PM(UTC-7)
    _m(
        "mo_trailer",
        "2025-10-24 19:45:30",
        "mer_sms",
        "odu_sms",
        "need u next saturday, bring the trailer",
        EV,
    ),
    _m("mo_trailer2", "2025-10-24 19:52:10", "odu_sms", "mer_sms", "ok"),
    # C43: 'thursday' sent on Tuesday Oct 28 is Oct 30
    _m(
        "mo_meet",
        "2025-10-28 12:05:40",
        "mer_sms",
        "odu_sms",
        "grain elevator lot thursday 7pm",
        EV,
    ),
    _m("mo_meet2", "2025-10-28 12:11:15", "odu_sms", "mer_sms", "bet", EV),
    # C28: ODUM also texts MERROW's own number that week (wrong candidate)
    _m("om_game", "2025-10-28 20:30:05", "odu_sms", "mer_sms", "u see the game"),
    _m("om_game2", "2025-10-28 20:44:30", "mer_sms", "odu_sms", "brutal"),
    # C04: MERROW's own number writes to the COURIER that day too (wrong candidate)
    _m("mo_light", "2025-10-30 16:12:50", "mer_sms", "odu_sms", "did u fix the van light"),
    _m("mo_light2", "2025-10-30 16:20:31", "odu_sms", "mer_sms", "ya"),
    # C06: the nearest exchange on the Tuesday after; the claimed words are in no record
    _m("mo_work", "2025-11-04 12:10:05", "mer_sms", "odu_sms", "u at work?"),
    _m("mo_work2", "2025-11-04 12:20:44", "odu_sms", "mer_sms", "till 6"),
    # C38: MERROW set the time; ODUM's reply holds similar words
    _m("mo_fri", "2025-11-13 19:40:10", "mer_sms", "odu_sms", "friday 9:30, back door", EV),
    _m("mo_fri2", "2025-11-13 19:44:52", "odu_sms", "mer_sms", "9:30 back door works", EV),
    # C36: on Item 3 only; Item 1's report does not hold it
    _m(
        "mo_good",
        "2025-11-22 13:15:30",
        "mer_sms",
        "odu_sms",
        "u good? stay off the main roads",
        skip=("item1",),
    ),
    # ---- MERROW <-> ODUM, Telegram (items 1 and 3)
    _m("mt_first", "2025-10-20 18:00:10", "mer_tg", "odu_tg", "this is me on here"),
    _m("mt_first2", "2025-10-20 18:05:44", "odu_tg", "mer_tg", "cool"),
    # C22: the thread fixes "pizzas"
    _m("mt_bat", "2025-11-03 19:15:20", "odu_tg", "mer_tg", "do the batteries come off those", EV),
    _m(
        "mt_bat2",
        "2025-11-03 19:20:02",
        "mer_tg",
        "odu_tg",
        "ya pop em off. on here we call them pizzas",
        EV,
    ),
    _m(
        "mt_pizza",
        "2025-11-04 18:40:20",
        "mer_tg",
        "odu_tg",
        "grab the pizzas from the container",
        EV,
    ),
    _m("mt_pizza2", "2025-11-04 18:45:33", "odu_tg", "mer_tg", "all 11?", EV),
    _m("mt_pizza3", "2025-11-04 18:46:58", "mer_tg", "odu_tg", "all 11 batteries ya", EV),
    # C29: five on Item 3 from Nov 10 through Nov 13; Item 1's report holds only three
    _m("mt_10a", "2025-11-10 09:30:05", "mer_tg", "odu_tg", "morning"),
    _m("mt_10b", "2025-11-10 09:41:30", "odu_tg", "mer_tg", "whats good"),
    _m("mt_11", "2025-11-11 14:20:12", "mer_tg", "odu_tg", "friday still?", skip=("item1",)),
    _m("mt_12", "2025-11-12 20:05:40", "odu_tg", "mer_tg", "who has the spare key"),
    _m("mt_13", "2025-11-13 11:10:55", "odu_tg", "mer_tg", "?", skip=("item1",)),
    # C47
    _m(
        "mt_pay",
        "2025-11-16 14:20:15",
        "mer_tg",
        "odu_tg",
        "sent u 400 for friday, check ur bank",
        EV,
    ),
    _m("mt_pay2", "2025-11-16 14:41:03", "odu_tg", "mer_tg", "got the 400, thx", EV),
    # C09: a second Telegram account writes to ODUM from Nov 20 (on Item 3 only: it is not an
    # account of Item 1)
    _m(
        "tm_new",
        "2025-11-20 10:00:30",
        "tm2_tg",
        "odu_tg",
        "new acct. its toby. the old one is done",
        EV,
    ),
    _m("tm_new2", "2025-11-20 10:06:12", "odu_tg", "tm2_tg", "ok"),
    _m("tm_3", "2025-11-25 21:00:40", "tm2_tg", "odu_tg", "u hear anything"),
    _m("tm_4", "2025-11-25 21:15:05", "odu_tg", "tm2_tg", "nothing"),
    # ---- ODUM's work cell ("Cal" on Item 1) <-> MERROW, SMS (item 1)
    _m("wk_cell", "2025-10-08 11:00:20", "mer_sms", "odw_sms", "this ur work cell?"),
    _m(
        "wk_cell2",
        "2025-10-08 11:14:05",
        "odw_sms",
        "mer_sms",
        "ya the warehouse one. my own is the other number",
    ),
    # ---- the BURNER <-> ODUM, SMS (item 3 only: the BURNER is no seized phone's account)
    _m(
        "b_new3",
        "2025-10-26 17:00:10",
        "bur_sms",
        "odu_sms",
        "its toby. new number, use this one for work stuff",
        EV,
    ),
    _m("b_new3b", "2025-10-26 17:04:40", "odu_sms", "bur_sms", "saved"),
    # C28: from Monday Oct 27 through Friday Oct 31 the COURIER sends the BURNER five texts
    _m("b27a", "2025-10-27 09:10:22", "bur_sms", "odu_sms", "u free sat night?"),
    _m("b27b", "2025-10-27 09:20:05", "odu_sms", "bur_sms", "ya"),
    _m("b28a", "2025-10-28 18:00:40", "odu_sms", "bur_sms", "how many we talking"),
    _m("b28b", "2025-10-28 18:05:11", "bur_sms", "odu_sms", "11 maybe more"),
    _m("b29a", "2025-10-29 12:30:30", "odu_sms", "bur_sms", "need gas money for the ride"),
    _m("b29b", "2025-10-29 12:40:02", "bur_sms", "odu_sms", "i got u"),
    # C04: 6:50 p.m. MDT on Oct 30; Item 3 prints 5:50:40 PM(UTC-7)
    _m(
        "b_gate",
        "2025-10-30 18:50:40",
        "bur_sms",
        "odu_sms",
        "gate code is 2291, use the side lane",
        EV,
    ),
    _m("b_gate2", "2025-10-30 18:55:15", "odu_sms", "bur_sms", "ok"),
    _m("b31a", "2025-10-31 21:15:08", "odu_sms", "bur_sms", "what time tmrw"),
    _m("b31b", "2025-10-31 21:20:44", "bur_sms", "odu_sms", "11. side lane"),
    # the next day (Saturday), outside the five days
    _m("ob_here", "2025-11-01 22:55:30", "odu_sms", "bur_sms", "here"),
    # ---- the BURNER <-> VARGA, SMS (item 2 only)
    _m("b_new2", "2025-10-26 17:02:30", "bur_sms", "var_sms", "its toby, new number. save it", EV),
    _m("b_new2b", "2025-10-26 17:10:05", "var_sms", "bur_sms", "saved as T2", EV),
    # C23: the exchange fixes "the 4 skinnies"
    _m("b_skin", "2025-11-16 11:05:30", "bur_sms", "var_sms", "the 4 skinnies are at the dock", EV),
    _m("b_skin2", "2025-11-16 11:12:14", "var_sms", "bur_sms", "the pindlewick road bikes?", EV),
    _m(
        "b_skin3",
        "2025-11-16 11:14:40",
        "bur_sms",
        "var_sms",
        "ya the carbon ones from friday, all 4",
        EV,
    ),
    # ---- VARGA <-> ODUM, WhatsApp (items 2 and 3)
    _m("vw_code", "2025-10-21 14:05:30", "var_wa", "odu_wa", "unit 41, code is 7719", EV),
    _m("vw_code2", "2025-10-21 14:09:12", "odu_wa", "var_wa", "got it"),
    # C41: 11:20 p.m. MDT on Friday Oct 31; Item 2 prints 11/1/2025 5:20:30 AM(UTC+0)
    _m(
        "vw_lock",
        "2025-10-31 23:20:30",
        "var_wa",
        "odu_wa",
        "start with 12 and 14, then the cage",
        EV,
    ),
    _m("vw_lock2", "2025-10-31 23:26:05", "odu_wa", "var_wa", "got it"),
    # C34: in the first 1 a.m. hour (MDT), not the second
    _m(
        "ow_full",
        "2025-11-02 01:25:40",
        "odu_wa",
        "var_wa",
        "the van is full, cant fit the boots",
    ),
    # C46: 5:48 a.m. MST; on Item 3 only, Item 2's report does not hold it
    _m(
        "ow_yard",
        "2025-11-02 05:48:20",
        "odu_wa",
        "var_wa",
        "moved it. van is back at the yard",
        EV,
        skip=("item2",),
    ),
    # C40: on Item 3 only
    _m(
        "vw_mkt",
        "2025-11-03 12:15:30",
        "var_wa",
        "odu_wa",
        "u handle marketplace, i do insta",
        EV,
        skip=("item2",),
    ),
    _m(
        "vw_mkt2",
        "2025-11-03 12:22:04",
        "odu_wa",
        "var_wa",
        "ok i got marketplace",
        EV,
        skip=("item2",),
    ),
    # C37: the exchange fixes who set the price
    _m(
        "vw_price0",
        "2025-11-05 13:00:15",
        "odu_wa",
        "var_wa",
        "what do i ask for the red ebikes on marketplace?",
        EV,
    ),
    _m("vw_price", "2025-11-05 13:06:30", "var_wa", "odu_wa", "1400 each, dont go under 1200", EV),
    _m("vw_price2", "2025-11-05 13:08:02", "odu_wa", "var_wa", "ok 1400", EV),
    # C35: contact on Nov 15 and Nov 16
    _m("vw_15a", "2025-11-15 11:00:10", "odu_wa", "var_wa", "u see the news"),
    _m("vw_15b", "2025-11-15 11:10:44", "var_wa", "odu_wa", "stay home today"),
    _m("vw_16", "2025-11-16 19:30:05", "odu_wa", "var_wa", "any word?"),
    # ---- VARGA <-> ODUM, SMS (items 2 and 3)
    # C21: VARGA wrote it, not ODUM
    _m(
        "vo_larch",
        "2025-11-12 17:10:45",
        "var_sms",
        "odu_sms",
        "the shop on larch closes at 9 on fridays",
        EV,
    ),
    _m("vo_larch2", "2025-11-12 17:16:20", "odu_sms", "var_sms", "ok noted"),
    # ---- VARGA <-> ODUM, Telegram (items 2 and 3). "Ines V" until Nov 9, then "vee.rides"
    _m("vt_first", "2025-10-15 20:10:30", "var_tg", "odu_tg", "hey its ines, toby gave me ur name"),
    _m("vt_first2", "2025-10-15 20:15:02", "odu_tg", "var_tg", "hey"),
    _m("vt_where", "2025-11-02 03:20:15", "odu_tg", "var_tg", "where do i put the van"),
    # C05: 3:40 a.m. MST; on Item 3 only, Item 2's report does not hold it
    _m(
        "vt_park",
        "2025-11-02 03:40:15",
        "var_tg",
        "odu_tg",
        "park it behind the feed store till light",
        EV,
        skip=("item2",),
    ),
    # C26: five on Item 3 from Nov 3 through Nov 9; Item 2 holds a sixth (vt_07)
    _m("vt_03a", "2025-11-03 09:00:40", "var_tg", "odu_tg", "u sleep at all?"),
    _m("vt_03b", "2025-11-03 09:12:15", "odu_tg", "var_tg", "barely"),
    _m("vt_06a", "2025-11-06 14:00:05", "odu_tg", "var_tg", "any buyers yet"),
    _m("vt_06b", "2025-11-06 14:20:30", "var_tg", "odu_tg", "2 so far"),
    _m("vt_07", "2025-11-07 21:05:12", "var_tg", "odu_tg", "?", skip=("item3",)),
    _m("vt_08", "2025-11-08 19:30:22", "var_tg", "odu_tg", "busy sunday, dont call"),
    # C10: the first rows under the new name
    _m("vt_10", "2025-11-10 16:45:10", "var_tg", "odu_tg", "new name on here, same me"),
    _m("vt_10b", "2025-11-10 16:50:33", "odu_tg", "var_tg", "lol ok"),
    # ---- the FENCE ("Jory" on Item 2) <-> VARGA, SMS (item 2)
    _m(
        "fe01",
        "2025-11-09 15:20:10",
        "fen_sms",
        "var_sms",
        "heard u have ebikes. 2 each for the big ones",
    ),
    _m("fe02", "2025-11-09 15:31:40", "var_sms", "fen_sms", "maybe. how many u want"),
    _m("fe03", "2025-11-09 15:35:02", "fen_sms", "var_sms", "all of them if theyre clean"),
    _m("fe04", "2025-11-17 10:00:30", "fen_sms", "var_sms", "still on for thurs?"),
    _m("fe05", "2025-11-17 10:20:12", "var_sms", "fen_sms", "not now"),
    # ---- Calla ("Cal" on Item 2) <-> VARGA (item 2)
    _m(
        "ca_kayak",
        "2025-11-05 19:00:10",
        "cal_wa",
        "var_wa",
        "1400 each for the kayaks? no way lol",
    ),
    # C03: the blue ones are Calla's kayak paddles
    _m(
        "ca_blue",
        "2025-11-06 10:15:20",
        "cal_wa",
        "var_wa",
        "the blue ones fit in my hatchback",
        EV,
    ),
    _m("ca_blue2", "2025-11-06 10:16:05", "cal_wa", "var_wa", "both paddles, no problem"),
    _m("ca_blue3", "2025-11-06 10:30:44", "var_wa", "cal_wa", "thx cal"),
    # C42: about the climbing gym, to Calla
    _m(
        "vc_staff",
        "2025-11-14 20:55:10",
        "var_sms",
        "cal_sms",
        "staff all gone, come up whenever",
    ),
    _m(
        "ca_nerv",
        "2025-11-21 09:00:30",
        "cal_wa",
        "var_wa",
        "im getting nervous about saturday, first comp in years",
    ),
    # ---- Toby Rusk ("Toby" on Item 2) <-> VARGA, SMS (item 2)
    _m(
        "ru_key",
        "2025-11-11 09:40:15",
        "rus_sms",
        "var_sms",
        "left the key under the blue pot, plumber comes at 2",
        EV,
    ),
    _m(
        "ru_stair",
        "2025-11-18 08:15:40",
        "var_sms",
        "rus_sms",
        "need the bikes out of the stairwell by thurs, inspection",
    ),
    # ---- Arlo, Brynn (item 1); Mama (item 2); Dorrie, Pell, Jory Pask (item 3)
    _m(
        "ar_cold",
        "2025-11-02 16:00:12",
        "mer_sms",
        "arl_sms",
        "the cold ones are in the garage fridge, help urself",
    ),
    _m(
        "ar_quad",
        "2025-11-04 09:05:44",
        "mer_sms",
        "arl_sms",
        "nobody rides the quad till december, its in the shop",
    ),
    _m(
        "br_gas",
        "2025-11-16 09:00:20",
        "mer_sms",
        "bry_sms",
        "sent u 40 for the gas, check ur bank",
    ),
    _m(
        "ma_tall",
        "2025-10-14 18:30:05",
        "var_wa",
        "mam_wa",
        "found 6 tall ones at the thrift for ur patio",
    ),
    _m(
        "do_pizza",
        "2025-11-04 17:30:10",
        "dor_wa",
        "odu_wa",
        "grab the pizzas from the freezer for the kids",
    ),
    _m(
        "pe_gym",
        "2025-11-13 18:20:30",
        "odu_sms",
        "pel_sms",
        "the gym on larch closes at 9 on fridays now",
    ),
    _m(
        "jo_lot",
        "2025-10-29 15:10:05",
        "odu_sms",
        "jor_sms",
        "drop the van at the grain elevator lot after 5",
    ),
)

SCRIPTED_CALLS: tuple[Call, ...] = (
    # C13: 9:31:05 p.m. MDT, 288 s; Item 3 prints 8:31:05 PM(UTC-7) ...
    _c("cl_1017a", "2025-10-17 21:31:05", "mer_sms", "odu_sms", 288),
    # ... and a 41 s call at 10:30 p.m. MDT, which Item 3 prints as 9:30:20 PM(UTC-7)
    _c("cl_1017b", "2025-10-17 22:30:20", "mer_sms", "odu_sms", 41),
    # C45: the only VARGA-ODUM call on Nov 4 is 50 s; the eight-minute call is with Calla
    _c("cl_vo04", "2025-11-04 14:10:20", "var_sms", "odu_sms", 50),
    _c("cl_vc04", "2025-11-04 19:30:00", "var_sms", "cal_sms", 482),
    # C14: a five-minute call at 4:50 p.m. MST, which Item 2 prints as 11:50:30 PM(UTC+0) ...
    _c("cl_1114a", "2025-11-14 16:50:30", "var_sms", "odu_sms", 305),
    # ... and the 11:52 p.m. one, 128 s, which Item 2 prints as 11/15/2025 6:52:10 AM(UTC+0)
    _c("cl_1114b", "2025-11-14 23:52:10", "var_sms", "odu_sms", 128),
    # C16: the BURNER calls the COURIER (Item 3 only), then MERROW's own number, 22 s
    _c("cl_bur1114", "2025-11-14 22:07:15", "bur_sms", "odu_sms", 92),
    _c("cl_mer1114", "2025-11-14 22:31:40", "mer_sms", "odu_sms", 22),
    # C18: "Jory" on Item 3 is Jory Pask, not the FENCE
    _c("cl_jory", "2025-11-19 15:22:30", "odu_sms", "jor_sms", 140),
    # C48: on Item 3's call log only
    _c("cl_vo23", "2025-11-23 18:10:40", "var_sms", "odu_sms", 210, skip=("item2",)),
)

# Words only scripted messages may use, so background chatter can never create, break or
# crowd a claim: claim quotes, wrong-candidate words, names, places and the case's slang.
# RESERVED_STEMS match at the start of a word ("bike" also bars "bikes"); RESERVED_WORDS match
# whole words or phrases only.
RESERVED_STEMS = (
    "quillbarrow",
    "bramblewood",
    "larch",
    "pindlewick",
    "camera",
    "locker",
    "hatchback",
    "paddle",
    "kayak",
    "toby",
    "tobias",
    "ines",
    "jory",
    "calvin",
    "calla",
    "trailer",
    "pizza",
    "container",
    "batter",
    "skinn",
    "carbon",
    "nervous",
    "garage",
    "marketplace",
    "insta",
    "grain",
    "elevator",
    "thurs",
    "bike",
    "ebike",
    "emtb",
    "wheel",
    "number",
    "phone",
    "quarry",
    "clock",
    "stairwell",
    "inspect",
    "plumber",
    "thrift",
    "patio",
    "freezer",
    "fridge",
    "cash",
    "money",
    "price",
    "buyer",
    "staff",
    "friday",
    "december",
    "nobody",
    "found",
    "close",
    "move",
    "ticket",
    "route",
    "bank",
    "stop",
    "park",
    "feed",
    "sent",
    "save",
    "acct",
    "stay",
    "home",
    "dark",
    "careful",
    "news",
    "word",
    "light",
    "spare",
    "cousin",
    "quad",
    "ride",
    "gym",
    "comp",
)
RESERVED_WORDS = (
    "cal",
    "vee",
    "t2",
    "red",
    "blue",
    "green",
    "lot",
    "pot",
    "key",
    "keys",
    "van",
    "yard",
    "gas",
    "dock",
    "cage",
    "gate",
    "lane",
    "code",
    "unit",
    "shop",
    "page",
    "list",
    "post",
    "new",
    "its",
    "this is",
    "back row",
    "back door",
    "cold ones",
    "tall ones",
    "start with",
    "last two",
    "first 6",
    "u up",
    "u good",
    "u see",
    "u at",
    "need u",
    "2291",
    "7719",
    "1400",
    "1200",
    "400",
    "9:30",
    "41",
    "11",
)

# ---------------------------------------------------------------- background chatter

WORK = (
    "running a few min behind",
    "pallets in bay b are done",
    "forklift needs a charge",
    "send me the pick sheet",
    "who has the scanner",
    "on my way",
    "be there in 15",
    "sounds good",
    "ok",
    "got it",
    "lunch at noon",
    "the truck is late again",
    "overtime saturday if u want it",
    "label the totes in black",
    "printer is jammed",
    "back in 20",
    "thanks",
    "all good",
    "which aisle?",
    "after lunch",
    "shift swap ok with u?",
    "rain all day, mud everywhere",
    "drywall guys show at 8",
    "need more screws",
)
FAMILY = (
    "omw",
    "lol",
    "did u eat",
    "heading out",
    "call me later",
    "can u grab eggs",
    "kids are asleep",
    "what time?",
    "after 7 works",
    "good morning",
    "how was work",
    "long day",
    "snow on the pass again",
    "happy bday!!",
    "game tonight?",
    "pick up some bread",
    "see u sunday",
    "love u",
    "text me when u get in",
    "ok",
    "haha true",
    "cant today",
    "maybe weekend",
    "traffic on i25 is awful",
    "nice",
    "yeah",
    "thx",
    "the heater is out again",
    "dinner at moms?",
    "send pics",
    "the dog got out lol",
    "pumpkin pie or apple",
)
LANDLORD = (
    "rent is due on the 1st",
    "the sink is dripping again",
    "furnace guy comes wednesday",
    "ok thanks",
    "will do",
    "recycling is tuesday now",
    "mail came for the old tenant",
    "ice on the steps this morning",
)
MECHANIC = (
    "brakes are done",
    "need a part, maybe tuesday",
    "oil change is 60",
    "ok",
    "thanks man",
    "can u come by after 4",
    "tires look worn",
    "the warning lamp was a loose wire",
    "be there in 30",
)
IG_CUSTOMER = (
    "is the helmet still available?",
    "how much for the rack",
    "can i pick up sunday",
    "do u ship?",
    "thanks, looks great",
    "any more pumps coming?",
    "what time can i come by",
    "ok see u then",
)
IG_SHOP = (
    "yes, 35",
    "rack is 20",
    "sunday after noon works",
    "local only, sorry",
    "thank u!",
    "more next week",
    "come by after 10",
    "see u then",
)
POOLS = {"work": WORK, "family": FAMILY, "landlord": LANDLORD, "mechanic": MECHANIC}


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


# C35's wrong reading (CAL = Item 2's "Cal") finds nothing from Nov 15 through Nov 17
CALLA_QUIET = (("2025-11-13 00:00:00", "2025-11-19 00:00:00"),)

FILLER_THREADS: tuple[FillerThread, ...] = (
    FillerThread("item1", "mer_sms", "shp_sms", 150, ("work",), calls=6),
    FillerThread("item1", "mer_sms", "bry_sms", 60, ("family",), calls=3),
    FillerThread("item1", "mer_wa", "arl_wa", 110, ("family",)),
    FillerThread("item1", "mer_sms", "arl_sms", 30, ("family",), calls=2),
    FillerThread("item2", "var_sms", "rus_sms", 40, ("landlord",), calls=2),
    FillerThread("item2", "var_wa", "cal_wa", 130, ("family",), quiet=CALLA_QUIET),
    FillerThread("item2", "var_sms", "cal_sms", 40, ("family",), calls=3, quiet=CALLA_QUIET),
    FillerThread("item2", "var_wa", "mam_wa", 140, ("family",)),
    FillerThread("item2", "var_ig", "ig1_ig", 20, ("ig",)),
    FillerThread("item2", "var_ig", "ig2_ig", 20, ("ig",)),
    FillerThread("item2", "var_ig", "ig3_ig", 20, ("ig",)),
    FillerThread("item3", "odu_sms", "ash_sms", 90, ("work",), calls=3),
    FillerThread("item3", "odu_wa", "dor_wa", 140, ("family",)),
    FillerThread("item3", "odu_sms", "pel_sms", 70, ("family",), calls=3),
    # C33's wrong reading (the FENCE = Item 3's "Jory") finds contact all month
    FillerThread("item3", "odu_sms", "jor_sms", 60, ("mechanic",), calls=5),
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
    return any(mt(a) <= at < mt(b) for a, b in t.quiet)


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

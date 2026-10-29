"""Case04 story. SYNTHETIC: every person, number, handle, place and event here is fictional.

case04 is the held-out set for the testability step's go/no-go: claims written the way
affidavits are written (defined terms, aliases, relative dates, indirect speech, numbers in
words) beside plain ones, over three phones, with a wrong reading planted for most claims: a
second person with the same first name or nickname, a second number or account for the same
person, a second phone that could be meant, a near-miss time window, a contact name used on two
phones for two people, or similar words in another thread. eval/synthetic/case04_key.py says,
claim by claim, which reading is right, which wrong candidate the data holds, and what the
signed sheet should name.

This file holds the hand-placed part of the case: people, accounts, devices, contacts and every
message or call a claim depends on, plus seeded background chatter that never touches a thread
between two subjects, the PREPAID or CW-1. Phone numbers use the 555-01xx range reserved for
fiction (area codes 312 and 773). Times are written in US Central local time with ct(); daylight
saving starts at 2:00 a.m. on 2026-03-08, the night of the BELMONT SITE theft.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

DEVICE_TZ = "America/Chicago"
ZONE = ZoneInfo(DEVICE_TZ)


def ct(local: str) -> datetime:
    """'2026-03-07 23:05:00' as a wall-clock time in Chicago -> aware UTC datetime."""
    return datetime.fromisoformat(local).replace(tzinfo=ZONE).astimezone(UTC)


def central_offset_min(utc: datetime) -> int:
    off = utc.astimezone(ZONE).utcoffset()
    return int(off.total_seconds() // 60) if off is not None else 0


CASE_START = ct("2026-02-09 00:00:00")
CASE_END = ct("2026-04-02 00:00:00")
T0 = CASE_START - timedelta(days=60)
RENAME_AT = ct("2026-03-15 12:00:00")  # the DRIVER's Telegram name: "dez" -> "D.O." (claim C10)

# ---------------------------------------------------------------- people (ground truth only)

PEOPLE = {
    "halloran": "Owen Halloran",
    "ferro": "Nadia Ferro",
    "okafor": "Desmond Okafor",
    "pratt": "Owen Pratt (Ferro's upstairs neighbour; a second Owen)",
    "lamb": "Desiree Lamb (Ferro's cousin, saved on Item 2 as 'Dez'; a second Dez)",
    "cw1": "CW-1 (cooperating witness, +17735550187; Item 1 saves the number as 'Rocco')",
    "vitale": "Rocco Vitale (a tile setter; Item 3 saves him as 'Rocco')",
    "marisol": "Marisol Ferro (Ferro's sister)",
    "kip": "the buyer (Instagram kip.flips.chi and kipflips.chi; two accounts)",
    "greer": "Tasha Greer (Okafor's girlfriend)",
    "mum": "Okafor's mother",
    "gus": "Gus (runs a tow lot)",
    "szabo": "Benny Szabo (Halloran's foreman)",
    "duda": "Mr. Duda (Halloran's landlord)",
    "wren": "Wren Castillo (Halloran's partner)",
    "brandt": "Brandt Metals (a scrap office)",
    "ike": "Ike Nwosu (Okafor's friend)",
    "ig_customers": "resale customers on Instagram",
}

# ---------------------------------------------------------------- accounts


@dataclass(frozen=True)
class Acct:
    key: str
    app: str  # SMS, WhatsApp, Telegram, Instagram
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


def _phone(n: str, area: str = "312") -> str:
    return f"+1{area}555{n}"


def _wa(n: str, area: str = "312") -> str:
    return f"1{area}555{n}@s.whatsapp.net"


ACCOUNTS: dict[str, Acct] = {
    a.key: a
    for a in [
        # HALLORAN (item1 owner) and the PREPAID, which is on no seized phone as an owner account
        Acct("hal_sms", "SMS", _phone("0141"), "halloran"),
        Acct("hal_wa", "WhatsApp", _wa("0141"), "halloran"),
        Acct("hal_tg", "Telegram", "8204101", "halloran", ((T0, "Hal"),)),
        Acct("pre_sms", "SMS", _phone("0199"), "halloran"),
        # FERRO (item2 owner); ferro.finds is her resale shop's Instagram
        Acct("fer_sms", "SMS", _phone("0152"), "ferro"),
        Acct("fer_wa", "WhatsApp", _wa("0152"), "ferro"),
        Acct("fer_tg", "Telegram", "8204102", "ferro", ((T0, "Nadia F"),)),
        Acct("fer_ig", "Instagram", "ferro.finds", "ferro"),
        # OKAFOR (item3 owner), the DRIVER
        Acct("oka_sms", "SMS", _phone("0176", "773"), "okafor"),
        Acct("oka_wa", "WhatsApp", _wa("0176", "773"), "okafor"),
        Acct("oka_tg", "Telegram", "8204103", "okafor", ((T0, "dez"), (RENAME_AT, "D.O."))),
        # third parties
        Acct("pratt_sms", "SMS", _phone("0118"), "pratt"),
        Acct("lamb_sms", "SMS", _phone("0164", "773"), "lamb"),
        Acct("cw1_sms", "SMS", _phone("0187", "773"), "cw1"),
        Acct("vitale_sms", "SMS", _phone("0133", "773"), "vitale"),
        Acct("mar_wa", "WhatsApp", _wa("0107"), "marisol"),
        Acct("kip1_ig", "Instagram", "kip.flips.chi", "kip"),
        Acct("kip2_ig", "Instagram", "kipflips.chi", "kip"),
        Acct("greer_sms", "SMS", _phone("0145", "773"), "greer"),
        Acct("mum_wa", "WhatsApp", _wa("0158", "773"), "mum"),
        Acct("gus_sms", "SMS", _phone("0191", "773"), "gus"),
        Acct("szabo_sms", "SMS", _phone("0126"), "szabo"),
        Acct("duda_sms", "SMS", _phone("0113"), "duda"),
        Acct("wren_wa", "WhatsApp", _wa("0172"), "wren"),
        Acct("brandt_sms", "SMS", _phone("0122", "773"), "brandt"),
        Acct("ike_tg", "Telegram", "8204177", "ike", ((T0, "Ike"),)),
        Acct("lina_ig", "Instagram", "lina.reuses", "ig_customers"),
        Acct("mo_ig", "Instagram", "mo_buys_tools", "ig_customers"),
        Acct("jt_ig", "Instagram", "jt.garage.chi", "ig_customers"),
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
    # 'fixed-360' (always UTC-6, the examiner's display setting, so wrong by an hour after DST)
    report_tz: str
    owner_accounts: tuple[str, ...]
    contacts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = field(default=())


DEVICES: tuple[Device, ...] = (
    Device(
        key="item1",
        evidence_no="Item 1",
        owner="halloran",
        label="Item 1: Apple iPhone 15 seized from Owen Halloran",
        model="Apple iPhone 15 (A3090)",
        os_version="iOS 17.6",
        extraction_type="logical",
        extraction_label="Advanced Logical",
        extracted_at=ct("2026-04-03 09:40:00"),
        report_tz="utc",
        owner_accounts=("hal_sms", "hal_wa", "hal_tg"),
        contacts=(
            ("Nadia", (("Phone-Mobile", _phone("0152")),)),
            ("Dez", (("Phone-Mobile", _phone("0176", "773")),)),  # OKAFOR here
            ("Rocco", (("Phone-Mobile", _phone("0187", "773")),)),  # CW-1's number here
            ("Benny NGE", (("Phone-Mobile", _phone("0126")),)),
            ("Duda landlord", (("Phone-Mobile", _phone("0113")),)),
            ("Wren", (("Phone-Mobile", _phone("0172")),)),
            ("Lucia scrap", (("Phone-Mobile", _phone("0122", "773")),)),
        ),
    ),
    Device(
        key="item2",
        evidence_no="Item 2",
        owner="ferro",
        label="Item 2: Google Pixel 8 seized from Nadia Ferro",
        model="Google Pixel 8 (GKWS6)",
        os_version="Android 14",
        extraction_type="file_system",
        extraction_label="Full File System",
        extracted_at=ct("2026-04-03 14:15:00"),
        report_tz="local",
        owner_accounts=("fer_sms", "fer_wa", "fer_tg", "fer_ig"),
        contacts=(
            ("Owen H", (("Phone-Mobile", _phone("0141")),)),
            ("Hal 2", (("Phone-Mobile", _phone("0199")),)),  # the PREPAID
            ("Owen upstairs", (("Phone-Mobile", _phone("0118")),)),  # a second Owen
            ("Desmond O", (("Phone-Mobile", _phone("0176", "773")),)),  # OKAFOR here
            ("Dez", (("Phone-Mobile", _phone("0164", "773")),)),  # Desiree Lamb, not OKAFOR
            ("Mari", (("Phone-Mobile", _phone("0107")),)),
            ("Brandt Metals", (("Phone-Mobile", _phone("0122", "773")),)),
        ),
    ),
    Device(
        key="item3",
        evidence_no="Item 3",
        owner="okafor",
        label="Item 3: Motorola moto g seized from Desmond Okafor",
        model="Motorola moto g 5G (XT2341)",
        os_version="Android 13",
        extraction_type="logical",
        extraction_label="Logical",
        extracted_at=ct("2026-04-04 10:30:00"),
        report_tz="fixed-360",
        owner_accounts=("oka_sms", "oka_wa", "oka_tg"),
        contacts=(
            ("Hal", (("Phone-Mobile", _phone("0141")),)),  # HALLORAN's own number
            ("H", (("Phone-Mobile", _phone("0199")),)),  # the PREPAID
            ("Nadia F", (("Phone-Mobile", _phone("0152")),)),
            ("Rocco", (("Phone-Mobile", _phone("0133", "773")),)),  # Rocco Vitale, not CW-1
            ("Tash", (("Phone-Mobile", _phone("0145", "773")),)),
            ("Mum", (("Phone-Mobile", _phone("0158", "773")),)),
            ("Gus tow", (("Phone-Mobile", _phone("0191", "773")),)),
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
    return Msg(key, ct(local), sender, to, body, "en", tag, skip)


def _c(key: str, local: str, caller: str, callee: str, dur: int, answered: bool = True) -> Call:
    return Call(key, ct(local), caller, callee, dur, answered)


SCRIPTED_MESSAGES: tuple[Msg, ...] = (
    # ---- HALLORAN <-> OKAFOR, SMS (items 1 and 3)
    _m(
        "ho_driver",
        "2026-02-12 18:20:15",
        "oka_sms",
        "hal_sms",
        "u still need a driver? i can do weekends",
    ),
    _m("ho_driver2", "2026-02-12 18:41:02", "hal_sms", "oka_sms", "maybe. talk sat"),
    _m(
        "ho_meet",
        "2026-03-03 12:10:44",
        "hal_sms",
        "oka_sms",
        "meet behind the laundromat on fullerton thursday 8pm",
        EV,
    ),
    _m("ho_meet2", "2026-03-03 12:16:09", "oka_sms", "hal_sms", "ok"),
    _m("ho_here", "2026-03-05 20:03:31", "oka_sms", "hal_sms", "here"),
    _m("ho_here2", "2026-03-05 20:05:12", "hal_sms", "oka_sms", "2 min"),
    # C04 and C28: HALLORAN's own number writes to the DRIVER that evening too (wrong candidate)
    _m("ho_drill", "2026-03-06 18:02:40", "hal_sms", "oka_sms", "u still got my drill?"),
    _m("ho_drill2", "2026-03-06 18:09:55", "oka_sms", "hal_sms", "ya bring it sun"),
    # C31: the only contact on Mar 14, local time; it is Mar 15 in UTC
    _m("ho_tmrw", "2026-03-14 21:30:18", "hal_sms", "oka_sms", "u around tmrw?", EV),
    _m("ho_tmrw2", "2026-03-14 21:52:07", "oka_sms", "hal_sms", "after 2"),
    # C15: Item 1 prints it as 3/19/2026 12:15:40 AM(UTC+0)
    _m(
        "ho_gloves",
        "2026-03-18 19:15:40",
        "hal_sms",
        "oka_sms",
        "need u at 6 tmrw, bring gloves",
        EV,
    ),
    _m("ho_gloves2", "2026-03-18 19:22:03", "oka_sms", "hal_sms", "ok"),
    # C36: on Item 3 only; Item 1's report does not hold it
    _m("ho_good", "2026-03-29 16:40:22", "oka_sms", "hal_sms", "u good?", skip=("item1",)),
    # ---- HALLORAN <-> OKAFOR, Telegram (items 1 and 3)
    _m(
        "ht_wrap",
        "2026-03-08 14:05:12",
        "oka_tg",
        "hal_tg",
        "wrap the spools in the moving blankets so they dont shine",
    ),
    _m("ht_wrap2", "2026-03-08 14:09:40", "hal_tg", "oka_tg", "ya blankets it is"),
    _m("ht_10a", "2026-03-10 09:40:05", "hal_tg", "oka_tg", "u up"),
    _m("ht_10b", "2026-03-10 09:52:30", "oka_tg", "hal_tg", "ya whats good"),
    _m("ht_blank", "2026-03-11 21:20:33", "hal_tg", "oka_tg", "the 9 blankets are at the unit", EV),
    _m("ht_blank2", "2026-03-11 21:24:50", "oka_tg", "hal_tg", "ok"),
    # C26: on Item 1 only, so Item 1 counts 7 in Mar 9-14 and Item 3 counts 6
    _m("ht_12", "2026-03-12 12:30:10", "hal_tg", "oka_tg", "?", skip=("item3",)),
    _m("ht_13a", "2026-03-13 11:00:20", "oka_tg", "hal_tg", "need the key for the shed"),
    _m("ht_13b", "2026-03-13 11:10:45", "hal_tg", "oka_tg", "nadia has it"),
    _m("ht_17a", "2026-03-17 10:15:00", "oka_tg", "hal_tg", "u need me thurs?"),
    _m("ht_17b", "2026-03-17 10:31:44", "hal_tg", "oka_tg", "maybe"),
    # ---- FERRO <-> OKAFOR, SMS (items 2 and 3)
    _m("fo_hi", "2026-02-20 13:00:10", "fer_sms", "oka_sms", "hi its nadia, hal gave me ur number"),
    _m("fo_hi2", "2026-02-20 13:05:42", "oka_sms", "fer_sms", "bet"),
    # C21: FERRO wrote it, not OKAFOR
    _m(
        "fo_welder",
        "2026-03-16 16:10:27",
        "fer_sms",
        "oka_sms",
        "that welder guy talks too much",
        EV,
    ),
    _m("fo_welder2", "2026-03-16 16:15:03", "oka_sms", "fer_sms", "word"),
    # C38: FERRO set the time
    _m("fo_pickup", "2026-03-20 14:00:35", "fer_sms", "oka_sms", "pickup 10:15, not before", EV),
    _m("fo_pickup2", "2026-03-20 14:04:12", "oka_sms", "fer_sms", "k"),
    # C27: five on Mar 21 local; the last two are Mar 22 in UTC
    _m("fo_21a", "2026-03-21 10:05:10", "oka_sms", "fer_sms", "u up?"),
    _m("fo_21b", "2026-03-21 10:20:44", "fer_sms", "oka_sms", "ya"),
    _m("fo_21c", "2026-03-21 15:30:02", "oka_sms", "fer_sms", "trailer is hooked up"),
    _m("fo_21d", "2026-03-21 19:10:30", "fer_sms", "oka_sms", "leaving in 10"),
    _m("fo_21e", "2026-03-21 22:20:15", "oka_sms", "fer_sms", "here"),
    # ---- FERRO <-> OKAFOR, WhatsApp (items 2 and 3)
    _m(
        "fw_addr",
        "2026-03-04 14:40:05",
        "fer_wa",
        "oka_wa",
        "address is 2210 n kildare, side gate",
        EV,
    ),
    _m("fw_addr2", "2026-03-04 14:43:30", "oka_wa", "fer_wa", "got it"),
    _m(
        "fw_600",
        "2026-03-23 20:30:12",
        "fer_wa",
        "oka_wa",
        "ur 600 is in the envelope under the mat",
        EV,
    ),
    _m("fw_6002", "2026-03-23 21:02:48", "oka_wa", "fer_wa", "got it, thx", EV),
    _m("fw_thurs", "2026-03-24 12:15:00", "oka_wa", "fer_wa", "u around thurs?"),
    _m("fw_thurs2", "2026-03-24 12:40:33", "fer_wa", "oka_wa", "no. stay away from the shed"),
    # C48: on Item 3 only; Item 2's report does not hold it
    _m(
        "fw_house",
        "2026-03-28 13:00:05",
        "fer_wa",
        "oka_wa",
        "u ok? dont come by the house",
        skip=("item2",),
    ),
    # ---- FERRO <-> OKAFOR, Telegram (items 2 and 3). "dez" until Mar 15, then "D.O."
    _m("ft_plan", "2026-03-03 19:00:00", "oka_tg", "fer_tg", "whats the plan sat"),
    _m("ft_plan2", "2026-03-03 19:12:00", "fer_tg", "oka_tg", "later"),
    _m("ft_load", "2026-03-08 00:52:18", "oka_tg", "fer_tg", "loaded and moving. 20 min"),
    # C46: 4:48 a.m. CDT; Item 3 prints it as 3:48:26 AM(UTC-6)
    _m("ft_gus", "2026-03-08 04:48:26", "oka_tg", "fer_tg", "home. van is back at gus", EV),
    _m("ft_gus2", "2026-03-08 09:30:02", "fer_tg", "oka_tg", "ok sleep"),
    _m("ft_news", "2026-03-17 20:00:12", "oka_tg", "fer_tg", "u see the news"),
    _m("ft_news2", "2026-03-17 20:05:40", "fer_tg", "oka_tg", "dont"),
    # ---- HALLORAN <-> FERRO, SMS (items 1 and 2)
    # C01: Item 1 prints it as 2/19/2026 2:12:40 AM(UTC+0)
    _m("hf_van", "2026-02-18 20:12:40", "hal_sms", "fer_sms", "need the big van sat, 6am", EV),
    _m("hf_van2", "2026-02-18 20:30:05", "fer_sms", "hal_sms", "its yours"),
    # C41: HALLORAN named the place
    _m(
        "hf_pul",
        "2026-03-07 21:15:20",
        "hal_sms",
        "fer_sms",
        "taking them to the unit on pulaski after",
        EV,
    ),
    _m("hf_pul2", "2026-03-07 21:19:48", "fer_sms", "hal_sms", "ok"),
    # C30: nine between 11 p.m. CST and the 2 a.m. jump (05:00-08:00 UTC) ...
    _m("hn01", "2026-03-07 23:05:10", "hal_sms", "fer_sms", "here"),
    _m("hn02", "2026-03-07 23:18:42", "fer_sms", "hal_sms", "where"),
    _m("hn03", "2026-03-07 23:31:05", "hal_sms", "fer_sms", "side lot"),
    _m("hn04", "2026-03-07 23:52:30", "fer_sms", "hal_sms", "k"),
    _m("hn05", "2026-03-08 00:14:12", "hal_sms", "fer_sms", "going in"),
    _m("hn06", "2026-03-08 00:37:55", "fer_sms", "hal_sms", "ok"),
    _m("hn07", "2026-03-08 01:02:20", "hal_sms", "fer_sms", "almost"),
    _m("hn08", "2026-03-08 01:25:41", "fer_sms", "hal_sms", "?"),
    _m("hn09", "2026-03-08 01:40:03", "hal_sms", "fer_sms", "out"),
    # ... and three in the hour after 3 a.m. CDT (08:00-09:00 UTC): inside "11 p.m. to 3 a.m."
    # only for a reading that forgets the clocks went forward
    _m("hn10", "2026-03-08 03:10:14", "fer_sms", "hal_sms", "u ok"),
    _m("hn11", "2026-03-08 03:34:40", "hal_sms", "fer_sms", "ya"),
    _m("hn12", "2026-03-08 03:51:09", "fer_sms", "hal_sms", "sleep"),
    _m(
        "hf_coils",
        "2026-03-09 10:30:15",
        "hal_sms",
        "fer_sms",
        "the coils are under the blue tarp",
        EV,
    ),
    _m("hf_coils2", "2026-03-09 10:41:02", "fer_sms", "hal_sms", "the copper ones?", EV),
    _m("hf_coils3", "2026-03-09 10:44:30", "hal_sms", "fer_sms", "ya the copper, all 9", EV),
    _m("hf_heavy", "2026-03-13 16:20:50", "fer_sms", "hal_sms", "bring the 3 heavy ones fri", EV),
    _m("hf_heavy2", "2026-03-13 16:33:12", "hal_sms", "fer_sms", "ok"),
    _m("hf_late", "2026-03-20 13:30:00", "hal_sms", "fer_sms", "running late"),
    _m(
        "hf_weld",
        "2026-03-23 11:00:40",
        "fer_sms",
        "hal_sms",
        "need the welder out of my garage by tmrw",
        EV,
    ),
    _m("hf_weld2", "2026-03-23 11:20:05", "hal_sms", "fer_sms", "ok ill grab it tonight", EV),
    # ---- HALLORAN <-> FERRO, WhatsApp (items 1 and 2)
    # C25: three on Feb 22 after 6 p.m. CST (Feb 23 in UTC), outside the local window ...
    _m("hw00a", "2026-02-22 19:10:00", "hal_wa", "fer_wa", "u free tmrw"),
    _m("hw00b", "2026-02-22 19:25:30", "fer_wa", "hal_wa", "after 4"),
    _m("hw00c", "2026-02-22 19:40:12", "hal_wa", "fer_wa", "k"),
    # ... eight inside it, the last two on Mar 1 after 6 p.m. CST (Mar 2 in UTC)
    _m("hw01", "2026-02-24 10:05:00", "fer_wa", "hal_wa", "call me when u can"),
    _m("hw02", "2026-02-24 10:30:20", "hal_wa", "fer_wa", "on a job, later"),
    _m("hw03", "2026-02-26 15:00:40", "fer_wa", "hal_wa", "did benny pay u"),
    _m("hw04", "2026-02-26 15:20:05", "hal_wa", "fer_wa", "friday"),
    _m("hw05", "2026-02-28 11:00:10", "fer_wa", "hal_wa", "storage guy wants the rent"),
    _m("hw06", "2026-02-28 11:30:45", "hal_wa", "fer_wa", "ill pay it"),
    _m("hw07", "2026-03-01 19:05:30", "fer_wa", "hal_wa", "u see the game"),
    _m("hw08", "2026-03-01 19:20:02", "hal_wa", "fer_wa", "ya rough"),
    # C17: 11:46 p.m. CDT on Mar 25; Item 1 prints 3/26/2026 4:46:12 AM(UTC+0)
    _m(
        "hw_mid",
        "2026-03-25 23:46:12",
        "fer_wa",
        "hal_wa",
        "they might come tmrw. clean the van",
        EV,
    ),
    _m("hw_mid2", "2026-03-25 23:58:40", "hal_wa", "fer_wa", "on it"),
    # ---- HALLORAN <-> FERRO, Telegram (items 1 and 2)
    # C05: 1:47 a.m. CST, before the jump; Item 1 prints 3/8/2026 7:47:10 AM(UTC+0)
    _m("hft_done", "2026-03-08 01:47:10", "hal_tg", "fer_tg", "all 9 at the unit. go to bed", EV),
    _m("hft_done2", "2026-03-08 09:31:20", "fer_tg", "hal_tg", "ok"),
    # C29: six on Item 2 from Mar 16 through Mar 20; Item 1's report holds only four
    _m("hft_16a", "2026-03-16 09:00:10", "fer_tg", "hal_tg", "call me"),
    _m("hft_16b", "2026-03-16 09:20:40", "hal_tg", "fer_tg", "busy, later"),
    _m("hft_18a", "2026-03-18 13:10:05", "fer_tg", "hal_tg", "the guy wants more", skip=("item1",)),
    _m("hft_18b", "2026-03-18 13:30:22", "hal_tg", "fer_tg", "not now", skip=("item1",)),
    _m("hft_19a", "2026-03-19 17:45:00", "fer_tg", "hal_tg", "fri?"),
    _m("hft_19b", "2026-03-19 17:59:31", "hal_tg", "fer_tg", "maybe"),
    # ---- the PREPAID <-> OKAFOR, SMS (item 3 only: the PREPAID is no seized phone's account)
    _m("p_new3", "2026-02-27 20:00:00", "pre_sms", "oka_sms", "new number, its hal"),
    # C28: eleven from Monday Mar 2 through Friday Mar 6
    _m("p01", "2026-03-02 09:10:05", "pre_sms", "oka_sms", "this is the work line. save it"),
    _m("p02", "2026-03-02 09:15:40", "oka_sms", "pre_sms", "saved"),
    _m("p03", "2026-03-03 17:20:00", "pre_sms", "oka_sms", "sat still on"),
    _m("p04", "2026-03-03 17:31:12", "oka_sms", "pre_sms", "yes"),
    _m("p05", "2026-03-04 08:45:30", "pre_sms", "oka_sms", "need the big van not the small one"),
    _m("p06", "2026-03-04 08:50:02", "oka_sms", "pre_sms", "ok"),
    _m("p07", "2026-03-05 16:05:44", "pre_sms", "oka_sms", "gus can do sat night?"),
    _m("p08", "2026-03-05 16:20:18", "oka_sms", "pre_sms", "he said yes"),
    _m(
        "p_ladder",
        "2026-03-06 19:15:22",
        "pre_sms",
        "oka_sms",
        "bring the long ladder and both dollies",
        EV,
    ),
    _m("p10", "2026-03-06 19:22:51", "oka_sms", "pre_sms", "ok"),
    _m("p11", "2026-03-06 21:40:09", "oka_sms", "pre_sms", "what time"),
    # the next day (Saturday), outside the work week
    _m(
        "p_alley", "2026-03-07 22:50:40", "pre_sms", "oka_sms", "park on the alley side, lights off"
    ),
    # ---- the PREPAID <-> FERRO, SMS (item 2 only)
    _m("p_new2", "2026-02-27 20:05:00", "pre_sms", "fer_sms", "new number, its hal", EV),
    _m("p_hitch", "2026-03-20 15:10:33", "pre_sms", "fer_sms", "u sure the hitch fits the van?"),
    _m("p_hitch2", "2026-03-20 15:20:00", "fer_sms", "pre_sms", "yes"),
    # C32: the PREPAID writes to FERRO inside Mar 27-29
    _m(
        "p_me",
        "2026-03-28 10:05:15",
        "pre_sms",
        "fer_sms",
        "its me. dont use the other number for a while",
        EV,
    ),
    _m("p_me2", "2026-03-28 10:12:40", "fer_sms", "pre_sms", "ok"),
    # ---- CW-1 <-> HALLORAN, SMS (item 1)
    _m(
        "cw01",
        "2026-02-25 18:00:30",
        "cw1_sms",
        "hal_sms",
        "benny said u might have copper to move",
    ),
    _m("cw02", "2026-02-25 18:20:12", "hal_sms", "cw1_sms", "maybe. who is this"),
    _m("cw03", "2026-02-25 18:24:40", "cw1_sms", "hal_sms", "rocco. bennys friend"),
    _m("cw04", "2026-03-12 11:00:00", "cw1_sms", "hal_sms", "still got stuff?"),
    _m("cw05", "2026-03-12 11:45:20", "hal_sms", "cw1_sms", "not now"),
    # ---- Desiree Lamb ("Dez" on Item 2) <-> FERRO, SMS (item 2)
    # C03: the yellow ones are Desiree's rain boots for the kids
    _m(
        "dz_yellow",
        "2026-03-10 11:05:30",
        "lamb_sms",
        "fer_sms",
        "the yellow ones are in my garage",
        EV,
    ),
    _m("dz_yellow2", "2026-03-10 11:12:02", "lamb_sms", "fer_sms", "come grab the boots whenever"),
    _m("dz_yellow3", "2026-03-10 11:30:45", "fer_sms", "lamb_sms", "thx dez"),
    _m(
        "dz_pick",
        "2026-03-20 08:15:20",
        "lamb_sms",
        "fer_sms",
        "pickup at 3:15 today? i can get the kids",
    ),
    # ---- Owen Pratt ("Owen upstairs") <-> FERRO, SMS (item 2)
    _m(
        "pr_van",
        "2026-02-16 09:30:10",
        "pratt_sms",
        "fer_sms",
        "can i borrow the van sat? moving a couch",
    ),
    _m("pr_van2", "2026-02-16 09:45:00", "fer_sms", "pratt_sms", "sure"),
    _m(
        "pr_heavy",
        "2026-03-13 18:05:40",
        "fer_sms",
        "pratt_sms",
        "bring the 2 heavy boxes down sat",
    ),
    _m(
        "pr_pkg",
        "2026-03-17 12:30:22",
        "pratt_sms",
        "fer_sms",
        "dropped off ur package by the door",
    ),
    _m(
        "pr_bike",
        "2026-03-23 09:10:05",
        "fer_sms",
        "pratt_sms",
        "need the bike out of the hallway by tmrw",
    ),
    # ---- Marisol ("Mari") <-> FERRO, WhatsApp (item 2)
    _m(
        "ms_coils",
        "2026-03-09 18:20:00",
        "fer_wa",
        "mar_wa",
        "the coils are under the porch, take what u need",
    ),
    _m("ms_pul", "2026-03-11 10:00:00", "fer_wa", "mar_wa", "moms boxes are at the pulaski unit"),
    _m("ms_owen", "2026-03-17 18:20:44", "mar_wa", "fer_wa", "owen dropped off the stuff", EV),
    _m("ms_owen2", "2026-03-17 18:31:10", "fer_wa", "mar_wa", "ok thx"),
    _m(
        "ms_60",
        "2026-03-23 19:00:30",
        "fer_wa",
        "mar_wa",
        "the 60 i owe u is in the envelope by the door",
    ),
    # ---- the buyer's two Instagram accounts <-> ferro.finds (item 2)
    _m("kp01", "2026-03-02 12:00:00", "kip1_ig", "fer_ig", "is the brass lamp still available?"),
    _m("kp02", "2026-03-02 12:20:00", "fer_ig", "kip1_ig", "yes, 40"),
    _m("kp03", "2026-03-02 12:25:00", "kip1_ig", "fer_ig", "ill take it"),
    _m("kf00", "2026-03-22 18:00:00", "kip2_ig", "fer_ig", "heard u have wire"),
    _m("kf01", "2026-03-22 18:30:00", "fer_ig", "kip2_ig", "maybe. what for"),
    _m(
        "kf_lot",
        "2026-03-24 14:50:10",
        "fer_ig",
        "kip2_ig",
        "lot is 4 spools 12 gauge copper, 250 ft each",
        EV,
    ),
    _m("kf_offer", "2026-03-24 15:05:33", "kip2_ig", "fer_ig", "1.8 for the lot, cash", EV),
    _m("kf_ok", "2026-03-24 15:12:48", "fer_ig", "kip2_ig", "1800 works. sat", EV),
    # ---- Tasha ("Tash") <-> OKAFOR, SMS (item 3)
    _m(
        "tg_drive",
        "2026-03-21 19:40:12",
        "oka_sms",
        "greer_sms",
        "driving for nadia tonight, back late",
        EV,
    ),
    _m("tg_drive2", "2026-03-21 19:44:30", "greer_sms", "oka_sms", "be safe"),
    # ---- Mum <-> OKAFOR, WhatsApp (item 3)
    _m(
        "mm_blank",
        "2026-03-12 09:00:00",
        "mum_wa",
        "oka_wa",
        "i left the blankets at your unit, the grey ones",
    ),
    # ---- Gus ("Gus tow") <-> OKAFOR, SMS (item 3)
    _m(
        "gu_laund",
        "2026-03-04 10:00:00",
        "oka_sms",
        "gus_sms",
        "leave it behind the laundromat on fullerton",
    ),
    _m("gu_talk", "2026-03-17 14:00:00", "oka_sms", "gus_sms", "that tow guy talks too much lol"),
    # ---- Benny ("Benny NGE") <-> HALLORAN, SMS (item 1)
    _m(
        "bz_clear",
        "2026-03-07 18:40:05",
        "hal_sms",
        "szabo_sms",
        "site is clear, everyone left at 5",
    ),
    _m(
        "bz_roof",
        "2026-03-15 07:30:10",
        "hal_sms",
        "szabo_sms",
        "stay off the roof till tuesday, its icing up",
    ),
)

SCRIPTED_CALLS: tuple[Call, ...] = (
    _c("cl_cw", "2026-03-02 17:30:00", "hal_sms", "cw1_sms", 120),
    # C13: 3:21:30 a.m. CDT, 245 s; Item 3 prints 2:21:30 AM(UTC-6), Item 1 8:21:30 AM(UTC+0)
    _c("cl_0321", "2026-03-08 03:21:30", "oka_sms", "hal_sms", 245),
    # C34: 4:12 a.m. CDT, which Item 3 prints as 3:12:40 AM(UTC-6)
    _c("cl_0412", "2026-03-08 04:12:40", "oka_sms", "fer_sms", 38),
    # C45: the only FERRO-OKAFOR call on Mar 12 is 45 s; the ten-minute one is with Desiree
    _c("cl_0312", "2026-03-12 15:20:11", "fer_sms", "oka_sms", 45),
    _c("cl_dz", "2026-03-12 19:05:00", "fer_sms", "lamb_sms", 612),
    # C14: an hour-earlier call, which Item 2 prints as 9:41:30 PM(UTC-5) ...
    _c("cl_2141", "2026-03-21 21:41:30", "fer_sms", "oka_sms", 75),
    # ... and the 10:41 p.m. one, which Item 3 prints as 9:41:05 PM(UTC-6)
    _c("cl_2241", "2026-03-21 22:41:05", "fer_sms", "oka_sms", 58),
    # C18: "Rocco" on Item 3 is Rocco Vitale, not CW-1
    _c("cl_vit", "2026-03-21 22:36:20", "oka_sms", "vitale_sms", 95),
    # C16: the DRIVER calls the PREPAID (Item 3 only), then HALLORAN's own number
    _c("cl_2258", "2026-03-21 22:58:10", "oka_sms", "pre_sms", 165),
    _c("cl_2310", "2026-03-21 23:10:05", "oka_sms", "hal_sms", 170),
)

# Words only scripted messages may use, so background chatter can never create, break or
# crowd a claim: claim quotes, wrong-candidate words, names, places and the case's slang.
RESERVED_WORDS = (
    "van",
    "spool",
    "copper",
    "coil",
    "blanket",
    "unit",
    "pulaski",
    "kildare",
    "fullerton",
    "laundromat",
    "welder",
    "pickup",
    "driv",
    "nadia",
    "owen",
    "hal",
    "dez",
    "gus",
    "rocco",
    "benny",
    "kip",
    "lot",
    "tarp",
    "heavy",
    "envelope",
    "ladder",
    "dollies",
    "site",
    "clear",
    "phone",
    "number",
    "hitch",
    "trailer",
    "tower",
    "yellow",
    "gloves",
    "wire",
    "tmrw",
    "tonight",
    "stuff",
    "dropped",
    "talks",
    "cop",
    "stay off",
    "tuesday",
    "thursday",
    "garage",
    "600",
    "1.8",
    "1800",
    "its ",
    "this is",
    "new ",
    "loaded",
    "home",
    "u up",
    "u ok",
    "u good",
)

# ---------------------------------------------------------------- background chatter

WORK = (
    "running 10 min late",
    "conduit run on 3 is done",
    "inspector comes at 9",
    "need more connectors",
    "panel on 2 is live, careful",
    "crew meeting at 7",
    "rain day, no pour",
    "send me the punch list",
    "who has the lift keys",
    "on my way",
    "be there in 15",
    "sounds good",
    "ok",
    "got it",
    "lunch at 12",
    "permit came through",
    "foreman says overtime sat",
    "mark the outlets in blue",
    "the hammer drill is dead",
    "back in 20",
    "thanks",
    "all good",
    "what floor?",
    "after lunch",
)
FAMILY = (
    "omw",
    "lol",
    "did u eat",
    "heading out",
    "call me later",
    "can u grab milk",
    "kids are asleep",
    "what time?",
    "after 6 works",
    "good morning",
    "how was work",
    "long day",
    "snow again",
    "happy bday!!",
    "bulls game?",
    "pick up some bread",
    "see u sunday",
    "love u",
    "text me when u get in",
    "ok",
    "haha true",
    "cant today",
    "maybe weekend",
    "traffic on the kennedy is bad",
    "nice",
    "yeah",
    "thx",
    "the heat is out again",
    "dinner at moms?",
    "send pics",
)
HOME = (
    "rent is due friday",
    "the sink is leaking again",
    "boiler guy comes wednesday",
    "ok thanks",
    "will do",
    "trash day moved to wed",
    "mailbox key is under the plant",
    "snow on the steps, careful",
)
SHOP = (
    "scale is open till 4",
    "prices posted on the board",
    "bring id next time",
    "closed sunday",
    "ok",
    "thanks",
    "what time u open?",
    "we close at 5",
)
TILE = (
    "grout is in",
    "can u do the bathroom sat",
    "need 40 more sq ft",
    "the saw blade is shot",
    "mortar set yet?",
    "ok",
    "thanks bro",
    "pay me friday",
    "be there at 8",
)
TOW = (
    "yard is full",
    "can u move the blue civic",
    "keys in the box",
    "ok",
    "storage fee is 40 a day",
    "be there in 30",
    "thx",
)
IG_CUSTOMER = (
    "is the dresser still available?",
    "how much for the mirror",
    "can i pick up saturday",
    "do u ship?",
    "thanks, looks great",
    "any more chairs coming?",
    "what time can i come by",
    "ok see u then",
)
IG_SHOP = (
    "yes, 60",
    "mirror is 25",
    "saturday after 11 works",
    "local only, sorry",
    "thank u!",
    "more chairs next week",
    "come by after 10",
    "see u then",
)
POOLS = {"work": WORK, "family": FAMILY, "home": HOME, "shop": SHOP, "tile": TILE, "tow": TOW}


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


FILLER_THREADS: tuple[FillerThread, ...] = (
    FillerThread("item1", "hal_sms", "szabo_sms", 140, ("work",), calls=6),
    FillerThread("item1", "hal_sms", "duda_sms", 25, ("home",), calls=2),
    FillerThread("item1", "hal_wa", "wren_wa", 160, ("family",)),
    FillerThread("item1", "hal_sms", "brandt_sms", 20, ("shop",), calls=2),
    FillerThread("item2", "fer_sms", "pratt_sms", 40, ("home",), calls=2),
    # C35's wrong reading (DEZ = Desiree) finds nothing from Mar 23 through Mar 25
    FillerThread(
        "item2",
        "fer_sms",
        "lamb_sms",
        90,
        ("family",),
        calls=4,
        quiet=(("2026-03-22 00:00:00", "2026-03-27 00:00:00"),),
    ),
    FillerThread("item2", "fer_wa", "mar_wa", 150, ("family",)),
    FillerThread("item2", "fer_sms", "brandt_sms", 20, ("shop",)),
    FillerThread("item2", "fer_ig", "lina_ig", 20, ("ig",)),
    FillerThread("item2", "fer_ig", "mo_ig", 20, ("ig",)),
    FillerThread("item2", "fer_ig", "jt_ig", 20, ("ig",)),
    FillerThread("item3", "oka_sms", "greer_sms", 170, ("family",), calls=8),
    FillerThread("item3", "oka_wa", "mum_wa", 100, ("family",)),
    FillerThread("item3", "oka_sms", "gus_sms", 40, ("tow",), calls=3),
    FillerThread("item3", "oka_sms", "vitale_sms", 50, ("tile",), calls=4),
    FillerThread("item3", "oka_tg", "ike_tg", 80, ("family",)),
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
    return any(ct(a) <= at < ct(b) for a, b in t.quiet)


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

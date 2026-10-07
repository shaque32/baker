"""Case01 story. SYNTHETIC: every person, number, handle and event here is fictional.

This file holds the hand-placed part of the case: people, accounts, devices, contacts and every
message or call that a trap or an affidavit claim depends on. Background chatter comes from
eval/synthetic/filler.py and never touches these threads.

Phone numbers use the 555-01xx range reserved for fiction. Times are written in US Eastern
local time with et(), which converts to UTC (DST starts 2026-03-08 02:00 local).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

# ---------------------------------------------------------------- time

DST_START_UTC = datetime(2026, 3, 8, 7, 0, tzinfo=UTC)  # 2026-03-08 02:00 EST
DST_END_UTC = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)  # 2026-11-01 02:00 EDT
DEVICE_TZ = "America/New_York"


def eastern_offset_min(utc: datetime) -> int:
    return -240 if DST_START_UTC <= utc < DST_END_UTC else -300


def et(local: str) -> datetime:
    """'2026-03-06 18:12:05' in US Eastern -> aware UTC datetime."""
    naive = datetime.fromisoformat(local)
    offset = -240 if naive >= datetime(2026, 3, 8, 3, 0) else -300
    return (naive - timedelta(minutes=offset)).replace(tzinfo=UTC)


# The 4-day WhatsApp gap: no WhatsApp artifact on either device in this UTC window.
WA_GAP_START = et("2026-03-20 00:00:00")
WA_GAP_END = et("2026-03-24 00:00:00")

CASE_START = et("2026-02-16 00:00:00")
CASE_END = et("2026-04-06 00:00:00")

# ---------------------------------------------------------------- people (ground truth only)

PEOPLE = {
    "petrov": "Daniel Petrov",
    "reyes": "Marcus Reyes",
    "sasha": "unknown (uses Telegram 5551234; Reyes saved him as 'Sasha N')",
    "turner": "Alex Turner",
    "ilya": "Ilya Morozov",
    "katya": "Katya Petrova",
    "mama_p": "Petrov's mother",
    "luis": "Luis Reyes",
    "jenna": "Jenna Ortiz",
    "jake": "Jake Brennan",
    "landlord": "Mr. Kim",
    "oksana": "Oksana Lebedeva",
    "mama_r": "Reyes's mother",
    "kevin": "Kevin Shah",
    "tires": "Bay Ridge Tire Supply",
    "dre": "Andre Cole",
}

# ---------------------------------------------------------------- accounts


@dataclass(frozen=True)
class Acct:
    key: str
    app: str  # SMS, WhatsApp, Telegram, Instagram
    identifier: str  # phone (E.164), WhatsApp JID, Telegram user id, Instagram username
    person: str  # key into PEOPLE; 'shared' when more than one person uses it
    # Telegram display names as (valid_from_utc, name); later entries win.
    names: tuple[tuple[datetime, str], ...] = ()

    def name_at(self, at: datetime) -> str | None:
        current = None
        for start, name in self.names:
            if at >= start:
                current = name
        return current


def _phone(n: str) -> str:
    return f"+1212555{n}"


def _wa(n: str) -> str:
    return f"1212555{n}@s.whatsapp.net"


T0 = CASE_START - timedelta(days=60)
RENAME_AT = et("2026-03-10 11:14:00")  # @alex92 -> @northstar

ACCOUNTS: dict[str, Acct] = {
    a.key: a
    for a in [
        # Petrov (item1 owner)
        Acct("pet_sms", "SMS", _phone("0111"), "petrov"),
        Acct("pet_wa", "WhatsApp", _wa("0111"), "petrov"),
        Acct("pet_tg", "Telegram", "7001001", "petrov", ((T0, "Dan P"),)),
        Acct("dpg_ig", "Instagram", "dp_garage", "shared"),  # trap: shared_account
        # Reyes (item2 owner)
        Acct("rey_sms", "SMS", _phone("0122"), "reyes"),
        Acct("rey_wa", "WhatsApp", _wa("0122"), "reyes"),
        Acct("rey_tg", "Telegram", "7001002", "reyes", ((T0, "Marcus R"),)),
        Acct("rey_ig", "Instagram", "m.reyes.auto", "reyes"),
        # trap: handle_change. Same Telegram user id before and after the rename.
        Acct("ns_tg", "Telegram", "5551234", "sasha", ((T0, "@alex92"), (RENAME_AT, "@northstar"))),
        # trap: second_alex. A different person, saved as 'Alex' on item1.
        Acct("turner_sms", "SMS", _phone("0182"), "turner"),
        Acct("ilya_sms", "SMS", _phone("0133"), "ilya"),
        Acct("katya_wa", "WhatsApp", _wa("0155"), "katya"),
        Acct("mamap_wa", "WhatsApp", _wa("0166"), "mama_p"),
        Acct("jake_sms", "SMS", _phone("0144"), "jake"),
        Acct("landlord_sms", "SMS", _phone("0191"), "landlord"),
        Acct("oksana_tg", "Telegram", "7001044", "oksana", ((T0, "Оксана"),)),
        Acct("luis_sms", "SMS", _phone("0177"), "luis"),
        Acct("jenna_sms", "SMS", _phone("0188"), "jenna"),
        Acct("jenna_wa", "WhatsApp", _wa("0188"), "jenna"),
        Acct("mamar_wa", "WhatsApp", _wa("0199"), "mama_r"),
        Acct("kevin_sms", "SMS", _phone("0162"), "kevin"),
        Acct("tires_sms", "SMS", _phone("0105"), "tires"),
        Acct("dre_tg", "Telegram", "7001077", "dre", ((T0, "Dre"),)),
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
    report_tz: str  # 'utc' or 'local': how the report prints timestamps (trap: timezone)
    owner_accounts: tuple[str, ...]
    contacts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = field(default=())


DEVICES: tuple[Device, ...] = (
    Device(
        key="item1",
        evidence_no="Item 1",
        owner="petrov",
        label="Item 1: Apple iPhone 13 seized from Daniel Petrov",
        model="Apple iPhone 13 (A2482)",
        os_version="iOS 17.4.1",
        extraction_type="logical",
        extraction_label="Advanced Logical",
        extracted_at=et("2026-04-07 10:12:00"),
        report_tz="utc",
        owner_accounts=("pet_sms", "pet_wa", "pet_tg", "dpg_ig"),
        contacts=(
            ("Marc Garage", (("Phone-Mobile", _phone("0122")),)),
            ("Alex", (("Phone-Mobile", _phone("0182")),)),  # Alex Turner, not @northstar
            ("Ilya", (("Phone-Mobile", _phone("0133")),)),
            ("Катя", (("Phone-Mobile", _phone("0155")),)),
            ("Мама", (("Phone-Mobile", _phone("0166")),)),
            ("Jake gym", (("Phone-Mobile", _phone("0144")),)),
            ("Mr Kim landlord", (("Phone-Mobile", _phone("0191")),)),
            ("Оксана", (("User ID-Telegram", "7001044"),)),
        ),
    ),
    Device(
        key="item2",
        evidence_no="Item 2",
        owner="reyes",
        label="Item 2: Samsung Galaxy S22 seized from Marcus Reyes",
        model="Samsung Galaxy S22 (SM-S901U)",
        os_version="Android 14",
        extraction_type="file_system",
        extraction_label="Full File System",
        extracted_at=et("2026-04-08 14:40:00"),
        report_tz="local",
        owner_accounts=("rey_sms", "rey_wa", "rey_tg", "rey_ig"),
        contacts=(
            ("Dan P", (("Phone-Mobile", _phone("0111")),)),
            # trap: second_alex. @northstar's Telegram id is linked to 0147, not 0182.
            ("Sasha N", (("Phone-Mobile", _phone("0147")), ("User ID-Telegram", "5551234"))),
            ("Luis primo", (("Phone-Mobile", _phone("0177")),)),
            ("Jenna", (("Phone-Mobile", _phone("0188")),)),
            ("Mom", (("Phone-Mobile", _phone("0199")),)),
            ("Kevin audi", (("Phone-Mobile", _phone("0162")),)),
            ("Bay Ridge Tire", (("Phone-Mobile", _phone("0105")),)),
            ("Dre", (("User ID-Telegram", "7001077"),)),
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
    attachment: str | None = None
    tag: str | None = None  # examiner tag shown in the report


@dataclass(frozen=True)
class Call:
    key: str
    at: datetime
    caller: str
    callee: str
    duration_s: int
    answered: bool = True


EV = "Evidence"  # examiner tag

SCRIPTED_MESSAGES: tuple[Msg, ...] = (
    # ---- Petrov <-> @alex92 / @northstar, Telegram (item1 only). Trap: handle_change.
    Msg(
        "ns01", et("2026-02-20 19:02:11"), "ns_tg", "pet_tg", "hey its sasha. marc gave me ur name"
    ),
    Msg("ns02", et("2026-02-20 19:05:40"), "pet_tg", "ns_tg", "yeah he said. what do u have"),
    Msg("ns03", et("2026-02-20 19:07:02"), "ns_tg", "pet_tg", "same as before. the usual"),
    Msg("ns04", et("2026-02-20 19:10:15"), "pet_tg", "ns_tg", "ok lmk"),
    Msg("ns05", et("2026-02-27 21:14:30"), "ns_tg", "pet_tg", "u around next week"),
    Msg("ns06", et("2026-02-27 21:30:08"), "pet_tg", "ns_tg", "maybe. busy w the shop"),
    Msg("ns07", et("2026-03-03 18:40:51"), "pet_tg", "ns_tg", "how much for 2"),
    Msg("ns08", et("2026-03-03 18:52:19"), "ns_tg", "pet_tg", "same price"),
    Msg("ns09", et("2026-03-10 11:15:03"), "ns_tg", "pet_tg", "new handle. same me"),
    Msg("ns10", et("2026-03-10 11:16:44"), "pet_tg", "ns_tg", "ok"),
    Msg("ns11", et("2026-03-12 20:03:27"), "pet_tg", "ns_tg", "need 2 more by friday", tag=EV),
    Msg("ns12", et("2026-03-12 20:09:02"), "ns_tg", "pet_tg", "friday hard. saturday"),
    Msg("ns13", et("2026-03-12 20:10:10"), "pet_tg", "ns_tg", "fine"),
    Msg(
        "ns14", et("2026-03-12 20:11:36"), "ns_tg", "pet_tg", "the package will be at marcs", tag=EV
    ),
    # trap: timezone, cross-device. Sent 15 minutes BEFORE Luis's call to Reyes (item2 only).
    # This message is on item1 only and the call on item2 only, so the order needs both phones.
    Msg("ns_move", et("2026-03-14 21:50:20"), "pet_tg", "ns_tg", "move it tonight", tag=EV),
    Msg("ns15", et("2026-03-16 22:40:00"), "ns_tg", "pet_tg", "everything ok?"),
    Msg("ns16", et("2026-03-16 22:58:12"), "pet_tg", "ns_tg", "dont know yet"),
    Msg("ns17", et("2026-03-21 13:05:44"), "pet_tg", "ns_tg", "talk later"),
    Msg("ns18", et("2026-03-21 13:20:01"), "ns_tg", "pet_tg", "ok"),
    Msg("ns19", et("2026-03-28 17:45:33"), "ns_tg", "pet_tg", "?"),
    Msg("ns20", et("2026-03-28 18:01:09"), "pet_tg", "ns_tg", "not now"),
    # ---- Reyes <-> @alex92 / @northstar, Telegram (item2 only)
    Msg("rn01", et("2026-02-18 16:00:20"), "rey_tg", "ns_tg", "gave ur name to dan"),
    Msg("rn02", et("2026-02-18 16:05:42"), "ns_tg", "rey_tg", "ok"),
    Msg("rn03", et("2026-03-10 11:20:15"), "ns_tg", "rey_tg", "new handle. same me"),
    Msg("rn04", et("2026-03-10 12:02:50"), "rey_tg", "ns_tg", "ok sasha"),
    Msg("rn05", et("2026-03-13 19:30:05"), "ns_tg", "rey_tg", "saturday still on?"),
    Msg("rn06", et("2026-03-13 19:42:47"), "rey_tg", "ns_tg", "yeah"),
    # trap: second_alex, cross-device. @northstar asks about Alex Turner as a third person.
    Msg(
        "rn07",
        et("2026-03-26 20:14:09"),
        "ns_tg",
        "rey_tg",
        "who is alex turner? dan keeps bringing him up",
    ),
    Msg("rn08", et("2026-03-26 20:20:31"), "rey_tg", "ns_tg", "guy from his work. nobody"),
    # ---- Petrov <-> Reyes, SMS (both devices)
    Msg(
        "pr01", et("2026-03-02 10:15:09"), "rey_sms", "pet_sms", "yo u coming by the shop this week"
    ),
    Msg("pr02", et("2026-03-02 10:40:31"), "pet_sms", "rey_sms", "thursday prob"),
    # trap: timezone. 21:31 EST on Mar 4 is 02:31 UTC on Mar 5; item1 prints UTC.
    Msg("pr03", et("2026-03-04 21:31:00"), "pet_sms", "rey_sms", "its done", tag=EV),
    Msg("pr04", et("2026-03-04 21:33:12"), "rey_sms", "pet_sms", "nice"),
    # trap: meeting_place. Reyes picks the place and time; Petrov agrees.
    Msg(
        "pr05",
        et("2026-03-06 18:12:05"),
        "rey_sms",
        "pet_sms",
        "lets meet monday 8pm. lot behind kings plaza",
    ),
    Msg("pr06", et("2026-03-06 18:20:40"), "pet_sms", "rey_sms", "ok works"),
    Msg("pr07", et("2026-03-09 20:02:13"), "pet_sms", "rey_sms", "here"),
    Msg("pr08", et("2026-03-09 20:03:01"), "rey_sms", "pet_sms", "2 min"),
    Msg(
        "pr10",
        et("2026-03-14 22:09:37"),
        "rey_sms",
        "pet_sms",
        "cops were at the shop earlier. luis just called",
    ),
    Msg("pr11", et("2026-03-14 22:15:02"), "pet_sms", "rey_sms", "ok"),
    Msg(
        "pr12",
        et("2026-03-19 14:22:48"),
        "pet_sms",
        "rey_sms",
        "dont text me about it, use telegram",
        tag=EV,
    ),
    # trap: gap. SMS continues while WhatsApp is silent.
    Msg("pr13", et("2026-03-20 12:10:30"), "rey_sms", "pet_sms", "u good?"),
    Msg("pr14", et("2026-03-20 12:31:55"), "pet_sms", "rey_sms", "yeah"),
    Msg("pr15", et("2026-03-22 16:45:19"), "rey_sms", "pet_sms", "call me when u can"),
    Msg("pr16", et("2026-03-30 09:05:00"), "rey_sms", "pet_sms", "shop closed today"),
    # ---- Petrov <-> Reyes, WhatsApp (both devices). Silent 2026-03-20..23.
    Msg("pw01", et("2026-02-24 11:02:40"), "rey_wa", "pet_wa", "bmw is ready for pickup"),
    Msg("pw02", et("2026-02-24 11:20:03"), "pet_wa", "rey_wa", "ill grab it after work"),
    Msg("pw03", et("2026-03-01 15:44:10"), "pet_wa", "rey_wa", "sending the invoice now"),
    Msg("pw04", et("2026-03-01 15:46:52"), "rey_wa", "pet_wa", "got it thx"),
    Msg("pw05", et("2026-03-17 10:30:00"), "rey_wa", "pet_wa", "audi detail thursday ok?"),
    Msg("pw06", et("2026-03-17 10:41:27"), "pet_wa", "rey_wa", "ilya can do it"),
    Msg("pw07", et("2026-03-19 22:48:05"), "rey_wa", "pet_wa", "night"),
    Msg("pw08", et("2026-03-24 09:12:44"), "pet_wa", "rey_wa", "morning. u at the shop?"),
    Msg("pw09", et("2026-03-24 09:20:18"), "rey_wa", "pet_wa", "yeah come thru"),
    Msg("pw10", et("2026-04-02 17:03:31"), "pet_wa", "rey_wa", "can u look at my brakes sat"),
    # ---- Petrov <-> Reyes, Telegram (both devices)
    Msg("pt01", et("2026-03-19 14:30:12"), "rey_tg", "pet_tg", "ok here"),
    Msg("pt02", et("2026-03-21 20:15:40"), "pet_tg", "rey_tg", "tomorrow"),
    Msg("pt03", et("2026-03-21 20:20:09"), "rey_tg", "pet_tg", "ok"),
    Msg("pt04", et("2026-03-26 18:33:51"), "rey_tg", "pet_tg", "all quiet"),
    # ---- dp_garage (shared) <-> m.reyes.auto, Instagram (both devices). Trap: shared_account.
    Msg(
        "ig01", et("2026-03-15 10:00:27"), "rey_ig", "dpg_ig", "can u do a detail on the audi thurs"
    ),
    Msg("ig02", et("2026-03-15 10:30:02"), "dpg_ig", "rey_ig", "yes 150"),
    Msg(
        "ig03",
        et("2026-03-18 13:02:14"),
        "dpg_ig",
        "rey_ig",
        "its ilya btw, dan's at work. he left his login on my ipad",
    ),
    Msg("ig04", et("2026-03-18 13:05:30"), "rey_ig", "dpg_ig", "lol ok"),
    Msg(
        "ig05", et("2026-03-18 17:40:09"), "dpg_ig", "rey_ig", "got the money, come get it", tag=EV
    ),
    Msg("ig06", et("2026-03-18 17:52:44"), "rey_ig", "dpg_ig", "tmrw"),
    # ---- Petrov <-> Ilya, SMS (item1). Corroborates the shared Instagram login.
    Msg(
        "il01",
        et("2026-03-18 12:55:00"),
        "ilya_sms",
        "pet_sms",
        "using ur insta on my ipad for the audi guy",
    ),
    Msg("il02", et("2026-03-18 12:58:41"), "pet_sms", "ilya_sms", "np"),
    # ---- Petrov <-> Katya, WhatsApp, Russian (item1)
    Msg("ka01", et("2026-03-11 22:15:06"), "pet_wa", "katya_wa", "я волнуюсь за Маркуса", "ru"),
    Msg("ka02", et("2026-03-11 22:17:30"), "katya_wa", "pet_wa", "что случилось?", "ru"),
    Msg("ka03", et("2026-03-11 22:20:12"), "pet_wa", "katya_wa", "потом расскажу", "ru"),
    # ---- Petrov <-> Alex Turner, SMS (item1). Trap: decoy_thread + second_alex.
    # trap: second_alex. On item1 the 0182 'Alex' names himself as Alex Turner.
    Msg(
        "at00",
        et("2026-02-17 09:05:12"),
        "turner_sms",
        "pet_sms",
        "hey its alex turner, new number. save it",
    ),
    Msg("at01", et("2026-03-02 08:45:00"), "turner_sms", "pet_sms", "running late, cover standup?"),
    Msg("at02", et("2026-03-02 08:47:22"), "pet_sms", "turner_sms", "ya"),
    Msg("at03", et("2026-03-25 12:30:18"), "turner_sms", "pet_sms", "did u get them?"),
    Msg(
        "at04",
        et("2026-03-25 12:42:09"),
        "pet_sms",
        "turner_sms",
        "got the tickets. 4 of them",
        tag=EV,
    ),
    Msg("at05", et("2026-03-25 12:43:30"), "pet_sms", "turner_sms", "section 112, $85 each"),
    Msg(
        "at06",
        et("2026-03-25 12:44:02"),
        "pet_sms",
        "turner_sms",
        "",
        attachment="VelvetStatic_Barclays_0403.pdf",
    ),
    Msg(
        "at07",
        et("2026-03-25 12:50:47"),
        "turner_sms",
        "pet_sms",
        "legend. velvet static at barclays!!",
    ),
    Msg(
        "at08",
        et("2026-03-25 12:51:15"),
        "turner_sms",
        "pet_sms",
        "ill venmo u 170 for mine and jess",
    ),
    Msg(
        "at09",
        et("2026-04-04 10:15:51"),
        "turner_sms",
        "pet_sms",
        "that show was insane last night",
    ),
)

SCRIPTED_CALLS: tuple[Call, ...] = (
    Call("c_mar9", et("2026-03-09 19:58:02"), "pet_sms", "rey_sms", 123),
    # The call Reyes says warned him. item2 only; prints local time.
    Call("c_luis", et("2026-03-14 22:05:44"), "luis_sms", "rey_sms", 61),
    Call("c_mar22", et("2026-03-22 17:02:10"), "pet_sms", "rey_sms", 0, answered=False),
)

# Words that only scripted threads may use, so filler can never create or break a trap.
RESERVED_WORDS = (
    "ticket",
    "package",
    "move it",
    "telegram",
    "northstar",
    "alex",
    "sasha",
    "money",
    "kings plaza",
    "the usual",
    "cops",
    "police",
    "delete",
    "concert",
    "show",
    "marc",
    "need 2",
    "its done",
    "insta",
    "ipad",
    "barclays",
    "velvet",
)

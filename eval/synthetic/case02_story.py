"""Case02 story (HIDDEN eval case). SYNTHETIC: every person, number, handle and event is fictional.

Builder threads must not read this file: case02 measures whether the engine generalizes.

A resale ring for tools and generators taken from contractor sites, told through two seized
phones, Feb 16 to Mar 31 2026. Both phones are set to America/Chicago. US DST starts
2026-03-08 02:00 local, so Central is UTC-6 before and UTC-5 after. QUINTERO flies to Los Angeles
on Mar 18 and back late on Mar 23; while he is there his phone runs on Pacific time (PDT, UTC-7),
and the Item 2 report, which prints device local time, prints those rows as (UTC-7).

This file holds the hand-placed part: people, accounts, devices, contacts, one group chat, and
every message or call that a trap or affidavit claim depends on. Background chatter comes from
eval/synthetic/case02_filler.py and never touches these threads.

Phone numbers use the 555-01xx range reserved for fiction. Times are written as US Central
local time with ct() or as Pacific local time with pt(); both return aware UTC datetimes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

# ---------------------------------------------------------------- time

DEVICE_TZ = "America/Chicago"
DST_START_UTC = datetime(2026, 3, 8, 8, 0, tzinfo=UTC)  # 2026-03-08 02:00 CST
DST_END_UTC = datetime(2026, 11, 1, 7, 0, tzinfo=UTC)  # 2026-11-01 02:00 CDT
PACIFIC_OFFSET_MIN = -420  # PDT; Los Angeles is on DST for the whole trip


def central_offset_min(utc: datetime) -> int:
    return -300 if DST_START_UTC <= utc < DST_END_UTC else -360


def ct(local: str) -> datetime:
    """'2026-03-09 20:15:33' in US Central -> aware UTC datetime."""
    naive = datetime.fromisoformat(local)
    offset = -300 if naive >= datetime(2026, 3, 8, 3, 0) else -360
    return (naive - timedelta(minutes=offset)).replace(tzinfo=UTC)


def pt(local: str) -> datetime:
    """'2026-03-20 23:41:10' in US Pacific (PDT, UTC-7) -> aware UTC datetime."""
    return (datetime.fromisoformat(local) - timedelta(minutes=PACIFIC_OFFSET_MIN)).replace(
        tzinfo=UTC
    )


def central(utc: datetime) -> datetime:
    """UTC -> naive Central wall clock."""
    return (utc + timedelta(minutes=central_offset_min(utc))).replace(tzinfo=None)


# QUINTERO's trip. Item 2 switches to Pacific when it lands at LAX and back when it lands in
# Chicago. The phone's own offset is what a device-local report prints (trap: travel_tz).
TRAVEL_START = pt("2026-03-18 13:05:00")
TRAVEL_END = ct("2026-03-24 00:30:00")

CASE_START = ct("2026-02-16 00:00:00")
# Item 1 was seized at BRANDT's arrest on Mar 26; Item 2 at QUINTERO's home on Mar 31.
ITEM1_END = ct("2026-03-26 12:00:00")
ITEM2_END = ct("2026-03-31 08:00:00")

# ---------------------------------------------------------------- people (ground truth only)

PEOPLE = {
    "brandt": "Nolan Brandt",
    "quintero": "Rafael Quintero",
    "hale": "Devon Hale",
    "fuentes": "Marisol Fuentes",
    "salas": "Hector Salas (saved on Item 1 as 'Chino', +13125550143)",
    "aguilar": "Victor Aguilar (QUINTERO's cousin; saved on Item 2 as 'Chino', +13125550158)",
    "mercer": "Kyle Mercer",
    "vic": "unknown (Telegram 'Vic Tools': user 8200417, then user 8200952 from Mar 17)",
    "erin": "Erin Brandt (BRANDT's sister)",
    "gary": "Gary Lindqvist (BRANDT's dispatcher at work)",
    "theo": "Theo Marchetti",
    "mama_q": "QUINTERO's mother",
    "dani": "Daniela Ruiz (QUINTERO's girlfriend)",
    "jaylen": "Jaylen Brooks",
    "wade": "Wade (named in one message only; not on either phone)",
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


def _phone(n: str) -> str:
    return f"+1312555{n}"


def _wa(n: str) -> str:
    return f"1312555{n}@s.whatsapp.net"


T0 = CASE_START - timedelta(days=60)

ACCOUNTS: dict[str, Acct] = {
    a.key: a
    for a in [
        # BRANDT (item1 owner)
        Acct("nb_sms", "SMS", _phone("0119"), "brandt"),
        Acct("nb_wa", "WhatsApp", _wa("0119"), "brandt"),
        Acct("nb_tg", "Telegram", "8100219", "brandt", ((T0, "Nolan B"),)),
        Acct("nb_ig", "Instagram", "nolan.builds", "brandt"),
        # QUINTERO (item2 owner)
        Acct("rq_sms", "SMS", _phone("0125"), "quintero"),
        Acct("rq_wa", "WhatsApp", _wa("0125"), "quintero"),
        Acct("rq_tg", "Telegram", "8100325", "quintero", ((T0, "Rafa Q"),)),
        Acct("rq_ig", "Instagram", "rq.kicks", "quintero"),
        # group members and trap counterparts
        Acct("hale_wa", "WhatsApp", _wa("0131"), "hale"),
        Acct("mari_wa", "WhatsApp", _wa("0136"), "fuentes"),
        # trap: name_collision. Two different people, both saved as 'Chino'.
        Acct("salas_wa", "WhatsApp", _wa("0143"), "salas"),
        Acct("salas_sms", "SMS", _phone("0143"), "salas"),
        Acct("vic_wa", "WhatsApp", _wa("0158"), "aguilar"),
        Acct("vic_sms", "SMS", _phone("0158"), "aguilar"),
        Acct("kyle_sms", "SMS", _phone("0150"), "mercer"),
        # trap: handle_reuse. Same display name, two different Telegram user ids.
        Acct("vt_old", "Telegram", "8200417", "vic", ((T0, "Vic Tools"),)),
        Acct("vt_new", "Telegram", "8200952", "vic", ((T0, "Vic Tools"),)),
        # background
        Acct("erin_wa", "WhatsApp", _wa("0164"), "erin"),
        Acct("erin_ig", "Instagram", "erinb.draws", "erin"),
        Acct("gary_sms", "SMS", _phone("0170"), "gary"),
        Acct("theo_tg", "Telegram", "8100488", "theo", ((T0, "Theo"),)),
        Acct("mama_wa", "WhatsApp", _wa("0173"), "mama_q"),
        Acct("mama_sms", "SMS", _phone("0173"), "mama_q"),
        Acct("dani_sms", "SMS", _phone("0185"), "dani"),
        Acct("jay_ig", "Instagram", "jaylen.hoops", "jaylen"),
    ]
}


@dataclass(frozen=True)
class Group:
    key: str
    app: str
    identifier: str  # group JID
    name: str
    members: tuple[str, ...]  # Acct keys


GROUPS: dict[str, Group] = {
    "wf": Group(
        "wf",
        "WhatsApp",
        "120363041187730125@g.us",
        "Westside Flips",
        ("nb_wa", "rq_wa", "hale_wa", "mari_wa"),
    ),
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
    report_tz: str  # 'utc' or 'local': how the report prints timestamps
    owner_accounts: tuple[str, ...]
    contacts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = field(default=())
    # Story keys of messages the report marks Deleted (trap: deleted_flag).
    deleted: frozenset[str] = frozenset()
    # Group chats the examiner left out of this curated report (trap: absence_curated).
    omitted_groups: tuple[str, ...] = ()
    # (start_utc, end_utc, offset_min): spans when the phone ran on another zone.
    travel: tuple[tuple[datetime, datetime, int], ...] = ()

    def offset_min(self, utc: datetime) -> int:
        """The phone's own UTC offset at that instant."""
        for start, end, off in self.travel:
            if start <= utc < end:
                return off
        return central_offset_min(utc)

    def printed_offset(self, utc: datetime) -> int:
        """The offset the report prints for that instant."""
        return 0 if self.report_tz == "utc" else self.offset_min(utc)


# Telegram rows QUINTERO's phone marks Deleted; all are intact on Item 1.
ITEM2_DELETED_TG = ("tq03", "tq04", "tq05", "tq06", "tq07", "tq12")

DEVICES: tuple[Device, ...] = (
    Device(
        key="item1",
        evidence_no="Item 1",
        owner="brandt",
        label="Item 1: Apple iPhone 14 seized from Nolan Brandt",
        model="Apple iPhone 14 (A2649)",
        os_version="iOS 17.3.1",
        extraction_type="logical",
        extraction_label="Advanced Logical",
        extracted_at=ct("2026-03-28 10:05:00"),
        report_tz="utc",
        owner_accounts=("nb_sms", "nb_wa", "nb_tg", "nb_ig"),
        contacts=(
            ("Rafa", (("Phone-Mobile", _phone("0125")),)),
            ("Devon", (("Phone-Mobile", _phone("0131")),)),
            ("Mari", (("Phone-Mobile", _phone("0136")),)),
            ("Chino", (("Phone-Mobile", _phone("0143")),)),  # Hector Salas
            ("Kyle", (("Phone-Mobile", _phone("0150")),)),
            ("Erin", (("Phone-Mobile", _phone("0164")),)),
            ("Gary dispatch", (("Phone-Mobile", _phone("0170")),)),
            ("Theo", (("User ID-Telegram", "8100488"),)),
        ),
        # Filler rows the report marks deleted, in BRANDT's thread with his dispatcher.
        deleted=frozenset({"f:item1:gary_sms:0010", "f:item1:gary_sms:0033"}),
    ),
    Device(
        key="item2",
        evidence_no="Item 2",
        owner="quintero",
        label="Item 2: Google Pixel 7 seized from Rafael Quintero",
        model="Google Pixel 7 (GVU6C)",
        os_version="Android 14",
        extraction_type="file_system",
        extraction_label="Full File System",
        extracted_at=ct("2026-04-02 13:30:00"),
        report_tz="local",
        owner_accounts=("rq_sms", "rq_wa", "rq_tg", "rq_ig"),
        contacts=(
            ("Nolan", (("Phone-Mobile", _phone("0119")),)),
            ("Devon", (("Phone-Mobile", _phone("0131")),)),
            ("Marisol", (("Phone-Mobile", _phone("0136")),)),
            ("Chino", (("Phone-Mobile", _phone("0158")),)),  # Victor Aguilar, not Salas
            ("Mamá", (("Phone-Mobile", _phone("0173")),)),
            ("Dani", (("Phone-Mobile", _phone("0185")),)),
        ),
        deleted=frozenset(
            set(ITEM2_DELETED_TG)
            | {"f:item2:dani_sms:0005", "f:item2:dani_sms:0061", "f:item2:dani_sms:0140"}
        ),
        omitted_groups=("wf",),
        travel=((TRAVEL_START, TRAVEL_END, PACIFIC_OFFSET_MIN),),
    ),
)

# ---------------------------------------------------------------- scripted events


@dataclass(frozen=True)
class Msg:
    key: str
    at: datetime
    sender: str  # Acct key
    to: str  # Acct key, or a GROUPS key for a group message
    body: str
    lang: str = "en"
    attachment: str | None = None
    tag: str | None = None  # examiner tag shown in the report
    only: str | None = None  # device key when the message reached only one phone


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
    # ---- BRANDT <-> QUINTERO, SMS (both phones)
    Msg("s01", ct("2026-02-19 18:30:22"), "rq_sms", "nb_sms", "u still got the truck this wknd?"),
    Msg("s02", ct("2026-02-19 18:41:05"), "nb_sms", "rq_sms", "ya sat"),
    # DST: 8:15 PM CDT on Mar 9 is 01:15 UTC on Mar 10; at the old CST offset it would be 7:15.
    Msg(
        "s03",
        ct("2026-03-09 20:15:33"),
        "nb_sms",
        "rq_sms",
        "unit 112 at the storage on 4th. code 0419",
        tag=EV,
    ),
    Msg("s04", ct("2026-03-09 20:19:02"), "rq_sms", "nb_sms", "bet"),
    # trap: quoted_speech. BRANDT reports what Wade said.
    Msg(
        "s05",
        ct("2026-03-11 13:02:48"),
        "nb_sms",
        "rq_sms",
        'wade said "bring the cash friday"',
        tag=EV,
    ),
    Msg("s06", ct("2026-03-11 13:10:30"), "rq_sms", "nb_sms", "tell him relax"),
    # trap: travel_tz. 11:41 PM PDT Mar 20 = 06:41 UTC Mar 21 = 1:41 AM CDT Mar 21.
    Msg(
        "s07",
        pt("2026-03-20 23:41:10"),
        "rq_sms",
        "nb_sms",
        "all 6 at devons. done for the week",
        tag=EV,
    ),
    Msg("s08", ct("2026-03-21 08:02:44"), "nb_sms", "rq_sms", "ok"),
    # Sent after Item 1 was seized; only QUINTERO's phone has it.
    Msg("s09", ct("2026-03-26 22:15:09"), "rq_sms", "nb_sms", "yo answer ur phone", only="item2"),
    # ---- BRANDT <-> QUINTERO, WhatsApp direct (both phones)
    Msg("w01", ct("2026-02-22 12:14:50"), "rq_wa", "nb_wa", "game at 7?"),
    Msg("w02", ct("2026-02-22 12:20:31"), "nb_wa", "rq_wa", "cant tonight"),
    # ---- BRANDT <-> QUINTERO, Telegram (both phones). Item 2 marks six rows Deleted.
    Msg("tq01", ct("2026-03-02 19:10:04"), "nb_tg", "rq_tg", "u free thursday"),
    Msg("tq02", ct("2026-03-02 19:15:40"), "rq_tg", "nb_tg", "ya after 5"),
    Msg("tq03", ct("2026-03-12 22:02:17"), "rq_tg", "nb_tg", "how many in the van"),
    Msg("tq04", ct("2026-03-12 22:05:39"), "nb_tg", "rq_tg", "8. 2 yellow ones"),
    Msg("tq05", ct("2026-03-12 22:06:12"), "rq_tg", "nb_tg", "ok i got a guy"),
    Msg("tq06", ct("2026-03-13 07:30:55"), "nb_tg", "rq_tg", "dont bring it to the shop"),
    Msg("tq07", ct("2026-03-13 07:41:20"), "rq_tg", "nb_tg", "ok"),
    Msg("tq08", ct("2026-03-16 20:12:08"), "nb_tg", "rq_tg", "u leaving wed?"),
    Msg("tq09", ct("2026-03-16 20:20:47"), "rq_tg", "nb_tg", "ya back monday night"),
    Msg("tq10", pt("2026-03-22 15:03:26"), "rq_tg", "nb_tg", "flight tmrw 6pm"),
    Msg("tq11", ct("2026-03-22 17:09:10"), "nb_tg", "rq_tg", "k"),
    Msg("tq12", ct("2026-03-25 21:40:02"), "nb_tg", "rq_tg", "they came by my moms today"),
    Msg("tq13", ct("2026-03-25 21:44:18"), "rq_tg", "nb_tg", "who"),
    Msg("tq14", ct("2026-03-25 21:45:01"), "nb_tg", "rq_tg", "u know who"),
    # ---- WhatsApp group 'Westside Flips' (on Item 1; the Item 2 report leaves it out)
    Msg(
        "g01",
        ct("2026-03-06 21:38:05"),
        "hale_wa",
        "wf",
        "nolan got more drills than the hardware store lol",
    ),
    # trap: sarcasm. 9:40 PM CST Mar 6 prints as 3:40 AM Mar 7 in UTC.
    Msg("g02", ct("2026-03-06 21:40:12"), "nb_wa", "wf", "yeah im the kingpin lol", tag=EV),
    Msg("g03", ct("2026-03-06 21:41:30"), "mari_wa", "wf", "jajaja"),
    Msg("g04", ct("2026-03-13 15:02:26"), "rq_wa", "wf", "where we meeting"),
    # trap: group_sender. HALE wrote this, not BRANDT.
    Msg(
        "g05",
        ct("2026-03-13 15:04:51"),
        "hale_wa",
        "wf",
        "drop is at the storage on 4th, bring the van at 6",
        tag=EV,
    ),
    Msg("g06", ct("2026-03-13 15:06:03"), "nb_wa", "wf", "k"),
    # trap: absence_curated, cross-device. QUINTERO and HALE in contact after Mar 22.
    Msg("g07", ct("2026-03-24 12:20:40"), "rq_wa", "wf", "back in chi. devon u around this wk?"),
    Msg("g08", ct("2026-03-24 12:31:15"), "hale_wa", "wf", "ya rafa. thursday"),
    # ---- BRANDT <-> 'Chino' (Hector Salas, 0143), WhatsApp (Item 1)
    Msg("ch01", ct("2026-03-03 17:20:11"), "salas_wa", "nb_wa", "u got anything this week"),
    Msg("ch02", ct("2026-03-03 17:35:48"), "nb_wa", "salas_wa", "maybe thursday"),
    # trap: attachment_only. The report has the file name only.
    Msg(
        "ch03",
        ct("2026-03-11 14:22:09"),
        "nb_wa",
        "salas_wa",
        "",
        attachment="IMG_4471.jpg",
        tag=EV,
    ),
    Msg("ch04", ct("2026-03-11 14:25:30"), "salas_wa", "nb_wa", "those the yellow ones?"),
    Msg("ch05", ct("2026-03-11 14:31:02"), "nb_wa", "salas_wa", "ya. 2 left"),
    Msg("ch06", ct("2026-03-14 10:05:44"), "salas_wa", "nb_wa", "ill come by sunday"),
    Msg("ch07", ct("2026-03-14 10:12:19"), "nb_wa", "salas_wa", "ok"),
    # ---- BRANDT <-> Kyle Mercer, SMS (Item 1). Trap: negation.
    Msg(
        "km01",
        ct("2026-03-24 19:02:37"),
        "kyle_sms",
        "nb_sms",
        "did u sell chino those drills or not",
    ),
    Msg(
        "km02",
        ct("2026-03-24 19:09:44"),
        "nb_sms",
        "kyle_sms",
        "no. i never sold chino anything. drop it",
        tag=EV,
    ),
    Msg("km03", ct("2026-03-24 19:10:58"), "kyle_sms", "nb_sms", "ok ok"),
    # ---- BRANDT <-> 'Vic Tools', Telegram (Item 1). Trap: handle_reuse.
    Msg(
        "v01",
        ct("2026-02-24 16:10:20"),
        "vt_old",
        "nb_tg",
        "need a pressure washer if u got one",
    ),
    Msg("v02", ct("2026-02-24 16:30:02"), "nb_tg", "vt_old", "maybe next wk"),
    Msg("v03", ct("2026-03-02 11:00:45"), "vt_old", "nb_tg", "?"),
    Msg("v04", ct("2026-03-02 11:20:13"), "nb_tg", "vt_old", "not yet"),
    Msg("v05", ct("2026-03-10 09:15:37"), "vt_old", "nb_tg", "lmk"),
    Msg(
        "v06",
        ct("2026-03-17 13:02:50"),
        "vt_new",
        "nb_tg",
        "new acct. old one got banned. its vic",
    ),
    Msg("v07", ct("2026-03-17 13:20:31"), "nb_tg", "vt_new", "ok"),
    Msg("v08", ct("2026-03-25 18:44:06"), "vt_new", "nb_tg", "still need that washer"),
    Msg("v09", ct("2026-03-25 18:50:29"), "nb_tg", "vt_new", "cant rn"),
    # ---- QUINTERO <-> HALE, WhatsApp direct (Item 2). Last row Mar 21, Pacific time.
    Msg("qh01", ct("2026-03-05 18:00:12"), "hale_wa", "rq_wa", "u coming fri?"),
    Msg("qh02", ct("2026-03-05 18:04:40"), "rq_wa", "hale_wa", "ya"),
    # trap: travel_tz. 10:30 PM PDT Mar 19 = 05:30 UTC Mar 20 = 12:30 AM CDT Mar 20.
    Msg(
        "qh03",
        pt("2026-03-19 22:30:15"),
        "rq_wa",
        "hale_wa",
        "van stays at ur place til i get back",
        tag=EV,
    ),
    Msg("qh04", pt("2026-03-19 22:41:02"), "hale_wa", "rq_wa", "np"),
    Msg("qh05", pt("2026-03-21 12:10:33"), "hale_wa", "rq_wa", "all good here"),
    Msg("qh06", pt("2026-03-21 12:15:09"), "rq_wa", "hale_wa", "good"),
    # ---- QUINTERO <-> 'Mamá', WhatsApp, Spanish (Item 2). Trap: translation.
    Msg(
        "mq01",
        ct("2026-03-15 19:20:31"),
        "rq_wa",
        "mama_wa",
        "el miércoles me voy a Los Ángeles unos días. te llamo de allá",
        "es",
    ),
    Msg(
        "mq02",
        ct("2026-03-15 19:26:02"),
        "mama_wa",
        "rq_wa",
        "cuídate mijo, avísame cuando llegues",
        "es",
    ),
    Msg("mq03", pt("2026-03-18 13:40:00"), "rq_wa", "mama_wa", "ya llegué, todo bien", "es"),
    # ---- QUINTERO <-> Marisol Fuentes, WhatsApp, Spanish slang (Item 2). Trap: translation.
    Msg(
        "mf01",
        ct("2026-03-25 16:05:27"),
        "rq_wa",
        "mari_wa",
        "dile a tu hermano que no venga por ahora, la cosa está caliente",
        "es",
        tag=EV,
    ),
    Msg("mf02", ct("2026-03-25 16:09:50"), "mari_wa", "rq_wa", "ok le digo. cuídate", "es"),
    # ---- QUINTERO <-> 'Chino' (Victor Aguilar, 0158, his cousin), WhatsApp (Item 2)
    Msg(
        "vc01",
        ct("2026-02-28 10:02:18"),
        "vic_wa",
        "rq_wa",
        "primo, el domingo comemos en casa de tu mamá. ella me invitó",
        "es",
    ),
    Msg("vc02", ct("2026-02-28 10:15:40"), "rq_wa", "vic_wa", "simón, ahí nos vemos", "es"),
)

SCRIPTED_CALLS: tuple[Call, ...] = (
    Call("k0", ct("2026-02-21 11:02:00"), "nb_sms", "rq_sms", 188),
    # trap: call_count. Five call records Mar 10-14, only two connected.
    Call("k1", ct("2026-03-10 18:22:40"), "nb_sms", "rq_sms", 271),
    Call("k2", ct("2026-03-11 12:03:15"), "rq_sms", "nb_sms", 0, answered=False),
    Call("k3", ct("2026-03-12 21:14:05"), "nb_sms", "rq_sms", 62),  # 00:01:02
    Call("k4", ct("2026-03-13 08:47:30"), "nb_sms", "rq_sms", 0, answered=False),
    # 7:58 PM CDT Mar 14 prints as 3/15 on Item 1 (UTC).
    Call("k5", ct("2026-03-14 19:58:12"), "rq_sms", "nb_sms", 0, answered=False),
    Call("k6", pt("2026-03-21 10:12:00"), "rq_sms", "nb_sms", 340),
    Call("ks", ct("2026-03-05 16:40:00"), "salas_sms", "nb_sms", 133),
)

# Words that only scripted threads may use, so filler can never create or break a trap.
RESERVED_WORDS = (
    "storage",
    "unit",
    "van",
    "cash",
    "drill",
    "generator",
    "kingpin",
    "sold",
    "sell",
    "chino",
    "devon",
    "nolan",
    "rafa",
    "wade",
    "vic",
    "delete",
    "police",
    "cops",
    "caliente",
    "la cosa",
    "ángeles",
    "angeles",
    "me voy",
    "hermano",
    "yellow",
    "washer",
    "drop",
    "code",
    "img_",
    "banned",
    "acct",
    "flips",
    "load",
    "all 6",
    "flight",
    "meeting",
    "shop",
)

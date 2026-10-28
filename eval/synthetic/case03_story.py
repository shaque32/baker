"""Case03 story. SYNTHETIC: every person, number, handle and event here is fictional.

case03 exists to measure a challenge step: a search for counter-evidence on claims that look
close to supported. So every planted counter-record sits where the fixed retrieval
(core/audit/retrieval.py) does not reach it: another app outside the claim's channel filter, a
day outside the claim's window and not the nearest record to it, another conversation, a saved
contact on the other phone, and with no word in common with the claim. eval/synthetic/case03_key.py
says, claim by claim, which explanation direction of core/hypotheses/explain.py should find
each one (group 1), or why only a word-variant search could (group 2).

This file holds the hand-placed part of the case: people, accounts, devices, contacts and every
message or call a claim depends on, plus seeded background chatter that never touches the
threads or windows the claims rest on. Phone numbers use the 555-01xx range reserved for
fiction. Times are written in US Eastern local time with et() (DST starts 2026-03-08).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from eval.synthetic.case01_story import DEVICE_TZ, Acct, Call, Device, Msg, eastern_offset_min, et

__all__ = ["DEVICE_TZ", "Acct", "Call", "Device", "Msg", "eastern_offset_min", "et"]

CASE_START = et("2026-02-23 00:00:00")
CASE_END = et("2026-04-06 00:00:00")
T0 = CASE_START - timedelta(days=60)

# Item 1's WhatsApp is quiet in every conversation from Mar 15 through Mar 18 (claim C09).
# Background chatter keeps off item1's WhatsApp a little wider than that, so the scripted last
# record before (Mar 14, 23:48) and first record after (Mar 19, 09:02) stay the nearest ones.
WA_QUIET_START = et("2026-03-15 00:00:00")
WA_QUIET_END = et("2026-03-19 00:00:00")
FILLER_WA_SKIP = (et("2026-03-14 22:00:00"), et("2026-03-19 10:00:00"))

# ---------------------------------------------------------------- people (ground truth only)

PEOPLE = {
    "orlov": "Pavel Orlov",
    "diaz": "Ruben Diaz",
    "kemal": "Kemal Aydin (works at Orlov's detailing shop, also runs its Instagram)",
    "lena": "Lena Orlova (Orlov's sister)",
    "misha": "Misha Orlov (Orlov's brother)",
    "kirill": "Kirill (Orlov's nephew, used Item 1 on Mar 6 to 8)",
    "dasha": "Dasha (Kirill's girlfriend)",
    "cs1": "CS-1 (confidential source)",
    "bell": "Mr. Bell (Orlov's landlord)",
    "eddie": "Eddie Prado (uses +16465550170; Diaz saved him as 'Eddie P')",
    "jr_parts": "unknown (Instagram jr.parts.nyc)",
    "mia": "Mia K. (detailing customer)",
    "ana": "Ana Diaz (Diaz's wife)",
    "mami": "Diaz's mother",
    "carmen": "Carmen Ramos (Diaz's aunt, Tito's mother)",
    "tito": "Tito Ramos (Diaz's cousin, used Item 2 on Mar 27 to 29)",
    "hector": "Hector (buying a 2009 Civic from Diaz)",
    "ptires": "Pasha Tires (a tire shop, not Orlov)",
    "nostrand": "Nostrand Parts (a parts counter)",
    "gio": "Gio (Diaz's friend)",
    "ig_customers": "detailing customers on Instagram",
}

# ---------------------------------------------------------------- accounts


def _phone(n: str, area: str = "718") -> str:
    return f"+1{area}555{n}"


def _wa(n: str, area: str = "718") -> str:
    return f"1{area}555{n}@s.whatsapp.net"


ACCOUNTS: dict[str, Acct] = {
    a.key: a
    for a in [
        # Orlov (item1 owner). The Instagram business account is an owner account of item1.
        Acct("orl_sms", "SMS", _phone("0111"), "orlov"),
        Acct("orl_wa", "WhatsApp", _wa("0111"), "orlov"),
        Acct("orl_tg", "Telegram", "7101001", "orlov", ((T0, "Pasha O"),)),
        Acct("odet_ig", "Instagram", "orlov.detailing", "shared"),  # Orlov and Kemal
        # Diaz (item2 owner)
        Acct("dia_sms", "SMS", _phone("0122"), "diaz"),
        Acct("dia_wa", "WhatsApp", _wa("0122"), "diaz"),
        Acct("dia_tg", "Telegram", "7101002", "diaz", ((T0, "Ruben D"),)),
        # Orlov's side
        Acct("kemal_sms", "SMS", _phone("0133"), "kemal"),
        Acct("lena_sms", "SMS", _phone("0144"), "lena"),
        Acct("lena_wa", "WhatsApp", _wa("0144"), "lena"),
        Acct("misha_tg", "Telegram", "7101044", "misha", ((T0, "Миша"),)),
        Acct("dasha_sms", "SMS", _phone("0155"), "dasha"),
        Acct("bell_sms", "SMS", _phone("0166"), "bell"),
        Acct("cs1_sms", "SMS", _phone("0190"), "cs1"),
        Acct("e0170_sms", "SMS", _phone("0170", "646"), "eddie"),
        Acct("jr_ig", "Instagram", "jr.parts.nyc", "jr_parts"),
        Acct("mia_ig", "Instagram", "mia.k.nyc", "mia"),
        Acct("dre_ig", "Instagram", "dre.bk.cars", "ig_customers"),
        Acct("sofia_ig", "Instagram", "sofia.rides", "ig_customers"),
        Acct("tony_ig", "Instagram", "tony.v.88", "ig_customers"),
        # Diaz's side
        Acct("ana_sms", "SMS", _phone("0177"), "ana"),
        Acct("ana_wa", "WhatsApp", _wa("0177"), "ana"),
        Acct("mami_wa", "WhatsApp", _wa("0188"), "mami"),
        Acct("carmen_sms", "SMS", _phone("0199"), "carmen"),
        Acct("hector_sms", "SMS", _phone("0123", "646"), "hector"),
        Acct("ptires_sms", "SMS", _phone("0106"), "ptires"),
        Acct("nostrand_sms", "SMS", _phone("0108"), "nostrand"),
        Acct("gio_tg", "Telegram", "7101077", "gio", ((T0, "Gio"),)),
    ]
}

# ---------------------------------------------------------------- devices

DEVICES: tuple[Device, ...] = (
    Device(
        key="item1",
        evidence_no="Item 1",
        owner="orlov",
        label="Item 1: Apple iPhone 14 Pro seized from Pavel Orlov",
        model="Apple iPhone 14 Pro (A2650)",
        os_version="iOS 17.5",
        extraction_type="logical",
        extraction_label="Advanced Logical",
        extracted_at=et("2026-04-08 11:05:00"),
        report_tz="utc",  # prints every time in UTC+0 (claim C04 rests on it)
        owner_accounts=("orl_sms", "orl_wa", "orl_tg", "odet_ig"),
        contacts=(
            ("Ruben Muffler", (("Phone-Mobile", _phone("0122")),)),
            ("Kemal", (("Phone-Mobile", _phone("0133")),)),
            ("Lena", (("Phone-Mobile", _phone("0144")),)),
            ("Миша", (("User ID-Telegram", "7101044"),)),
            ("Dasha", (("Phone-Mobile", _phone("0155")),)),
            ("Mr Bell landlord", (("Phone-Mobile", _phone("0166")),)),
            ("Mikey", (("Phone-Mobile", _phone("0190")),)),
        ),
    ),
    Device(
        key="item2",
        evidence_no="Item 2",
        owner="diaz",
        label="Item 2: Samsung Galaxy S23 seized from Ruben Diaz",
        model="Samsung Galaxy S23 (SM-S911U)",
        os_version="Android 14",
        extraction_type="file_system",
        extraction_label="Full File System",
        extracted_at=et("2026-04-09 15:20:00"),
        report_tz="local",
        owner_accounts=("dia_sms", "dia_wa", "dia_tg"),
        contacts=(
            # Orlov's number, saved under the Russian short form of Pavel (decoy for code
            # that compares name words: "Pasha" shares no letters' prefix with "Pavel").
            ("Pasha", (("Phone-Mobile", _phone("0111")),)),
            ("Pasha Tires", (("Phone-Mobile", _phone("0106")),)),  # decoy: a tire shop
            ("Ana", (("Phone-Mobile", _phone("0177")),)),
            ("Mami", (("Phone-Mobile", _phone("0188")),)),
            ("Tia Carmen", (("Phone-Mobile", _phone("0199")),)),
            ("Hector civic", (("Phone-Mobile", _phone("0123", "646")),)),
            ("Nostrand Parts", (("Phone-Mobile", _phone("0108")),)),
            # Plant for C16: the number the affidavit gives DIAZ is saved on DIAZ's own phone
            # under another person's name. No message or call with it is on Item 2.
            ("Eddie P", (("Phone-Mobile", _phone("0170", "646")),)),
            ("Gio", (("User ID-Telegram", "7101077"),)),
        ),
    ),
)

# ---------------------------------------------------------------- scripted events


def _m(
    key: str,
    local: str,
    sender: str,
    to: str,
    body: str,
    lang: str = "en",
    tag: str | None = None,
) -> Msg:
    return Msg(key, et(local), sender, to, body, lang, None, tag)


EV = "Evidence"  # examiner tag

SCRIPTED_MESSAGES: tuple[Msg, ...] = (
    # ---- ORLOV <-> DIAZ, SMS (both phones)
    _m("ds01", "2026-02-24 10:12:30", "dia_sms", "orl_sms", "u need the lift this week?"),
    _m("ds02", "2026-02-24 10:40:02", "orl_sms", "dia_sms", "maybe thurs"),
    _m("ds03", "2026-02-27 16:05:44", "orl_sms", "dia_sms", "invoice sent"),
    _m("ds04", "2026-03-03 12:20:10", "dia_sms", "orl_sms", "exhaust guy is late again"),
    _m("ds05", "2026-03-03 12:31:55", "orl_sms", "dia_sms", "classic"),
    # C03 (group 2): written while Kirill had the phone, per his misspelled note to Dasha.
    _m(
        "ds_bay",
        "2026-03-07 10:15:20",
        "orl_sms",
        "dia_sms",
        "can u open the bay early tmrw, got 3 to drop",
        tag=EV,
    ),
    _m("ds_bay2", "2026-03-07 10:31:07", "dia_sms", "orl_sms", "ok 7am"),
    # C05 (group 3, clean)
    _m(
        "ds_hondas",
        "2026-03-11 15:42:18",
        "orl_sms",
        "dia_sms",
        "got 4 more, all hondas. same price?",
        tag=EV,
    ),
    _m("ds_hondas2", "2026-03-11 15:50:41", "dia_sms", "orl_sms", "same. bring them thurs"),
    # C08 (group 4): sent on Mar 18, which is three days after the SEARCH, not two.
    _m(
        "ds_quiet",
        "2026-03-18 09:10:00",
        "dia_sms",
        "orl_sms",
        "all quiet here, dont come by",
        tag=EV,
    ),
    _m("ds_quiet2", "2026-03-18 09:25:36", "orl_sms", "dia_sms", "ok"),
    # C15 (group 2): "the paper" is the 2009 Civic's title (see DIAZ <-> Hector below).
    _m("ds_paper", "2026-03-24 14:30:12", "dia_sms", "orl_sms", "bring the paper tmrw", tag=EV),
    _m("ds_paper2", "2026-03-24 14:41:50", "orl_sms", "dia_sms", "ok"),
    _m("ds06", "2026-03-25 17:10:03", "orl_sms", "dia_sms", "outside"),
    # C17 (group 1): sent on the weekend Tito says he was using Ruben's phone.
    _m(
        "ds_keep",
        "2026-03-28 16:10:45",
        "dia_sms",
        "orl_sms",
        "keep ur phone on tonight, might need u at 10",
        tag=EV,
    ),
    _m("ds_keep2", "2026-03-28 16:22:09", "orl_sms", "dia_sms", "ok"),
    _m(
        "ds07",
        "2026-04-01 11:00:27",
        "dia_sms",
        "orl_sms",
        "can u do a full detail on ana's car sat",
    ),
    _m("ds08", "2026-04-01 11:15:40", "orl_sms", "dia_sms", "yes 9am"),
    # ---- ORLOV <-> DIAZ, WhatsApp (both phones). None from Mar 15 through Mar 18.
    _m("dw01", "2026-02-25 09:30:00", "dia_wa", "orl_wa", "invoice for the audi is in ur email"),
    _m("dw02", "2026-02-25 09:45:12", "orl_wa", "dia_wa", "got it"),
    _m(
        "dw03", "2026-03-04 18:10:33", "orl_wa", "dia_wa", "the black acura is done, he can pick up"
    ),
    _m("dw04", "2026-03-04 18:12:02", "dia_wa", "orl_wa", "nice"),
    _m("dw05", "2026-03-10 13:00:47", "dia_wa", "orl_wa", "u coming by later?"),
    _m("dw06", "2026-03-10 13:20:15", "orl_wa", "dia_wa", "after 5"),
    # C09 (group 1): looks like a deliberate move off WhatsApp; the plant says the app broke.
    _m("dw_away1", "2026-03-14 18:24:05", "dia_wa", "orl_wa", "u around tonight?"),
    _m("dw_away", "2026-03-14 18:30:20", "orl_wa", "dia_wa", "dont write me here for a while"),
    _m("dw_back", "2026-03-19 11:20:05", "dia_wa", "orl_wa", "u around?"),
    _m("dw_back2", "2026-03-19 11:41:30", "orl_wa", "dia_wa", "at the shop"),
    # C13 (group 1): the agreement. The retraction is on Telegram the same evening.
    _m(
        "dw_hold",
        "2026-03-21 13:05:09",
        "orl_wa",
        "dia_wa",
        "can u hold the 6 pieces at ur shop til tuesday",
        tag=EV,
    ),
    _m("dw_hold2", "2026-03-21 13:12:44", "dia_wa", "orl_wa", "ok bring them by after 8", tag=EV),
    _m("dw07", "2026-03-30 10:00:18", "orl_wa", "dia_wa", "u still need the buffer back?"),
    _m("dw08", "2026-03-30 10:20:56", "dia_wa", "orl_wa", "keep it til next week"),
    # ---- ORLOV <-> DIAZ, Telegram (both phones)
    _m("dt01", "2026-02-26 20:00:14", "orl_tg", "dia_tg", "u see the game"),
    _m("dt02", "2026-02-26 20:05:31", "dia_tg", "orl_tg", "brutal"),
    # C02 (group 3, clean): exactly nine between Mar 1 and Mar 7, local time. The last two are
    # sent after 10:30 p.m. on Mar 7 and fall on Mar 8 in UTC (decoy for the day boundary;
    # Item 1 prints them as 3/8).
    _m("dt_c1", "2026-03-02 11:05:40", "dia_tg", "orl_tg", "u at the shop today?"),
    _m("dt_c2", "2026-03-02 11:20:03", "orl_tg", "dia_tg", "after 2"),
    _m("dt_c3", "2026-03-03 19:40:26", "orl_tg", "dia_tg", "the guy w the prius came back"),
    _m("dt_c4", "2026-03-03 19:52:11", "dia_tg", "orl_tg", "what he say"),
    _m("dt_c5", "2026-03-03 19:55:48", "orl_tg", "dia_tg", "wants it done by friday"),
    _m("dt_c6", "2026-03-05 18:10:05", "dia_tg", "orl_tg", "here"),
    _m("dt_c7", "2026-03-05 18:12:37", "orl_tg", "dia_tg", "2 min"),
    _m("dt_c8", "2026-03-07 22:38:19", "dia_tg", "orl_tg", "u up?"),
    _m("dt_c9", "2026-03-07 22:40:02", "orl_tg", "dia_tg", "ya. call u in the am"),
    # C06 (group 4): the affidavit says PASHA wrote it; DIAZ did.
    _m(
        "dt_lift", "2026-03-12 17:05:33", "dia_tg", "orl_tg", "need the lift friday after 6", tag=EV
    ),
    _m("dt_lift2", "2026-03-12 17:20:08", "orl_tg", "dia_tg", "ill have it free by 6"),
    # C12 (group 3, clean): Friday -> "sunday" is Sunday Mar 22.
    _m("dt_varick", "2026-03-20 15:15:27", "dia_tg", "orl_tg", "lot on varick, sunday 9pm", tag=EV),
    _m("dt_varick2", "2026-03-20 15:22:50", "orl_tg", "dia_tg", "ok"),
    # C13 plant (group 1): the retraction, on another app inside the claim's day.
    _m(
        "dt_scratch",
        "2026-03-21 22:15:36",
        "dia_tg",
        "orl_tg",
        "scratch that. landlord coming by sunday. cant have them here",
    ),
    _m("dt_scratch2", "2026-03-21 22:19:04", "orl_tg", "dia_tg", "fine ill keep them in the van"),
    _m("dt03", "2026-03-31 19:00:22", "orl_tg", "dia_tg", "u good?"),
    _m("dt04", "2026-03-31 19:30:45", "dia_tg", "orl_tg", "ya all good"),
    # ---- ORLOV <-> CS-1, SMS (item1). C07 (group 4).
    _m("cs01", "2026-03-13 18:00:09", "cs1_sms", "orl_sms", "u around this wknd?"),
    _m("cs02", "2026-03-13 18:30:51", "orl_sms", "cs1_sms", "maybe"),
    _m("cs03", "2026-03-15 11:20:14", "cs1_sms", "orl_sms", "still on for today?"),
    _m("cs_now", "2026-03-15 11:26:40", "orl_sms", "cs1_sms", "not now. after the weekend", tag=EV),
    _m("cs04", "2026-03-24 15:00:33", "cs1_sms", "orl_sms", "everything ok w u?"),
    _m("cs05", "2026-03-24 15:40:02", "orl_sms", "cs1_sms", "busy"),
    # ---- +16465550170 <-> ORLOV, SMS (item1 only). C16 (group 1).
    _m("e01", "2026-03-22 13:00:27", "e0170_sms", "orl_sms", "new # for a bit, save it"),
    _m("e02", "2026-03-22 13:04:10", "orl_sms", "e0170_sms", "ok"),
    _m(
        "e_bush",
        "2026-03-25 16:15:52",
        "e0170_sms",
        "orl_sms",
        "the bushwick guy wants 6 by friday",
        tag=EV,
    ),
    _m("e_bush2", "2026-03-25 16:21:18", "orl_sms", "e0170_sms", "got it ruben, tell him thursday"),
    # ---- ORLOV <-> Lena (item1)
    # C09 plant (group 1): the last WhatsApp record on item1 before the quiet stretch.
    _m(
        "lw_crash",
        "2026-03-14 23:48:06",
        "orl_wa",
        "lena_wa",
        "this app keeps crashing since the update, half my chats wont load. just text me",
    ),
    _m("ls_ok", "2026-03-14 23:55:30", "lena_sms", "orl_sms", "ok will text u"),
    # C09 plant (group 1): the first WhatsApp record on item1 after it.
    _m("lw_fixed", "2026-03-19 09:02:44", "orl_wa", "lena_wa", "its working again finally"),
    # C05 decoys (group 3): a denial and a lost phone near the claimed message; code that
    # reads hand-off words correctly passes over both.
    _m(
        "lw_igor1",
        "2026-03-12 20:01:15",
        "lena_wa",
        "orl_wa",
        "mom says someone called her from igor's number at 2am",
    ),
    _m(
        "lw_igor2",
        "2026-03-12 20:05:39",
        "orl_wa",
        "lena_wa",
        "i never used his phone, ask him yourself",
    ),
    # ---- ORLOV <-> Kemal, SMS (item1)
    _m(
        "ks_left",
        "2026-03-10 18:40:21",
        "kemal_sms",
        "orl_sms",
        "left my phone in ur car lol, can u bring it tmrw",
    ),
    _m("ks_left2", "2026-03-10 18:52:03", "orl_sms", "kemal_sms", "ya"),
    # C12 decoy (group 3): the same street, nothing to do with the meeting.
    _m(
        "ks_varick",
        "2026-03-20 11:30:12",
        "kemal_sms",
        "orl_sms",
        "parking on varick is a nightmare today",
    ),
    _m("ks_varick2", "2026-03-20 11:42:57", "orl_sms", "kemal_sms", "use the lot on bergen"),
    # ---- ORLOV <-> Misha, Telegram (item1). Russian, and Latin-letter Russian (translit).
    # C10 plant (group 2): the boxes are their mother's dishes, written in translit, so no
    # Cyrillic word of the claim's quote matches them.
    _m(
        "mt_box1",
        "2026-03-09 20:15:08",
        "misha_tg",
        "orl_tg",
        "pasha, mama prosit zabrat korobki s posudoj iz garazha i otvezti k nej",
        "ru-Latn",
    ),
    _m(
        "mt_box2",
        "2026-03-09 20:30:41",
        "orl_tg",
        "misha_tg",
        "ok, zaberu na etoj nedele",
        "ru-Latn",
    ),
    _m(
        "mt_claim",
        "2026-03-17 18:40:03",
        "orl_tg",
        "misha_tg",
        "коробки у меня, завтра отвезу",
        "ru",
        tag=EV,
    ),
    _m("mt_claim2", "2026-03-17 18:48:29", "misha_tg", "orl_tg", "хорошо", "ru"),
    _m("mt_18a", "2026-03-18 10:15:50", "misha_tg", "orl_tg", "как мама?", "ru"),
    _m("mt_18b", "2026-03-18 10:31:12", "orl_tg", "misha_tg", "всё хорошо", "ru"),
    _m(
        "mt_box3",
        "2026-03-19 19:45:17",
        "misha_tg",
        "orl_tg",
        "mama zvonila, skazala ty privez korobki. spasibo",
        "ru-Latn",
    ),
    _m("mt_box4", "2026-03-19 19:50:40", "orl_tg", "misha_tg", "da, vse otvez", "ru-Latn"),
    # ---- orlov.detailing (Instagram, item1)
    _m("jr01", "2026-03-17 14:10:22", "jr_ig", "odet_ig", "u still got those parts?"),
    _m("jr02", "2026-03-17 14:30:59", "odet_ig", "jr_ig", "ya. come by thurs"),
    _m("jr03", "2026-03-19 18:30:47", "jr_ig", "odet_ig", "when can i come"),
    _m(
        "jr_cash",
        "2026-03-19 18:42:15",
        "odet_ig",
        "jr_ig",
        "come thru after 9, bring cash",
        tag=EV,
    ),
    _m("jr04", "2026-03-19 18:45:30", "jr_ig", "odet_ig", "bet"),
    # C11 plant (group 1): the business account's other user names himself, the day before.
    _m("mia01", "2026-03-18 10:20:04", "mia_ig", "odet_ig", "hi is my car ready?"),
    _m(
        "mia_kemal",
        "2026-03-18 10:32:41",
        "odet_ig",
        "mia_ig",
        "hi its kemal from the shop. boss is out today, pickup after 4",
    ),
    _m("mia02", "2026-03-18 10:35:09", "mia_ig", "odet_ig", "ok thx kemal"),
    # ---- Kirill on Item 1 -> Dasha, SMS (item1). C03 plant (group 2): misspelled, so no
    # hand-off phrase a literal pattern knows ("usin", "fone", no apostrophe on "pasha").
    _m(
        "kd_fone",
        "2026-03-06 21:40:33",
        "orl_sms",
        "dasha_sms",
        "dis kirill. usin pasha fone til sunday, mine broke. dont txt my #",
    ),
    _m("kd_reply", "2026-03-06 21:44:18", "dasha_sms", "orl_sms", "lol ok. call me later"),
    _m(
        "kd_back",
        "2026-03-08 19:10:52",
        "orl_sms",
        "dasha_sms",
        "bak on my own fone now, ignore this #",
    ),
    # ---- DIAZ <-> Tia Carmen, SMS (item2). C17 plant (group 1): a literal hand-off.
    _m(
        "tc_tito",
        "2026-03-27 18:20:37",
        "dia_sms",
        "carmen_sms",
        "ma its tito. using ruben's phone this weekend, mine is broke. dont call my number",
    ),
    _m("tc_reply", "2026-03-27 18:31:02", "carmen_sms", "dia_sms", "ok mijo, portate bien", "es"),
    # ---- DIAZ <-> Hector, SMS (item2). C15 plant (group 2): slang for the car title.
    _m(
        "hc01",
        "2026-03-23 13:10:44",
        "hector_sms",
        "dia_sms",
        "still want the 09 civic. need the pink slip first n we're done",
    ),
    _m(
        "hc02",
        "2026-03-23 13:25:16",
        "dia_sms",
        "hector_sms",
        "my guy has it, ill get it to u by thursday",
    ),
    _m("hc03", "2026-03-26 09:40:28", "dia_sms", "hector_sms", "come by at 5, got the title for u"),
    _m("hc04", "2026-03-26 17:20:55", "hector_sms", "dia_sms", "here"),
    # ---- DIAZ <-> Ana, WhatsApp (item2)
    # Item 2's WhatsApp goes on while Item 1's is quiet (so only Item 1 is quiet).
    _m("aw_kids", "2026-03-16 12:00:31", "ana_wa", "dia_wa", "can u get the kids at 3 today?"),
    _m("aw_kids2", "2026-03-16 12:05:09", "dia_wa", "ana_wa", "yes"),
    # C12 decoy (group 3): another "sunday" the same day.
    _m(
        "aw_sunday",
        "2026-03-20 09:15:40",
        "ana_wa",
        "dia_wa",
        "sunday is my moms bday dont make plans",
    ),
    _m("aw_sunday2", "2026-03-20 09:20:13", "dia_wa", "ana_wa", "ok"),
)

SCRIPTED_CALLS: tuple[Call, ...] = (
    Call("cl01", et("2026-02-28 12:10:40"), "dia_sms", "orl_sms", 95),
    Call("cl02", et("2026-03-05 17:55:12"), "orl_sms", "dia_sms", 40),
    # C04 (group 1). Item 1 prints this outgoing two-minute call as 11:40:12 PM (UTC+0); on
    # the phone's own clock it was 7:40 p.m., before the 11:20 p.m. theft.
    Call("cl_740", et("2026-03-09 19:40:12"), "orl_sms", "dia_sms", 125),
    Call("cl_miss", et("2026-03-09 21:52:30"), "orl_sms", "dia_sms", 0, answered=False),
    # The call inside the stated time is DIAZ calling ORLOV, not the other way round.
    Call("cl_1139", et("2026-03-09 23:39:05"), "dia_sms", "orl_sms", 112),
    Call("cl03", et("2026-03-11 16:02:27"), "dia_sms", "orl_sms", 210),
    # C14 (group 3, clean) and its clock decoy: a 10:05 a.m. call of the same length that
    # Item 1 prints as 2:05:20 PM (UTC+0).
    Call("cl_1005", et("2026-03-23 10:05:20"), "dia_sms", "orl_sms", 362),
    Call("cl_1404", et("2026-03-23 14:04:30"), "dia_sms", "orl_sms", 370),
    Call("cl04", et("2026-03-26 09:15:03"), "orl_sms", "dia_sms", 75),
    Call("cl05", et("2026-04-02 18:30:48"), "dia_sms", "orl_sms", 300),
)

# Words only scripted messages may use, so background chatter can never create, break or
# crowd a plant: claim quotes, plant words, hand-off and self-introduction words, name words.
RESERVED_WORDS = (
    "phone",
    "fone",
    "cell",
    "ipad",
    "laptop",
    "computer",
    "account",
    "login",
    "password",
    "insta",
    "whatsapp",
    "telegram",
    "app",
    "using",
    "usin",
    "used",
    "borrow",
    "its ",
    "this is",
    "im ",
    "i am",
    "honda",
    "pieces",
    "paper",
    "pink slip",
    "title",
    "civic",
    "varick",
    "sunday",
    "lift",
    "bay",
    "cash",
    "bushwick",
    "korobki",
    "коробк",
    "posud",
    "landlord",
    "scratch",
    "kemal",
    "kirill",
    "tito",
    "pasha",
    "ruben",
    "eddie",
    "igor",
    "crash",
    "update",
)

# ---------------------------------------------------------------- background chatter

SHOP = (
    "running 10 min late",
    "customer at 2",
    "need more microfiber towels",
    "the buffer is acting up again",
    "ceramic coat on the bmw today",
    "invoice paid",
    "can u order more clay bars",
    "be there in 10",
    "who has the keys to the van",
    "closing early today",
    "rain again, no washes",
    "two sets of tires 225/45r17",
    "delivery tuesday am",
    "in stock?",
    "need a quote for brake pads",
    "oil change done",
    "thanks again",
    "all good",
    "got it",
    "sounds good",
    "np",
    "ok",
    "on my way",
    "what time?",
    "after lunch",
    "the jeep needs a second coat",
    "out of wax",
    "send me the address",
    "almost there",
    "five min",
    "how much for the rims",
    "card machine is down",
    "parts came in",
    "back in 20",
    "the vacuum is broken",
    "can u cover saturday",
)
FAMILY = (
    "u up?",
    "omw",
    "lol",
    "did u eat",
    "heading home",
    "call me later",
    "can u grab milk",
    "kids are asleep",
    "what time?",
    "after 6 works",
    "good morning",
    "how was work",
    "long day",
    "rain again",
    "happy bday!!",
    "game tonight?",
    "knicks lost again",
    "pick up some bread",
    "see u tomorrow",
    "love u",
    "drive safe",
    "ok",
    "haha true",
    "cant today",
    "maybe weekend",
    "traffic is crazy",
    "nice",
    "yeah",
    "thx",
    "the heat is off again",
)
HOME = (
    "rent is due friday",
    "the sink is leaking again",
    "boiler guy comes tuesday",
    "ok thanks",
    "will do",
    "trash pickup moved to wed",
)
RU = (
    "привет",
    "как дела?",
    "всё хорошо",
    "позвони мне",
    "я на работе",
    "скоро буду",
    "ты где?",
    "спасибо",
    "доброе утро",
    "спокойной ночи",
    "купи хлеба",
    "я дома",
    "устал",
    "в субботу приедешь?",
    "давай завтра",
    "не могу сейчас",
    "ладно",
    "хорошо",
    "ты поел?",
    "холодно сегодня",
    "напиши когда доедешь",
    "ок",
    "приезжай на ужин",
    "посмотри фото",
    "как работа?",
    "перезвоню",
    "всё нормально",
    "до завтра",
)
ES = (
    "ya llegué",
    "gracias mijo",
    "llámame",
    "te quiero",
    "cuídate",
    "ok mamá",
    "¿comiste?",
    "bendiciones",
    "¿cómo están los niños?",
    "hace frío hoy",
)
IG_CUSTOMER = (
    "hi do u do ceramic coating?",
    "how much for a full detail",
    "can i come by saturday",
    "is the interior done?",
    "thanks, looks amazing",
    "can u fit me in this week",
    "do u do headlight restoration",
    "what time do u open",
    "ok see u then",
)
IG_SHOP = (
    "yes, $350 for ceramic",
    "full detail is $180",
    "come by after 10",
    "should be done by 4",
    "thank u!",
    "we can do thursday",
    "yes we do, $60",
    "we open at 9",
    "come in anytime this week",
)
POOLS = {
    "shop": SHOP,
    "family": FAMILY,
    "home": HOME,
    "ru": RU,
    "es": ES,
}
LANG_OF_POOL = {"shop": "en", "family": "en", "home": "en", "ru": "ru", "es": "es"}


@dataclass(frozen=True)
class FillerThread:
    device: str
    owner_acct: str
    other_acct: str
    n: int
    pools: tuple[str, ...]  # pool keys, chosen per message; "ig" uses the two IG pools
    calls: int = 0  # phone calls; only for SMS threads


FILLER_THREADS: tuple[FillerThread, ...] = (
    FillerThread("item1", "orl_sms", "kemal_sms", 150, ("shop",), calls=6),
    FillerThread("item1", "orl_wa", "lena_wa", 150, ("family",)),
    FillerThread("item1", "orl_sms", "lena_sms", 20, ("family",), calls=3),
    FillerThread("item1", "orl_tg", "misha_tg", 140, ("ru",)),
    FillerThread("item1", "orl_sms", "bell_sms", 25, ("home",), calls=2),
    FillerThread("item1", "odet_ig", "dre_ig", 20, ("ig",)),
    FillerThread("item1", "odet_ig", "sofia_ig", 20, ("ig",)),
    FillerThread("item1", "odet_ig", "tony_ig", 20, ("ig",)),
    FillerThread("item2", "dia_sms", "ana_sms", 180, ("family",), calls=10),
    FillerThread("item2", "dia_wa", "ana_wa", 100, ("family",)),
    FillerThread("item2", "dia_wa", "mami_wa", 120, ("es", "es", "family")),
    FillerThread("item2", "dia_sms", "carmen_sms", 20, ("es",)),
    FillerThread("item2", "dia_sms", "ptires_sms", 40, ("shop",), calls=3),
    FillerThread("item2", "dia_sms", "nostrand_sms", 50, ("shop",), calls=3),
    FillerThread("item2", "dia_tg", "gio_tg", 60, ("family",)),
)


def _random_time(rng: random.Random) -> datetime:
    days = (CASE_END - CASE_START).days
    day = CASE_START + timedelta(days=rng.randrange(days))
    local_hour = rng.choice(range(8, 24))
    at = day + timedelta(hours=local_hour, minutes=rng.randrange(60), seconds=rng.randrange(60))
    # CASE_START is local midnight in UTC; correct for the DST change inside the range
    return at - timedelta(minutes=eastern_offset_min(at) - eastern_offset_min(CASE_START))


def _skipped(t: FillerThread, at: datetime) -> bool:
    """Background chatter stays off item1's WhatsApp around the quiet stretch (claim C09)."""
    is_wa = ACCOUNTS[t.owner_acct].app == "WhatsApp"
    return t.device == "item1" and is_wa and FILLER_WA_SKIP[0] <= at < FILLER_WA_SKIP[1]


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
                if at >= CASE_END or _skipped(t, at):
                    break
                pool = rng.choice(t.pools)
                if pool == "ig":
                    body = rng.choice(IG_SHOP if sender_is_owner else IG_CUSTOMER)
                    lang = "en"
                else:
                    body = rng.choice(POOLS[pool])
                    lang = LANG_OF_POOL[pool]
                sender, to = (
                    (t.owner_acct, t.other_acct)
                    if sender_is_owner
                    else (t.other_acct, t.owner_acct)
                )
                msgs.append(
                    Msg(f"f:{t.device}:{t.other_acct}:{made:04d}", at, sender, to, body, lang)
                )
                made += 1
                at += timedelta(seconds=rng.randint(20, 900))
                if rng.random() < 0.6:
                    sender_is_owner = not sender_is_owner
        for i in range(t.calls):
            at = _random_time(rng)
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
                    rng.randint(15, 900) if answered else 0,
                    answered,
                )
            )
    return msgs, calls

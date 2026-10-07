"""Case01 mock affidavit and DRAFT answer key. SYNTHETIC.

DRAFT ONLY. Every verdict below is the generating agent's proposal. Arsh reviews and decides
each gold verdict line by line; nothing here is gold until it is copied into eval/gold/ by a
human. The affidavit text is generated from this file so claim wording stays verbatim.

Evidence is referenced as (device, story key); the generator resolves keys to stable record
ids such as 'msg:item1:Chats!412'.
"""

from __future__ import annotations

from dataclasses import dataclass

DRAFT_LABEL = "DRAFT (agent proposal, not approved by Arsh)"

# Rules applied consistently across claims; shown in the answer key.
LABELING_RULES = (
    "A meaning claim is contradicted only when the record supplies a specific, independently "
    "corroborated alternative meaning (C20). A merely plausible alternative, or silence, makes "
    "it unproven (C06, C13).",
    "An identity claim is contradicted only by observed evidence incompatible with one person "
    "(C19); a different saved number alone is not enough.",
    "A machine translation is inferred. A claim resting on one is supported only after a human "
    "reader confirms the translation (C17).",
    "Dates and times are judged in the phone's local time, never the printed UTC value.",
)

# The working assumption every claim shares; flagged for Arsh in the answer key.
DEVICE_ATTRIBUTION = (
    "Item 1 is used by PETROV and Item 2 by REYES, so the owner accounts on each phone speak "
    "for them. The key treats this as given, as the affidavit does; it is not proven by the data."
)


@dataclass(frozen=True)
class DraftClaim:
    claim_id: str
    text: str
    claim_type: str
    cross_device: bool
    verdict: str
    core_assumptions: tuple[str, ...]
    evidence: tuple[tuple[str, str], ...]  # (device, story key)
    trap: str | None
    rationale: str


C = DraftClaim

CLAIMS: tuple[DraftClaim, ...] = (
    C(
        "C01",
        'Item 1 contains a contact named "Marc Garage" with the number +1 (212) 555-0122.',
        "identity",
        False,
        "supported",
        ("Item 1's contact list has an entry 'Marc Garage' with +12125550122",),
        (("item1", "contact:Marc Garage"),),
        None,
        "Observed directly in the Item 1 contacts sheet.",
    ),
    C(
        "C02",
        "Between February 20 and March 28, 2026, PETROV exchanged Telegram messages on Item 1 with "
        "a single Telegram account, user ID 5551234, which appears under the handle @alex92 and, "
        "from March 10, 2026, under the handle @northstar.",
        "identity",
        False,
        "supported",
        (
            "Messages under @alex92 and @northstar carry the same Telegram user ID 5551234",
            "The first message is on Feb 20 and the last on Mar 28 (local time)",
        ),
        (("item1", "ns01"), ("item1", "ns08"), ("item1", "ns09"), ("item1", "ns20")),
        "handle_change",
        "Every row in the thread shows user ID 5551234; the display name switches from @alex92 to "
        "@northstar at the Mar 10 'new handle. same me' message.",
    ),
    C(
        "C03",
        "From March 10 through March 31, 2026, Item 1 recorded 13 Telegram messages exchanged "
        "between PETROV and @northstar.",
        "count",
        False,
        "supported",
        ("Count covers Telegram user ID 5551234 only, Mar 10 to Mar 31 local time",),
        tuple(
            ("item1", k)
            for k in [f"ns{i:02d}" for i in range(9, 15)]
            + ["ns_move"]
            + [f"ns{i:02d}" for i in range(15, 21)]
        ),
        "handle_change",
        "Thirteen rows fall in the window, all Telegram user 5551234; none sits near either "
        "boundary after UTC-to-local conversion. The count is derived. Any count that splits "
        "@alex92 from @northstar by handle text instead of user ID would get a different number.",
    ),
    C(
        "C04",
        "PETROV first made contact with @northstar on March 12, 2026, two days after the seizure.",
        "timing",
        False,
        "contradicted",
        (
            "@northstar is a different account from @alex92",
            "No contact with that account before Mar 12",
        ),
        (("item1", "ns01"), ("item1", "ns09"), ("item1", "ns11")),
        "handle_change",
        "The same user ID 5551234 messaged PETROV from Feb 20 as @alex92 and announced the new "
        "handle on Mar 10, so contact began well before Mar 12.",
    ),
    C(
        "C05",
        'On March 12, 2026, PETROV wrote to @northstar: "need 2 more by friday".',
        "communication",
        False,
        "supported",
        ("The outgoing message is on Item 1 with that exact text and date",),
        (("item1", "ns11"),),
        "timezone",
        "Verbatim outgoing Telegram message at 8:03 PM local on Mar 12. Item 1 prints it as "
        "3/13 (UTC), so reading the printed date would wrongly contradict a correct claim.",
    ),
    C(
        "C06",
        'The package in the message "the package will be at marcs", which @northstar sent on '
        "March 12, 2026, contained narcotics.",
        "content_meaning",
        False,
        "unproven",
        ("The 'package' contained narcotics",),
        (("item1", "ns14"),),
        "timezone",
        "The message and its date (8:11 PM Mar 12 local, printed as 3/13 UTC) are observed; "
        "only the meaning is unproven. Nothing on either phone says what the package held, and "
        "no alternative meaning is corroborated (labeling rule 1).",
    ),
    C(
        "C07",
        "On March 6, 2026, PETROV and REYES agreed by text message to meet at 8 p.m. on Monday, "
        "March 9, 2026, in the lot behind Kings Plaza.",
        "communication",
        False,
        "supported",
        (
            "A proposal to meet Monday 8pm behind Kings Plaza on Mar 6",
            "PETROV accepted it",
            "'monday' in a message sent Friday Mar 6 means Monday Mar 9 (derived)",
        ),
        (("item1", "pr05"), ("item1", "pr06")),
        "meeting_place",
        "REYES proposed 'lets meet monday 8pm. lot behind kings plaza' and PETROV replied "
        "'ok works' on Mar 6.",
    ),
    C(
        "C08",
        "PETROV chose the location of the March 9, 2026 meeting.",
        "role",
        False,
        "contradicted",
        ("PETROV proposed or selected the location",),
        (("item1", "pr05"), ("item1", "pr06")),
        "meeting_place",
        "REYES named the place and time; PETROV only agreed. The generator plants no other "
        "message naming the place (a test checks that 'kings plaza' appears exactly once per "
        "phone, sent by REYES). An off-phone conversation cannot be excluded, so the report "
        "should say 'the written record shows'.",
    ),
    C(
        "C09",
        "At about 7:58 p.m. on March 9, 2026, Item 1 placed a call of about two minutes to "
        '+1 (212) 555-0122, the number saved as "Marc Garage".',
        "communication",
        False,
        "supported",
        ("Outgoing call at about 7:58 PM local on Mar 9", "Duration about two minutes"),
        (("item1", "c_mar9"), ("item1", "contact:Marc Garage")),
        "timezone",
        "Item 1 prints 11:58:02 PM (UTC+0), which is 7:58 PM EDT after the Mar 8 DST change; "
        "duration 00:02:03.",
    ),
    C(
        "C10",
        'At 2:31 a.m. on March 5, 2026, PETROV texted REYES "its done".',
        "timing",
        False,
        "contradicted",
        ("The message was sent at 2:31 a.m. local time",),
        (("item1", "pr03"), ("item2", "pr03")),
        "timezone",
        "Item 1 prints 2:31:00 AM (UTC+0). The phone's time zone is America/New_York, so the "
        "local time was 9:31 PM on March 4 (Item 2 shows the same message at 9:31 PM UTC-5).",
    ),
    C(
        "C11",
        "At 10:05 p.m. on March 14, 2026, REYES received a phone call warning him about police "
        'activity at his shop, and after that call PETROV sent the Telegram message "move it '
        'tonight".',
        "timing",
        True,
        "contradicted",
        ("PETROV's message came after the 10:05 p.m. call",),
        (("item1", "ns_move"), ("item2", "c_luis"), ("item2", "pr10")),
        "timezone",
        "The message (to @northstar) is only on Item 1, printed 1:50:20 AM 3/15 (UTC+0). The "
        "call is only on Item 2, printed 10:05:44 PM 3/14 (UTC-4). In UTC the message is 01:50 "
        "and the call 02:05: the message came 15 minutes before the call. Reading the printed "
        "times naively reverses the order. Neither phone alone has both records. The call's "
        "content is only inferred from REYES's later SMS, but the failed timing assumption "
        "already makes the claim contradicted.",
    ),
    C(
        "C12",
        'On March 19, 2026, PETROV texted REYES: "dont text me about it, use telegram".',
        "communication",
        False,
        "supported",
        ("The outgoing SMS is on Item 1 with that text and date",),
        (("item1", "pr12"),),
        None,
        "Verbatim outgoing SMS at 2:22 PM local on Mar 19.",
    ),
    C(
        "C13",
        "PETROV directed REYES's handling and movement of the narcotics.",
        "role",
        False,
        "unproven",
        ("PETROV gave REYES instructions", "The instructions concerned narcotics"),
        (("item1", "pr12"), ("item1", "ns_move"), ("item1", "pr05")),
        None,
        "Short imperatives such as 'dont text me about it, use telegram' are observed, but what "
        "'it' is and who directed whom is interpretation, and 'narcotics' is not established "
        "(as in C06). REYES set the meeting time and place (pr05), which cuts against PETROV "
        "as the director. Role claims stay unproven without more.",
    ),
    C(
        "C14",
        "PETROV and REYES had no contact of any kind between March 20 and March 23, 2026.",
        "absence",
        False,
        "contradicted",
        ("No messages or calls between them on any app in that window",),
        (
            ("item1", "pr13"),
            ("item1", "pr14"),
            ("item1", "pr15"),
            ("item1", "pt02"),
            ("item1", "pt03"),
            ("item1", "c_mar22"),
        ),
        "gap",
        "WhatsApp is silent on both phones, but SMS (Mar 20, Mar 22), Telegram (Mar 21) and an "
        "unanswered outgoing call of 00:00:00 (Mar 22) all fall inside the window. Also a "
        "timezone edge: the last WhatsApp message before the gap prints 3/20 (UTC) but is "
        "10:48 PM Mar 19 local, outside the window.",
    ),
    C(
        "C15",
        "PETROV deleted the WhatsApp messages he exchanged with REYES between March 20 and "
        "March 23, 2026.",
        "event",
        False,
        "unproven",
        ("WhatsApp messages existed in that window", "PETROV deleted them"),
        (("item1", "pw07"), ("item1", "pw08")),
        "gap",
        "No WhatsApp rows exist on either phone in the window and none is flagged deleted. "
        "An absence of artifacts is not evidence of deletion; the pair used SMS and Telegram then.",
    ),
    C(
        "C16",
        'On March 18, 2026, PETROV, using the Instagram account dp_garage, told REYES "got the '
        'money, come get it".',
        "communication",
        False,
        "unproven",
        (
            "PETROV personally wrote the dp_garage message",
            "m.reyes.auto is REYES (Item 2's own Instagram account)",
        ),
        (("item1", "ig05"), ("item1", "ig03"), ("item1", "il01")),
        "shared_account",
        "The message is on the account, but the same account wrote 'its ilya btw, dan's at "
        "work' that afternoon and Ilya texted that he was using the login. Authorship is not "
        "established.",
    ),
    C(
        "C17",
        'On March 11, 2026, PETROV wrote in Russian to the WhatsApp contact saved as "Катя" that '
        "he was worried about Marcus.",
        "content_meaning",
        False,
        "supported",
        ("The outgoing message is in Russian to Катя", "It says he is worried about Marcus"),
        (("item1", "ka01"), ("item1", "contact:Катя")),
        "timezone",
        "'я волнуюсь за Маркуса' means 'I am worried about Marcus'. Original text is the citation. "
        "Printed 3/12 (UTC) but sent 10:15 PM Mar 11 local. A machine translation is inferred, "
        "so 'supported' holds only once a Russian reader confirms the translation; record who.",
    ),
    C(
        "C18",
        "The Telegram user @northstar is ALEXANDER SOKOLOV.",
        "identity",
        False,
        "unproven",
        ("Telegram user 5551234 is Alexander Sokolov",),
        (("item2", "contact:Sasha N"), ("item2", "rn04"), ("item1", "ns01")),
        None,
        "Item 2 saves the account as 'Sasha N' and REYES calls him 'sasha'. That fits a nickname "
        "for Alexander but names no surname; nothing ties the account to Sokolov.",
    ),
    C(
        "C19",
        '@northstar is the same person saved in Item 1 as "Alex" at +1 (212) 555-0182.',
        "identity",
        True,
        "contradicted",
        ("Telegram user 5551234 and the 0182 'Alex' are one person",),
        (
            ("item1", "contact:Alex"),
            ("item1", "at00"),
            ("item2", "rn07"),
            ("item2", "contact:Sasha N"),
        ),
        "second_alex",
        "On Item 1 the 0182 'Alex' introduces himself as 'alex turner'. On Item 2, @northstar "
        "asks REYES 'who is alex turner?', treating him as someone else. That is incompatible "
        "with one person, and it takes both phones. Item 2 also links 5551234 to 0147, not 0182 "
        "(consistent, though not decisive on its own).",
    ),
    C(
        "C20",
        'On March 25, 2026, PETROV told the contact "Alex" that he "got the tickets", which in '
        "this context refers to narcotics.",
        "content_meaning",
        False,
        "contradicted",
        ("'tickets' refers to narcotics",),
        (
            ("item1", "at04"),
            ("item1", "at05"),
            ("item1", "at06"),
            ("item1", "at07"),
            ("item1", "at09"),
            ("item1", "contact:Alex"),
        ),
        "decoy_thread",
        "The thread names a seat section, a per-seat price, a PDF named for a Barclays concert on "
        "Apr 3, the band, and 'that show was insane last night' on Apr 4. Context shows concert "
        "tickets. Contradicted under labeling rule 1: the record supplies a specific, "
        "independently corroborated alternative meaning. The PDF is in the attachments table.",
    ),
)

# Affidavit layout: (page, paragraph parts). A part is plain text or a claim id.
AFFIDAVIT: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            "I, Special Agent R. Calder of the Metro Narcotics Task Force (a fictional agency), "
            "make this affidavit from my training, experience and review of the evidence below.",
        ),
    ),
    (
        1,
        (
            "This affidavit is based on forensic extraction reports for two phones: Item 1, an "
            "Apple iPhone 13 seized from DANIEL PETROV, and Item 2, a Samsung Galaxy S22 seized "
            "from MARCUS REYES.",
        ),
    ),
    (
        1,
        (
            "On March 10, 2026, officers executed a search warrant at a garage operated by REYES "
            "and seized a package.",
        ),
    ),
    (1, ("C01", "C02")),
    (1, ("C03", "C04")),
    (1, ("C05", "C06")),
    (2, ("C07", "C08", "C09")),
    (2, ("C10",)),
    (2, ("C11",)),
    (2, ("C12", "C13")),
    (2, ("C14", "C15")),
    (3, ("C16",)),
    (3, ("C17",)),
    (3, ("C18", "C19")),
    (3, ("C20",)),
    (
        3,
        (
            "Based on the above, I believe there is probable cause that PETROV and REYES "
            "conspired to distribute controlled substances.",
        ),
    ),
)

## 2026-10-29: Message counts can say which side sent them, or that messages went each way (validation rulings R2, R3)
- Changed: two new assumption fields, signed by Arsh on 2026-10-29 in the validation thread
  (the core/contracts.py diff in PROPOSED_CHANGES.md, applied word for word).
  - R2, `sent_by`: "SUBJECT-2 sent SUBJECT-1 exactly three Signal messages" is a count of the
    messages one side sent. The count check (1.2.0) counts only rows whose recorded sender is
    that side's account. Before, any one-way count was refused (#160). The filler sets it only
    for the plain form "<sender> sent <count> ..." with the other side written after "sent":
    the sender is one person, by name or as the exact owner of a phone the claim writes, or
    the accounts by identifier, with no other words beside it. "Received", the passive ("were
    sent by"), a second one-way word, a sender written on both sides, a side written as someone's
    or someone acted for ("PETROV's lawyer", "a friend of REYES"), and a person the assumption
    does not name written after "sent" stay refused. A message to the other side with no
    recorded sender may be one of the counted side's, so "exactly" and "at most" then stay
    inconclusive unless the known ones already exceed the claim. A denial ("has not sent",
    "never sent") is not the plain form, and the other side must be written as the recipient
    (right after "sent", or after "to", "to the Kik account"), not in another clause
    ("while REYES was abroad"). Words after "sent" that limit which messages count ("about the
    delivery", "mentioning money") are refused, since the check reads no message content. A number written another way finds its account (R6).
  - R3, `each_way`: "exchanged ... messages" passes only when each side sent at least one
    counted message in the window. With no stated number it is "at least two"; a stated number
    is still compared. One side's silence never fails the claim: the check says "Not finding a
    message each way does not mean one was never sent" and stays inconclusive. A claim that
    states a count the model left out ("exchanged exactly three", "dozens of") is refused, not
    read as "at least two"; so is a denial ("never exchanged", "had not exchanged"), and any limit the check does not
    read: the clause that says "exchanged" may hold only its own two sides, the phone, the
    count, the app and plain joining words, so "about the delivery", "in Spanish", "with
    photos attached", or a third person or number refuse it. The whole clause is read, past
    any comma. On both forms an app written in the claim is plain wording only when the count
    keeps to that app; otherwise the claim is refused.
  - Later review rounds tightened both forms the same way, each with a test that fails without
    it: a side's identifier counts only written whole, and the accounts side holds only the
    accounts the claim writes there; every phone the claim writes must be one the count
    searches; a count per side ("two each"), per period ("every day", "per hour"), a range
    ("one to two"), a bound written as a sign ("<2", "2+"), and "DMs" or "direct messages"
    are refused; "iMessages" and "emails" need the count kept to that app; and the words
    before the clause may be only its date, time and phone ("in Spanish, PETROV sent ..." is
    refused). "Twenty-one" stays one number.
  - When the two sides share an account (through a confirmed identity link), a count by
    direction is inconclusive: which side sent a message from that account is not known.
  - A count of calls takes neither field: a call log's direction is not read here, so the
    template refuses them with 'call' among the channels.
  - When the model names no phone for a message count and the claim writes exactly one, that
    phone is the one counted.
  - The assumption text says "counting only messages X sent" or "with at least one message
    each way", and ends "Filled from the claim's wording." when code set the field.
    The report is 0.28.0 for this wording.
  Why: run 3 of the Hickman iOS 15 validation needs as many code-checked claims as the data
  allows; one-way and "exchanged" counts were refused only for want of a field.
- Where: branch claude/project-thread-ds0ify (the R2/R3 PR)
- Verified: on this container, 2026-10-29. New tests in tests/checks/test_unit.py (one side's
  count passes and fails, each way passes and never fails on silence, refused directions, the
  contract validators, a message with no recorded sender) and tests/test_assumption_filler.py
  (synthetic case01: one side's count, "exchanged" with and without a number, the written phone,
  and the refused wordings, among them role-named sides); the
  tests that exercise new behaviour fail without it. Replaying run 2's recorded model answers
  through this code on run 2's case database (development data, project files only): 34
  code-checked, 15 check unsettled, 3 expert only (52 tested), up from 33, 14 and 3 at #169;
  11 with a failed core check, unchanged. Both moved claims moved through the new fields; the
  written-phone fill changed no other claim's tier. No 14B run on this code: every number is
  model-free or a replay of recorded answers. `make check`: see the PR.
- Open: the version bump (CONTRACTS_VERSION 0.5.0, schema.sql header) was not in the signed
  diff and is proposed in PROPOSED_CHANGES.md. Every assumption id changes once, since the id
  hashes params with their defaults: a case re-run under this code gets new ids and an expert
  decision on an old id does not carry over (no pilot case exists yet). TEMPLATES_VERSION stays
  1.0.0 (the gold pins it; existing assumptions render as before). Claims writing "iMessage"
  still need fill e to be read as Native Messages. This PR does not change the rules (0.4.0
  on main): a failed one-way count on a filled assumption contradicts without an expert, as any
  failed check on one does. The direction reader is a word allow list, so a rare wording it
  does not know is refused rather than misread; review stopped at Arsh's call (2026-10-29) once
  rounds found only rare wordings and the run 2 replay no longer moved. Any wording found later
  is a follow-up.
- Affects: capabilities (one-way and "exchanged" message counts; count check 1.2.0); no privacy
  change; no customer-facing claim change
- Status doc: pending: in the count check's capabilities, add "counts one side's messages
  ('X sent Y three messages') and 'exchanged' messages (at least one each way, never failed on
  one side's silence)"

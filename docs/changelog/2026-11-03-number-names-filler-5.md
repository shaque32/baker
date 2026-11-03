## 2026-11-03: The expert names a number as the document does; filler 5 reads names with or without "the"
- Changed: In the case05 testability go/no-go (NO-GO, conversion 5 of 33), 11 of the 28 claims
  the step did not convert were stopped by a name code could not resolve. Affidavits name a
  number ("+1 (720) 555-0186 (the "BURNER")") and then write only "the BURNER", which had no
  place to go; and a model's "COURIER" did not match the alias "the COURIER". Seven more had
  the claim's own sentence copied into quoted_text for a call. Four changes, all in code (no
  signed file, no schema change), with FILLER_VERSION 5:
  - **Number names.** The expert can give a number or account id the document's names, with
    `mabillon name-account --identifier "+1 (720) 555-0186" --name "the BURNER" --by
    expert:<name>` or `core/review/actions.name_account`, as phones are named with
    name-device (#139). Each change is a hash-chained audit-log entry `account.names` (the
    identifier's whole list; empty clears it), read back by core/review/account_names.py.
    The identifier must be held by an account in the case. A name is refused when it would
    also match a person (whole name, surname or alias), a phone, an event, another number's
    name, or is itself another account's number or id, with or without a leading "the"; and
    a person alias, phone name or event that would match a number's name is refused too. The
    filler reads the name as that number or id: in a model's account answer (the rules for
    numbers still apply, so a number alone never picks the app) and wherever code reads a
    party from the claim's words (a call's parties, a count's sides and sender, no contact,
    a recipient). A name for an id that is no number is not read as a no-contact party. The
    name is never a person: a model that writes it as one is refused with "write it as an
    account", and it confirms no identity link. Report 0.32.0 lists each name under
    Limitations as the expert's statement, and that it says nothing about who used the
    number. A change marks verdicts Not current (case_changed_after), and the bundle check
    counts it as an input that can change a testability repair. The testability step's
    lookups list a number's name as every account that holds it, "an account, not a person".
  - **"the" either way.** A model's answer matches a person alias or a phone name whole, with
    or without a leading "the" on either side (core/identity/aliases.answers,
    device_names.keys): "COURIER" for "the COURIER". Clash checks compare the form without
    "the" too (aliases.forms), so an alias "the COURIER" is refused when another person is
    named "Courier", and the same holds for events and number names.
  - **A call's unquoted words.** When the claim quotes nothing at all (no straight, curly or
    single quotes), quoted_text on a call's time range (record_time with channel "call") is
    dropped, and the drop is logged with the words, instead of refusing the time range: a
    call holds no words, so its check rests on parties, app and time. Everything else keeps
    refusing words the claim does not quote: a sender, a meaning, a contact's saved name, a
    weekday, and a message's time range, which is picked by its words.
  - **Code reads a plainly stated time.** When the words a model gives for a range state one
    plain range, code's reading of them is the range, not the model's arithmetic: "at about
    11:50 p.m. on November 14, 2025" is 11:42 to 11:58 p.m. (8 minutes either side, as
    stated_windows already reads it), where a model gave 11:50 to midnight and check_window's
    15 minutes let it through. Without this, dropping a call's stray quote would have let such
    a try reach the sheet check and count as a wrong-window try. A range the words leave
    open, or that holds more than one date, keeps the model's checked times as before.
  - **Lookups.** The testability step's lookups find a person alias, a phone name or a
    number's name written with or without its "the", and list a number's name once per app
    that holds it ("an account on SMS: +1 (720) 555-0186, as the expert named it, not a
    person").
  - **Vocabulary.** "texting" names SMS; "spoke by phone", "talked by phone" and "spoke on the
    phone" name a call.
  Agreed with the validation thread, which owns assumption_filler.py, on 2026-11-03, on top of
  #201 (case events, FILLER_VERSION 4).
- Where: PR #209 (merge after #201)
- Verified: tests/test_account_names.py (54 tests on synthetic case01): entering, replacing
  and clearing names; every refusal; holders across apps and WhatsApp ids; the name never
  resolves to a person and adds no person or link; Not current; bundle repair inputs; the
  report line passes the word check; the CLI; a model's account answer, a code-read call
  party, an exchange count and a sent-by count each checked on the named number and passing;
  no contact by a number's name, and refused for an id's name; testability lookups; "the
  COURIER" refused beside a person "Courier"; "the" matching for aliases and phones; the quote
  drop only for a call's time range in a claim with no quotes, and a sender with unquoted
  words still refused, so a dropped quote never leaves a sender without its anchor; "texting"
  and "spoke by phone". make check: see the PR.
- Open: Not measured on any model run. The case05 claims these address are development data
  (case05 is spent); the go/no-go of record is a fresh case06 on Arsh's Mac. A blocker fixed
  does not mean a claim converts: some case05 claims had two. The case screen has no form for
  number names yet (CLI and action only). The eval case setup does not yet enter phone or
  number names from case.json (next PR). A code-made sender (`received_from`) does not read
  a number's name.
- Affects: capabilities (expert-entered number names; the filler resolves more of an
  affidavit's own names, so more claims can be tested by code); no privacy, network or verdict
  rule change; no customer-facing claim.
- Status doc: pending: section 8, in the item that says "The expert can record the document's
  names for each phone (TARGET PHONE, Item 1); ... (#139).", add after it: "The expert can also
  record the document's names for a number or account id ("the BURNER"), with `mabillon
  name-account`; the audit reads a claim's use of the name as that number, never as a person,
  and every report lists the names as the expert's statement. A name matches with or without a
  leading "the" (#209)."

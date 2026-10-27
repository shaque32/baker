## 2026-10-27: Assumption filler finds accounts written another way (#152)
- Changed: in run 1 of the real-export validation, 11 claims were refused because an account
  the model proposed "matches no account in the case". When the words are not an account's
  identifier, `core/audit/assumption_filler.py` now tries three more lookups, each with one
  answer only. The change is code only: no model, prompt, rule, contract, schema, gold, scorer
  or `eval/validation/` file changes.
  - A number written another way. `phone_digits` reads "(919) 888-7386", "919-888-7386" or
    "+1 919 888 7386" as 19198887386, and finds an account written "+19198887386", a phone
    account's own number, or a WhatsApp id. A number without "+" is read only in the North
    American form. A user id made of digits is never taken for a phone number. A number that
    two accounts recorded differently share on the app ("+1 (919) 888-7386" and
    "+19198887386") is refused, never joined (review fix).
  - A person written as an account. "SUBJECT-1" on Signal, where SUBJECT-1 is a person the
    expert created, becomes that person. The checks then take the person's accounts from
    confirmed stipulations and links, never from the words, as for any person. If an account
    not confirmed as theirs carries the same name on that app, the proposal is refused.
  - A display name. The display name of exactly one account on the model's app finds that
    account. A name that several accounts carry is refused, because accounts are never
    merged. For example, real Skype data lists one account under two identifiers.
  - A number or a display name finds an account only on a phone app or on an app the claim
    names. The words alone never pick the app.
  - "@" handles stay handles that the checks resolve, as before.
  - A count or an absence on an account of an app that holds more than the claim's word names
    is refused, however the account was found (review fix). Native Messages holds iMessages
    and SMS together, so a count of "iMessages" on its account would count SMS too.
- Where: PR #152 (branch `claude/project-thread-6i2msb-accounts`), stacked on #150
- Verified: new `tests/test_account_lookups.py`, 33 tests on synthetic case01 with made-up
  wording:
    - phone_digits forms, including a UK number with and without "+" and digits run together;
    - user ids are not numbers;
    - numbers on SMS, WhatsApp and Phone;
    - a number on an app that does not hold it, or that the claim does not name, is refused;
    - a number two accounts recorded differently share is refused;
    - a count or an absence of iMessages on a Native Messages account, found by its display
      name or its identifier, is refused, and a count of "messages" on it is read;
    - a person written as an account, and the template that takes no person;
    - one display name, a display name two accounts carry, and a display name on an app the
      claim does not name;
    - a person whose name another account carries, or two other accounts carry, is refused
      as not theirs;
    - a person written as an account beside a writer is a second party, so a sender (one
      party) is refused and never read as "sent by A or B"; a no-contact keeps both parties;
    - an app's name written as an account is refused;
    - "@" handles are unchanged.
  - The existing filler tests pass unchanged, including the wrong-app refusals.
  - `make check` passes; its eval numbers are in the PR.
  - Read-only replay of run 1's 11 recorded account words on run 1's own case data, done after
    the code was written:
    - 3 numbers, 4 person names and 2 display names now find their party;
    - "ThisIs DfirTwo" on Skype is refused, because two Skype identifiers carry it;
    - "Signal" written as a handle is refused.
    - After the review fixes, one of the 3 numbers is refused again: on that claim (a
      same-account claim) Viber holds the number as two accounts recorded differently, which
      the earlier code joined. Every other replayed proposal is unchanged.
- Open: unmeasured on a run.
  - With #150 and #139, the estimate from run 1's log is that every
    recorded reason is cleared on 36 of the 51 claims with a model-side reason (37 before the
    review fix refused one claim's joined Viber accounts). A claim can still fail on a later
    reason.
  - The same caveat as #150 applies. The lookups were designed after reading run 1's refusals,
    so a run 3 on the same 106 claims is not a held-out test of them.
  - A display name is the export's own field. Whether that name belongs to the person the
    claim means is still the expert's question, as it is for any account.
- Affects: capabilities. More claims can be set up from real affidavit wording.
- Status doc: pending: section 9 item 8 ("Other gaps"): add "an account the claim writes by a
  number in another format, a person's name or one account's display name is found by code;
  a number or display name several accounts carry is refused, never merged (#152)".

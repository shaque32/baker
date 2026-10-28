## 2026-10-28: Code reads a call's parties from the claim, on the app it names (PR #164)
- Changed: The 14B often proposes a call's time range with no party ("a Signal call from
  (919) 888-7386"), which the time template refuses, so the whole claim stayed unproven. In
  core/audit/assumption_filler.py, a record_time proposal for a call that names no party now
  gets its parties from the claim's own words (`_call_parties`):
  - each person the expert created whom the claim names, and each number, account
    identifier or quoted display name it writes;
  - on the one app the claim names for the call (`_call_app`); a call on no named app, on
    two apps, or one whose app appears only inside an address is refused;
  - each must resolve to exactly one person or one account key (one account as two phones
    recorded it counts once), or nothing is filled;
  - a name that is someone's ("SUBJECT-1's phone"), follows "of", "for", "about", "posing
    as" and the like, or sits in a claim with a second clause ("after speaking with",
    "while", "who") fills nothing (Baker Eval on #164);
  - two parties both written as accounts (two numbers, or a number and a quoted name) are
    refused: the checks read every account id as one party, either of them (Codex on #164);
  - a handle, address or long number the case does not know refuses the fill, and so does a
    claim that gives only one side of the call: both sides, or the phone and one account
    ("(919) 888-7386 called the TARGET PHONE"). A person alone may be the phone's own side,
    with the other side a name code cannot read (Codex on #164). A phone the claim writes
    as a side, when the model gave none, scopes the search to that phone and gives the
    window its zone;
  - a quoted name that is both a person's and an account's on the app is refused: it may be
    that account, which no one has linked to the person;
  - the call's app is read outside quoted words.

  The channels become "call" and that app. The time check (core/audit/checks/timing.py,
  version 1.0.2) now reads "call" with an app beside it as that app's calls only; before,
  "call" admitted every app's calls, so a WhatsApp call could pass a Signal claim. "call"
  alone still admits every app's calls. A call's time check never fails, so the risk this
  guards is a false pass. Native phone calls are not filled: this export records them under
  app "unknown", which is the ingest step of the coverage plan. Direction is not checked
  ("placed a call to" passes on a call either way); the assumption says "a call between".
  No frozen file changes. Assumption filling stays local.
- Where: PR #164
- Verified: on this container, 2026-10-28.
  - New tests/test_call_parties.py: parties from persons, numbers, a quoted display name and
    a written identifier; refusals for no app, two apps, an address, an unknown name and no
    party; possessives, roles and second clauses; two account-only parties; an unknown handle, address or number; one side only; the phone kept as the scope and zone; a quoted name a person and an account share; the model's other app; "call" added beside
    an app; a model's own party kept; and the time check searching only the named app's calls.
  - Replay of run 2's recorded answers: unchanged by the possessive, role and clause guards.
  - `make check`: see the PR.
- Open: Direction and native phone calls (coverage plan steps 4 and 5) are not covered. A
  display name two accounts share (one Skype contact recorded under two identifiers) is
  refused, never joined.
- Affects: capabilities (more call claims tested; the time check is stricter for app calls);
  no privacy or customer-facing claim change
- Status doc: pending: in "2. Pipeline (main)", row "5. Assumptions", append to the description:
  "Code reads a call's parties from the claim on the one app it names; the time check reads a
  call with an app as that app's calls only"

## 2026-10-28: Code adds a quoted message's meaning and its stated writer (PR #164)
- Changed: The 14B often proposes who sent a quoted message and when, but leaves out the
  `meaning` assumption a meaning claim needs, so `coverage_gap` refused the whole claim. In
  core/audit/assumption_filler.py, code now fills what the claim plainly states:
  - A claim whose type needs `meaning` and got none gets it on the claim's one quoted message
    (`the_quote`): the words a kept sender or time assumption already quotes, or else the one
    quote in the claim that is no name (a person or an account's identifier or display name)
    and follows a verb of saying, a word for a message or a colon. Two quotes, a quote over
    two lines or a name's lead-in ("saved as", "the LINE user") add nothing. Meaning has no
    check, so only the expert's acceptance covers it: Supported gets harder, never easier.
  - A quoted message now needs a sender assumption in a claim of any type, not only a
    communication claim, so a meaning claim is never tested with its writer unchecked. Outside
    a communication claim, a claim whose every quote is a known name ('13 messages with the
    Telegram user "Marcus R"') quotes no message (Codex on #164).
  - A claim that quotes a message and names its writer ("PETROV wrote to @northstar: ...")
    but got no sender assumption gets one from code: that message, sent by the person
    `stated_sender` reads. `stated_sender` also reads "sent the Telegram message '...'".
  - Each assumptions run records the filler's version (`FILLER_VERSION`, "2") in its params
    as `code_version`. Stored model answers are still reused across filler versions.

  Assumption filling stays local. No frozen file changes.
- Where: PR #164
- Verified: on this container, 2026-10-28.
  - New tests in tests/test_assumption_filler.py: meaning from the quote, the quote rules
    (names, two quotes, a saved name, a wrapped quote, the model's own words), the sender
    rule for any claim type and a count claim quoting only a name, the code-made sender, and
    the run's filler version.
    tests/test_speed.py: the code version is recorded and does not stop reuse.
  - tests/test_filler_replay.py (synthetic case01, Mac-run answers): unchanged at 8 tested,
    10 with the added name. A first version read a saved contact name as a message there;
    the cue rule above now refuses it.
  - `make check`: see the PR.
- Open: The writer is read only from the wordings `stated_sender` knows ("SUBJECT-2 sent
  SUBJECT-1 a message reading ..." names no writer yet), so a meaning claim quoting such a
  message stays unproven under the sender rule. Widening it is step 3 of the coverage plan.
  A code-made meaning is tested only by the expert; reports do not yet mark it as made by
  code.
- Affects: capabilities (more meaning claims tested, each still needing expert acceptance);
  no privacy or customer-facing claim change
- Status doc: pending: in "2. Pipeline (main)", row "5. Assumptions", append to the description:
  "Code adds a meaning assumption on the claim's one quoted message and a sender for the
  writer the claim names; every quoted message needs a sender; runs record the filler
  version"

## 2026-10-28: Code reads more ways a claim names a message's writer (PR #164)
- Changed: In core/audit/assumption_filler.py:
  - `stated_sender` reads more of the ways a claim names who wrote a quoted message: "asked"
    and "posted" ("SUBJECT-1 asked on TikTok: ..."), an app's name between the verb and the
    quote ("told SUBJECT-1 by iMessage: ..."), "in a ... chat", "the ... user", a phone number
    or a quoted name the case knows as the recipient ("wrote to the Discord user 'X': ..."),
    and "sent ... a Signal message to (919) 888-7386 reading ...". Every guard it had stays:
    an unknown quoted word, "reading" after anything but a message, "said" and any phrase that
    can hand the quote to someone else still name no writer. "by" or "via" must be followed
    by an app's name ("a message by SUBJECT-1" names no writer), and a claim whose words before
    the quote forward, quote, relay, repost, share or screenshot a message names no writer
    (Baker Eval on #164). A full stop after a phone number still ends the sentence, so the
    quote after it is handed on (Codex on #164).
  - A sender code makes for the claim's named writer is searched on the apps the claim
    names. When it names only a phone's messages ("texted", "by iMessage"), it is searched on
    every app in the case that holds a phone's messages (SMS, iOS "Native Messages"), never on
    Telegram and the rest; a case with no such app gets no code-made sender. An app named
    inside the quoted message ('texted "use Telegram"') is no app it went by. The one phone
    the claim writes ("On Item 1, ...") scopes the code-made sender; two phones give none
    (Codex on #164).
  - A phone written as an account ("the TARGET PHONE's Kik account") is that phone's own
    accounts on the app the claim names, as the phone recorded them; not its owner's other
    links, and never a phone app.
  - A count's number may be written in words ("thirteen messages", "at least twenty-one
    texts"); "a message" is never a count of one, and a part of a longer number ("twenty
    one", "one hundred", "1,000") is no count. The words after the whole counted phrase
    ("13 text messages or more") are what direction and comparison are read from (Codex on
    #164).

  A wrong writer would fail the sender check and contradict the claim, so each new wording
  has a test that it names the claim's writer and a test that a near wording names none. No
  frozen file changes. Assumption filling stays local.
- Where: PR #164
- Verified: on this container, 2026-10-28.
  - tests/test_assumption_filler.py: 21 new `stated_sender` cases (11 that read the writer,
    10 that must not), the phone's own accounts, counts in words and "a" never a count, and
    the code-made sender's apps, including a phone's messages; parts of numbers.
  - tests/test_filler_replay.py (synthetic case01, Mac-run answers): unchanged.
  - `make check`: see the PR.
- Open: "SUBJECT-2's iMessage '...'" (a possessive) and "a text that read '...'" still name no
  writer: an earlier review kept "PETROV replied to REYES's message 'ok'" ambiguous. Counts in
  words gain nothing on their own today, because the count check counts messages in both
  directions and most counts in words are of calls or of one side's messages.
- Affects: capabilities (more quoted messages get their stated writer checked); no privacy
  or customer-facing claim change
- Status doc: pending: in "2. Pipeline (main)", row "5. Assumptions", append to the description:
  "stated_sender reads more wordings of a message's writer; a phone written as an account is
  its own accounts on the named app; counts may be written in words"

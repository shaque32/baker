## 2026-11-05: App: a conversation names each sender once per side (#PR)
- Changed: Arsh asked about the "phone tags" above every message ("Telegram 7001001 (this phone)
  · outgoing · observed"). On the local screen only, a conversation now names a sender again
  only when the account on that side changes, as a chat app does; the bubble's side gives the
  direction, which moves to the sender's hover title. Selection leaves the app off the sender
  ("7001001 (this phone)"), since the conversation header names it, and the header says "Tier:
  derived; each message observed" instead of every bubble saying "observed". When the source
  printed a name for the sender it leads ("Dan P (5551234)"). The claim and evidence pages
  always name the sender of the record under review, and drop "to <account>" when the one
  account seen answering in the thread is that recipient (a group's recipients still show).
  The account itself is never dropped. The exported report is unchanged (core/report/selection.py
  `sender_words` and the side rule run only when `Links.plain` is on).
- Where: PR #PR (after #222)
- Verified: ruff; `make check` (numbers in the PR); tests/test_demo.py checks Selection names
  5551234 and this phone once each in the first conversation, a repeat from the same account is
  unnamed, the claim page names the record's sender with no "to" in a one-to-one thread, and
  the report still prints "Telegram 5551234 · incoming · observed"; the demo at 1280 px before
  and after.
- Open: Windows browsers and dark mode not looked at.
- Affects: none (wording and layout of the local screen; every sender, account and tier stays
  on the screen; no verdict, rule, label or report change)
- Status doc: no change

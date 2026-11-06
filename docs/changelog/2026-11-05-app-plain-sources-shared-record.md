## 2026-11-05: App: sources in words, a shared record drawn once (#222)
- Changed: the next app fixes from the AI design slop audit (its PRs C and D). Look and wording
  on the local screen only. Selection writes each message's place in words ("item1 · Chats, row
  948" for an Excel sheet row; other locator shapes as they are, the raw text in the hover
  title) and each conversation's tier as "Tier: derived"; the report keeps "item1 Chats!948" and
  "tier derived" (core/report/selection.py gains `Links.plain`, off by default, which only the
  screen turns on). Case: a phone's stipulation drops its device id ("(dev:item1)", now in the
  hover title) and its source shows as "From item1" in plain type, not monospace. Set up: a
  phone file reads "Cellebrite Excel export, logical extraction" with "Made by <tool> <version>"
  under it (the stored kind and extraction ids in the hover title), and the step headings drop
  their "1." to "5." (the step strip numbers them). Claim page: when two assumptions cite the
  same message (demo C05), the first item draws the conversation and the second shows its
  verified quote, its source line, its tier and stance tags and its own Accept and Dismiss, and
  says it is the same message as the item above; nothing about how items are stored or decided
  changes.
- Where: PR #222
- Verified: ruff; `make check` (numbers in the PR); tests/test_demo.py checks C05 draws one
  conversation with two decision forms, the Selection, Case and Set up wording, and that the
  exported report still prints the ids; the demo at 1280 px before and after.
- Open: the Exhibits and context tables still print source and locator in monospace; the report's
  own look (audit PR E) is not started. Windows browsers and dark mode not looked at.
- Affects: none (wording and layout of the local screen; every source and tier stays visible; no
  verdict, rule, label or report change)
- Status doc: no change

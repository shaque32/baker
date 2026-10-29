## 2026-10-28: Checks match a claim's quote across curly quotes and space runs (#165)
- Changed: the sender, time and weekday checks find the record a claim quotes with a fold
  (`fold_text` in `core/audit/checks/_common.py`). Curly quotes (’ ‘ “ ”) read as straight ones,
  and each run of spaces as one space. Every other character must still match, the match is
  still word-aligned, and case still counts. Why: real exports store `I’m` where a claim types
  `I'm`, and keep two spaces where a claim has one. Replaying run 2's recorded answers and
  running the checks on run 2's iOS 15 case database showed those checks finding nothing. Quote
  verification of model labels (`core/audit/quotes.py`) stays exact; the fold is only for
  finding records. The hypotheses explainer uses the same match. Each check's searched text now
  says how it matched. Check versions: sender 1.0.2, weekday 1.0.2, time 1.0.3.
- Where: PR #165
- Verified: on this container, 2026-10-28. New tests in tests/checks/test_unit.py:
  - the fold matches in both directions, and for double quotes, two spaces and a line break;
  - it does not fold a missing apostrophe or a backtick;
  - matches stay word-aligned and case-sensitive;
  - `verify_quote` stays exact.
  The replay of run 2's answers through this code, with the checks run on run 2's case
  database (development data), gives 18 of 35 tested claims with a core check that passed or
  failed, up from 7 at main e99c0a8. The number of claims with a failed core check goes from 4
  to 8; whether those failures are right is unscored until run 3. `make check`: see the PR.
- Open: the fold may make more checks fail as well as pass. On rules 0.3.0 a failed check
  contradicts a claim without an expert, so run 3's measure 7 is what tests it. Other
  typographic forms are not folded: dashes, ellipses and prime marks.
- Affects: capabilities (which records the sender, time and weekday checks find); no privacy
  or customer-facing claim change
- Status doc: pending: in "Other versions (main)", change "check versions same_account, sender,
  time, weekday and absence 1.0.1" to "check versions same_account and absence 1.0.1, sender
  and weekday 1.0.2, time 1.0.3 (#165: curly quotes and runs of spaces fold in the text match;
  time 1.0.2 was #164)"

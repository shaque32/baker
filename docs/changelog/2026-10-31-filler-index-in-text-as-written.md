## 2026-10-31: the filler finds the exchange clause and a duration's words in the claim as written (#190)
- Changed: three places in `core/audit/assumption_filler.py` found a position in a lower-cased
  or case-folded copy of the claim and used it on the claim itself. A copy can be longer ("ß"
  folds to "ss", "İ" lower-cases to two characters), so the position could point past the
  real one. The "exchanged" clause start and the duration's words are now found
  case-insensitively in the text itself, and a "sent" form code cannot place raises a refusal
  instead of an error. Found in review of #172 and #186; no case seen in the data.
  `FILLER_VERSION` goes from 2 to 3, so a run's recorded code version tells runs before #164
  from runs with #164, #169, #172, #186 and this change (Grok Product on #190, point 7).
- Where: PR #190
- Verified: three new tests in `tests/test_assumption_filler.py`, each failing first (a third
  party left out of the exchange clause after 60 "ß"; "or more" missed after "İSMAİL İNCİ"; an
  AttributeError on an unplaced sent form). `make check` passes; eval numbers in the PR.
- Open: none.
- Affects: none (refuses a few more malformed claims; no verdict path change)
- Status doc: no change

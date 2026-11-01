## 2026-10-31: Claims screen progress says it includes Unproven (branch claude/project-thread-rirtrz)
- Changed: The Claims screen's progress label read "Settled", but its count covers every
  audited claim not waiting on the expert, Unproven included. A reader could take "settled" as
  decided for or against (Grok Product review on #190, point 8). It now reads "Not waiting on
  you", with a line under the bar, "Includes N unproven", whenever any claim is unproven. The
  count itself is unchanged. Look and wording only, in `ui/pages.py` and `ui/theme.py`; the
  exported report is unchanged.
- Where: branch claude/project-thread-rirtrz
- Verified: ruff; pytest and make eval (see PR description); a new test in
  `tests/test_review_screen.py` checks the label and that the note matches the Unproven count.
- Open: none.
- Affects: customer-facing claims (the Claims screen's progress wording)
- Status doc: no change

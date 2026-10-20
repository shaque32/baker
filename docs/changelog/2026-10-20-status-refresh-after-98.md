## 2026-10-20: Status refresh after #98 (rules 0.3.0)
- Changed: `docs/PRODUCT_STATUS.md` now matches main `477190d`. It applies #98's pending edits
  (rules 0.3.0, report 0.8.0, section 6 CONTRADICTED row, gate 19 and "11 of 19 gates met",
  section 12 row 1) and fixes spots #98's entry missed that still said a model-only
  "contradicts" makes a claim CONTRADICTED: section 4 "Opus's influence on verdicts" (2nd
  bullet and the known-risk bullet), section 9 limitations 2 and 4, section 12 row 2, and the
  `eval/probe/run_probe.py` module docstring (comment only, no behavior change). Section 10 has
  a fresh `make check`. #97's and #98's entries now name their merges.
- Where: branch `claude/status-refresh-after-98-u6nwod`, not merged.
- Verified: each edit checked against `core/audit/rules.py` (`RULE_VERSION = "0.3.0"`,
  `_AUTO_CONTRADICT` empty), `core/review/status.py` and `docs/PILOT_GATES.md` on main;
  `make check` (Linux, 2026-10-20): 2251 passed, case01 gated 1.00 / 0 false supported,
  unreviewed 0.55, hostile PASS, case02 0.90 / 0 false supported.
- Open: #93 (stance v1.2 for cloud only) was not merged when this opened; its entry waits for
  the next refresh. Section 12 line numbers were not re-checked.
- Affects: customer-facing claims (the status doc no longer says a model can mark a claim
  Contradicted alone). No capability, privacy or performance change.
- Status doc: applied 2026-10-20

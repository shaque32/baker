## 2026-10-20: Status refresh after #98 (rules 0.3.0) and #93 (stance v1.2 for cloud)
- Changed: `docs/PRODUCT_STATUS.md` now matches main `79fc398`. It applies #93's pending edits (cloud
  stance prompt v1.2, Opus results with it, the 14B's v1.2 result, the 14B-vs-Opus comparison). It applies #98's pending edits
  (rules 0.3.0, report 0.8.0, section 6 CONTRADICTED row, gate 19 and "11 of 19 gates met",
  section 12 row 1) and fixes spots #98's entry missed that still said a model-only
  "contradicts" makes a claim CONTRADICTED: section 4 "Opus's influence on verdicts" (2nd
  bullet and the known-risk bullet), section 9 limitations 2 and 4, section 12 row 2, and the
  `eval/probe/run_probe.py` module docstring (comment only, no behavior change), and pilot gate 8
  in `docs/PILOT_GATES.md` for #93. Section 10 has
  a fresh `make check`. #97's and #98's entries now name their merges.
- Where: branch `claude/status-refresh-after-98-u6nwod`, not merged.
- Verified: each edit checked against `core/audit/rules.py` (`RULE_VERSION = "0.3.0"`,
  `_AUTO_CONTRADICT` empty), `core/review/status.py` and `docs/PILOT_GATES.md` on main;
  `make check` (Linux, 2026-10-20): 2278 passed (after merging #93), case01 gated 1.00 / 0 false supported,
  unreviewed 0.55, hostile PASS, case02 0.90 / 0 false supported.
- Open: #93's numbers are copied from its entry, not re-run. Section 12 rows 1 and 2 line numbers re-checked on 0.3.0; rows 3-6 were not.
- Affects: customer-facing claims (the status doc no longer says a model can mark a claim
  Contradicted alone). No capability, privacy or performance change.
- Status doc: applied 2026-10-20

## 2026-10-19: An expert confirms every model contradiction (rules 0.3.0) (#98)
- Changed: a model's or the AI reviewer's "contradicts" no longer marks a claim CONTRADICTED on
  its own (Grok's URGENT FIX on #90; the local 14B scored 58% contradicts precision on the signed
  probe set, bar 90%, Mac run 2026-10-19 at `eee8d15`). Rule 1b in `core/audit/rules.py` counts
  only an expert-accepted contradiction; until then the claim is Unproven and the screen and
  the report both say "Contradiction found, confirm to finalize". On the claim page,
  **Confirm contradiction** takes a one-sentence reason, records the acceptance in the
  hash-chained audit log and re-runs the verdicts in one click (`/evidence/confirm`). A failed
  deterministic check still contradicts without this step. New `_AUTO_CONTRADICT` in
  `core/audit/rules.py`: a versioned map of claim types allowed to contradict without an expert,
  each naming the probe run that qualified it; EMPTY, and each addition needs Arsh's sign-off
  and a rules bump. The report's Versions table prints it ("Model contradictions without an
  expert"). No confidence score. Rules 0.2.2 -> 0.3.0, report 0.7.0 -> 0.8.0. New pilot gate 19.
  METHODS, ARCHITECTURE, review-screen and demo docs updated to match.
  Sign-off: comment 6278243303 on #90 records the approval; Arsh chose "Apply it" for the
  rules change in the owning project thread on 2026-10-20, and final "approved" is pending.
- Where: PR #98 (branch `claude/expert-confirms-contradicts-y6ti2f`), not merged. Holds for Arsh's
  approval of the rules change.
- Verified: `tests/contract/test_rules.py` (unaccepted and AI-accepted contradictions never give
  CONTRADICTED; an expert-accepted one does; the allow-set restores automation for its claim
  type only), `tests/test_report_consistency.py` (screen and report agree before and after a
  one-click confirm; the audit log holds the reason), `tests/test_pipeline.py`. `make eval`
  (Linux, 2026-10-19): case01 gated 1.00 accuracy, 0 false supported (unchanged); case01
  unreviewed 0.60 -> 0.55 (one model-only Contradicted now waits for the expert, by design);
  hostile PASS; case02 0.90, 0 false supported (unchanged).
- Open: the stance prompt fix (guide rules 12 and 23, re-probe with per-item lists) is PR2 and
  not started. Cases audited under 0.2.x keep their verdicts until the verdicts are re-run; the
  report's Versions row says so.
- Affects: capabilities (verdict path), customer-facing claims (model contradictions need the
  expert; Contradicted now always rests on a failed check or an expert's acceptance). No
  privacy or performance change.
- Status doc: pending: header "Rule version" line -> 0.3.0 (`core/audit/rules.py`, this PR);
  section 2 row 11 -> "`decide_verdict` applies rules 0.3.0"; section 6 Outcome table heading
  "(rules 0.3.0)" and CONTRADICTED -> "A failed deterministic check, or a "contradicts" an
  expert accepted; an unaccepted one shows "Contradiction found, confirm to finalize"";
  section 11: add gate 19, met by #98, and "11 of 19 gates met"; section 12 row 1:
  `RULE_VERSION = "0.3.0"`.

## 2026-11-02: an override to Supported needs accepted support, and a bad stored verdict no longer takes the case down (#205)
- Changed: on the claim page (and `mabillon verdict --set supported`), "Override the verdict" to
  Supported on a claim whose verdict cites no evidence (demo C05, unproven) stored Supported with
  nothing cited. The frozen VerdictDecision contract refuses that row, so every page of the case
  (claim, claims, case, report) failed from then on. `core/review/actions.py` override_verdict
  now refuses Supported until the expert has accepted at least one supporting item on an
  observed record of a core assumption (the items rule 3c counts), and the verdict then cites
  those items; the override's audit-log entry records them (`cited_evidence_ids`) and the
  bundle verifier replays them and checks each was the claim's and expert-accepted when the
  override was made. The override reads its row back through the contract before it commits,
  so no override can store an unreadable verdict again. A case that already holds such a row
  (`core/pipeline.py` load_verdict raises StoredVerdictInvalid, an InvariantViolation) shows a
  page saying why with a "Re-run the verdicts" button (409, not a crash); the re-run decides
  every claim again under the rules and the screen works again. This enforces the existing
  rule (CLAUDE.md: never SUPPORTED without an expert accepting its supporting evidence); it
  does not change `core/audit/rules.py`, RULE_VERSION, contracts or schema. It does narrow
  overrides: Supported over a contradicted or unproven verdict now needs accepted support, where
  before it was stored (and from contradicted, cited the contradicting items).
- Where: PR #205
- Verified: tests/test_verdict_override.py (7 tests: refusal stores and logs nothing; the screen
  flashes the reason and every page stays 200; dismissed support does not count; accepted
  support is cited, logged, renders, and the exported bundle verifies, also after overriding
  away again; the verifier refuses a forged override citing an unaccepted or foreign item; an
  old bad row shows the re-run page and the re-run repairs it; the CLI names `mabillon
  redecide` and it repairs the row); `make check` (numbers in the PR).
- Open: a contradicted-to-Supported override keeps the contradiction's cited checks alongside
  the accepted support. Bundles made before this keep verifying (their overrides carry no
  `cited_evidence_ids`). On the command line a command that meets such a row prints the
  message and the `mabillon redecide` command that repairs it.
- Affects: capabilities (override to Supported narrowed to accepted support; bad stored row
  recoverable from the screen)
- Status doc: pending: §4 "Verdicts come from code or the expert", after "under the expert's
  name in the audit log.", add "An override to Supported needs at least one supporting item
  the expert accepted on an observed record of a core assumption, and cites those items; the
  bundle verifier replays them (#205)." §12 table row 1 (Verdicts come from versioned rules),
  after "as the expert's decision;", add "an override to Supported needs expert-accepted support
  and cites it;".

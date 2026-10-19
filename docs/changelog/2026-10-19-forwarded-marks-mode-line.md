## 2026-10-19: Report says where a case keeps forwarded marks (#95)
- Changed: a case made before contracts 0.4.0 has no forwarded columns, so it fails closed from
  the coverage list but cannot name an original author, and nothing said so (Grok Product
  follow-up on #89). The report's Versions table now has a "Forwarded marks" row: "on the
  record" or "coverage list only (case made before contracts 0.4.0)", which also warns that a
  source imported before #73 has no list, so its forwarded messages are not marked (Codex).
  Report 0.6.0 -> 0.7.0.
  PILOT_GATES gate 4 now records #89 as merged (gate still not met), and its As of line names
  main `0dc55dc` (Codex).
- Where: PR #95
- Verified: the old-schema test in `tests/test_ufdr.py` checks both labels; `make check` and eval
  in the PR description.
- Open: AXIOM does not read forwarded marks (parked until a public sample has the field); the
  original text of a forward is not imported.
- Affects: customer-facing claims (one new row in the report's Versions table). No verdict,
  privacy or performance change.
- Status doc: pending: header, set Contracts to "0.4.0 on main (`core/contracts.py`, forwarded
  columns, PR #89)"; limitation 3, replace "(PR #89, not merged)" with "(PR #89, merged
  2026-10-19)" and end the paragraph with "the report's Versions table says which mode a case
  is in (\"Forwarded marks\", #95)."; archive, set #89's `Where:` in `docs/CHANGELOG_AI.md` to
  "main (PR #89, merge 4513a4a, 2026-10-19)".

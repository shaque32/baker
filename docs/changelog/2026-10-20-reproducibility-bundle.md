## 2026-10-20: reproducibility bundle, export and offline verify (#104)
- Changed: `baker export-bundle` writes one zip per case (input hashes, build and versions,
  model identity, every table incl. model calls with raw output, expert reviews, verdicts and
  the full audit log, the report, a method note); producing one is the examiner's choice on
  counsel's advice, needs `--by expert:`, is logged (`bundle.export`) and refuses an
  unfinished audit. `baker verify-bundle` checks it offline and re-derives every verdict of the
  exported run from the recorded labels and the expert decisions as they stood when each was
  decided; any edited file, label, decision, input hash, log entry, verdict or report fails.
  New audit-log content, no schema change: `cloud.received` per cloud answer (API-reported
  model, message and request ids, raw-output SHA-256), and each `pipeline.claim` entry names
  the model calls stored while it ran with one SHA-256 over them. Why: legal defensibility
  (Arsh's brief, 2026-10-20): equal access, authentication, hosted-model reproducibility.
- Where: PR #104
- Verified: tests/test_bundle.py (18: round trips on a reviewed case01 and a cloud-path case01
  with a stand-in API; 11 tampering cases fail); full suite 2299 passed before a lint-only fix;
  make eval unchanged (case01 1.00, 0 false supported; unreviewed 0.55; hostile PASS; case02
  aggregate 0.90, 0 false supported). Not tried on a real case or a real Anthropic answer.
- Open: CLI only, no screen button. The anchor is the audit log's last hash printed on the
  report; no signature or outside timestamp. Only the exported run's verdicts are re-derived.
  Re-generating local labels on another machine untested. The bundle is plaintext even for an
  encrypted case (the export says so).
- Affects: capabilities (new export/verify); privacy (a bundle holds case content in plain
  form, only when the examiner makes one; nothing is sent); customer-facing claims (recorded
  labels and rules are reproducible; cloud labels still cannot be regenerated).
- Status doc: pending: §8 add item 6 "Reproducibility bundle (#104): `baker export-bundle`
  (examiner's choice, logged, plaintext) and `baker verify-bundle` (offline; re-derives every
  verdict of the exported run from recorded labels and expert decisions; docs/bundle.md); CLI
  only"; §4 "Failure handling" add "each answer is logged as `cloud.received` (API-reported
  model, message and request ids, raw-output SHA-256)"; §12 row 5 add to Evidence "a
  reproducibility bundle carries every table and log entry, and `baker verify-bundle`
  re-derives the verdicts offline (#104)"; §3 last paragraph add "each claim's audit-log entry
  binds its stored model calls by SHA-256 (#104)".

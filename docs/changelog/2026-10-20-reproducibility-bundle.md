## 2026-10-20: reproducibility bundle, export and offline verify (#104)
- Changed: `baker export-bundle` writes one zip per case (input hashes, build and versions,
  model identity, every table incl. model calls with raw output, expert reviews, verdicts and
  the full audit log, the report, a method note); producing one is the examiner's choice on
  counsel's advice: it lists what the bundle would hold and writes nothing without
  `--confirm-counsel-reviewed` and `--by expert:`; an encrypted case's bundle is encrypted
  (AES-256-GCM, scrypt bundle passphrase), never plain; the export is logged (`bundle.export`,
  with the bundle's SHA-256) only after the file is written, and the file is removed if that
  entry fails; an unfinished audit is refused. `verify-bundle` exits 0 only when every check
  ran and passed, 2 when something could not be checked, 1 on any failure. `baker
  verify-bundle` checks it offline and re-derives every verdict of the exported run from the recorded labels and the expert decisions as they stood when each was
  decided; any edited file, label, rationale, source locator, assumption, check result, AI
  review, expert review, claim, model call, stipulation, decision, input hash, log entry,
  verdict, model identity, timeline setting, method note or report fails. New audit-log content, no schema change: `cloud.received` per
  cloud answer, refused ones too (API-reported model, message and request ids, raw-output
  SHA-256, why refused), and each `pipeline.claim` entry names the model calls stored while it
  ran with one SHA-256 over their whole rows, plus one SHA-256 over the rows its verdict rests
  on (`rows_sha256`) and one over the claim (`claim_sha256`). No export while a newer audit is
  unfinished. Why: legal defensibility
  (Arsh's brief, 2026-10-20): equal access, authentication, hosted-model reproducibility.
- Where: PR #104
- Verified: tests/test_bundle.py (52: round trips on a reviewed case01 and a cloud-path case01
  with a stand-in API; 32 tampering and malformed-bundle cases fail without a crash; a refused
  cloud answer is logged with its ids; an answer that cannot be logged pauses the
  audit; a retried send logs one answer; no export without the confirmation; an encrypted case
  never exports in plain form; a failed write leaves no bundle and no success entry; partial
  coverage never reads as fully verified); full suite 2334 passed, 8 skipped;
  make eval unchanged (case01 1.00, 0 false supported; unreviewed 0.55; hostile PASS; case02
  aggregate 0.90, 0 false supported). Not tried on a real case or a real Anthropic answer.
- Open: CLI only, no screen button. The anchor is the audit log's last hash printed on the
  report; no signature or outside timestamp. Only the exported run's verdicts are re-derived.
  Re-generating local labels untested, on the same machine or another (a 14B repeat-run
  check is planned). Default scope is the whole case;
  whether to export only what the verdicts rest on is Arsh's open decision (Baker Product
  review on #104).
- Affects: capabilities (new export/verify); privacy (a bundle holds case content, plain only
  for a plain case, and only when the examiner confirms one; nothing is sent); customer-facing claims (recorded
  labels and rules are reproducible; cloud labels still cannot be regenerated).
- Status doc: pending: §8 add item 6 "Reproducibility bundle (#104): `baker export-bundle`
  (examiner's choice after counsel review, logged with its SHA-256, encrypted for an encrypted case) and `baker verify-bundle` (offline; re-derives every
  verdict of the exported run from recorded labels and expert decisions; docs/bundle.md); CLI
  only"; §4 "Failure handling" add "each answer is logged as `cloud.received` (API-reported
  model, message and request ids, raw-output SHA-256)"; §12 row 5 add to Evidence "a
  reproducibility bundle carries every table and log entry, and `baker verify-bundle`
  re-derives the verdicts offline (#104)"; §3 last paragraph add "each claim's audit-log entry
  binds its stored model calls by SHA-256 (#104)".

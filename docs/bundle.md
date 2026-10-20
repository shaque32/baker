# Reproducibility bundle

A bundle lets the other side re-check everything Baker added to an examiner's findings without
our help: which files went in, which model labelled what, what the expert decided, and that the
versioned rules turn those recorded labels and decisions into exactly the verdicts reported.

Producing a bundle is the examiner's choice, made on counsel's advice. Baker never makes or
sends one on its own, and nothing is shared by default. A bundle is **not encrypted** and holds
case content (record text, the prompts sent to the model and its answers), so handle it under
the case's protective order.

## Export

```
baker export-bundle --db <case>/case.db --out bundle.zip --by "expert:<your name>"
```

It prints the notice above, the bundle's SHA-256 (keep it: it names this exact bundle) and the
audit log's last hash. The export is logged in the case's audit log (`bundle.export`, by you),
and the bundle holds the case as it stands, that entry included. Only the latest completed
audit can be exported; resume an unfinished audit (or re-run the verdicts) first. A case whose
audit log does not verify is refused, as for a report.

## What is inside

| File | What it holds |
|---|---|
| `bundle.json` | Format and version; the Baker build (release, commit) and every version (pipeline, contracts, rules, report, quote check) that exported it and that ran the audit; each input's file name, SHA-256, importer and importer version; each model run's identity; the audit log's entry count and last hash; every other file's SHA-256 |
| `METHOD.md` | Plain-English method note: what Baker did, who labelled the evidence, how to check the bundle, its limits |
| `report.html` | The claims report, rendered from exactly the rows in `tables/` |
| `tables/<table>.jsonl` | Every table `core/schema.sql` defines, one JSON object per row, in the database's own order |

Model identity, per model run (`bundle.json` `models`, and `tables/model_runs.jsonl`):
- Local model: the model file's SHA-256, the seed, the generation settings and the prompt's
  version and SHA-256.
- Hosted model: vendor, the API model name, the effort, the prompt's version and SHA-256, and
  the line "Labels from a hosted model (Anthropic, `<model>`). They cannot be regenerated
  exactly; the recorded labels and rules are reproducible." Each request is in the audit log
  before it was sent (`cloud.sent`), and each answer after it came back (`cloud.received`: the
  model the API reported, its message id and request id, stop reason, token counts and the
  SHA-256 of the raw answer). `cloud.received` exists from this release on.
- Every model call, with the prompt exactly as filled in and the raw output exactly as returned,
  is in `tables/model_calls.jsonl`, whatever happened to it (ok, invalid output, quote failed,
  error). Each claim's audit-log entry names the calls stored while it ran and one SHA-256 over
  them (`model_calls`), from this release on.
- Every expert decision with its reason (`tables/evidence_reviews.jsonl`, `evidence.decide` in
  the log), every verdict confirmation and override (`verdict.confirm`, `verdict.override`), and
  the case's cloud choice with the attestation the expert agreed to (`set_cloud`).

## Verify

```
baker verify-bundle bundle.zip [--inputs <folder holding the original files>]
```

Offline; it never opens the case. It loads the tables into a database in memory and prints one
line per check (PASS, FAIL or NOTE), then exits 1 if anything failed:

1. **Files.** Each file matches its SHA-256 in `bundle.json`; nothing added or missing.
2. **Versions.** The rules and contracts that decided the verdicts are the ones in this copy of
   Baker. If not, it names the commit to verify with.
3. **Tables.** Each row has exactly the schema's columns; every reference resolves.
4. **Audit log.** The hash chain holds from the first entry; the last hash is the one in
   `bundle.json` (and printed in the report); the last entry is this export; every expert
   evidence decision in the log matches its stored review, and the other way round.
5. **Inputs.** Each import entry in the log names the hash stored for that source. With
   `--inputs`, the files there are hashed: a file of the same name with another hash fails.
6. **Labels.** Each evidence item's id still matches its content; its label is the model's
   answer as stored; its quote is found word for word in the record (when the audit's quote
   check is this copy's). Each claim's stored model calls match the digest its log entry
   recorded, and each hosted answer matches a `cloud.received` hash.
7. **Verdicts.** The rules, re-applied to the recorded labels, checks, stipulations and the
   expert decisions as they stood when each verdict was decided, give every verdict exactly
   (verdict, basis, reasons, coverage, citations). Confirmations and overrides in the log
   replay to the stored outcome.
8. **Report.** The report rendered from the tables is byte for byte the one in the bundle.

NOTE lines say what could not be checked: a labeler that stored no model answers (the eval's
stand-ins), cases audited before `cloud.received` or the claim digests existed, the government
document's import (not logged), original files not supplied.

## Limits

- The check is as strong as its anchor: the audit log's last hash, printed in the report. Anyone
  who rewrites every table, the whole log and `bundle.json` consistently makes a bundle that
  verifies on its own; comparing its last hash with a report produced earlier catches that.
  There is no signature and no outside timestamp.
- A hosted model's labels cannot be regenerated; what can be re-checked is the recorded labels
  and the rules applied to them.
- Regenerating a local model's labels needs the same model file, runtime and settings. Not tested
  across machines.
- Only the verdicts of the exported audit are re-derived; older runs' rows are carried as stored.
- Producing a bundle is no claim that Baker's results are correct or court-ready; it lets them
  be checked.

# Reproducibility bundle

A bundle lets the other side re-check everything Mabillon added to an examiner's findings without
our help: which files went in, which model labelled what, what the expert decided, and that the
versioned rules turn those recorded labels and decisions into exactly the verdicts reported.

Producing a bundle is the examiner's choice, made on counsel's advice. Mabillon never makes or
sends one on its own, and nothing is shared by default. A bundle holds case content (record
text, the prompts sent to the model and its answers, the expert's reasons), so handle it under
the case's protective order. By default it holds only what the verdicts rest on (Scope, below).

## Export

```
mabillon export-bundle --db <case>/case.db --out bundle.zip --by "expert:<your name>"
```

Run first without `--confirm-counsel-reviewed`: it prints the notice and exactly what the bundle
would hold (its row count per table, and each part it leaves out) and writes nothing. Once
counsel has reviewed that, run it again with `--confirm-counsel-reviewed`. Add
`--include <parts>` (comma separated, or `all` for the whole case) to both runs to widen it.

## Scope

By default a bundle holds what the latest audit's verdicts rest on: the claims; the
assumptions, check results and evidence items behind each verdict; the records they cite, with
the thread and accounts shown beside them; the model calls behind those items and their AI
reviews (prompt and answer); the expert's decisions and reasons on them; the verdicts;
stipulations, identity links, persons, devices, sources, coverage records, models, the
government document and exhibits; and the audit log. Each part below is left out unless you
include it:

| Part | What it adds |
|---|---|
| `dismissed` | Evidence items dismissed when their verdict was decided and still dismissed, with their reviews and the expert's `evidence.decide` entries for them |
| `irrelevant` | Evidence items the model labelled irrelevant, likewise |
| `prompts` | Every other model call (prompt and answer), and every `cloud.sent` entry (each holds the prompt sent) |
| `records` | The rest of the phone: records, threads, accounts, recipients, translations and locations no shipped row cites |
| `history` | Earlier audit runs' assumptions, checks, evidence, reviews and verdicts |
| `feedback` | The expert's flags about Mabillon (`flag.add`, `flag.withdraw`) |

No verdict rests on what is left out: the rules skip dismissed and irrelevant items. Mabillon runs
`verify-bundle` on every bundle before writing it and refuses one that fails, so a scope that
left out a row a verdict needs is never written.

What stays checkable. The audit log's digests are hashes over per-item hashes, so
`withheld.jsonl` lists each left-out evidence item and model call a digest names by its
SHA-256, and each left-out log entry by its time, actor, action and hashes; the digests and the
hash chain still check. What a left-out item or entry says cannot be checked from the bundle,
and a left-out entry's time, actor and action are as the export listed them, so
`verify-bundle` reports a scoped bundle as partly verified (exit 2) and says what it left out.
The full case, or a bundle exported with `--include all`, can show each one against its hash.

Still in a scoped bundle: the prompts behind the shipped items quote the nearby messages and
group members the model was shown, and the audit's manifests in the log name left-out items by
id (an evidence id names its record's id, not its text).

An encrypted case's bundle is encrypted too (AES-256-GCM under a key derived with scrypt from a
bundle passphrase you type twice; `core/bundle/sealed.py`); give counsel the passphrase by
another channel. Mabillon never writes an encrypted case's bundle in plain form. A plain case's
bundle is a plain zip.

It prints the bundle's SHA-256 (keep it: it names this exact file) and the audit log's last
hash. The export reads the case in one transaction, so the bundle is one snapshot (a decision
saved on the review screen meanwhile waits for it), and it never replaces a file already there,
even one another export wrote a moment before. Only after the file is fully written is the export logged in the case's audit log
(`bundle.export`, by you: the bundle's SHA-256, whether it is encrypted, your confirmation, what
it holds and the log head it carries). If that entry cannot be written, the file is removed; a
failed export leaves neither a bundle nor a success entry. The bundle holds the log as it stood
just before that entry. Only the latest completed audit can be exported, and not while a newer
audit is running or stopped part way; resume it (or re-run the verdicts) first. An audit
decided under other rules or contracts than this Mabillon's is refused too (this Mabillon could not
verify its bundle): re-run the verdicts or the full audit. If a stopped
audit rewrote the rows a verdict rests on, run the full audit again. A case whose audit log
does not verify is refused, as for a report.

## What is inside

| File | What it holds |
|---|---|
| `bundle.json` | Format and version; the Mabillon build (release, commit) and every version (pipeline, contracts, rules, report, quote check) that exported it and that ran the audit; each input's file name, SHA-256, importer and importer version; each model run's identity; the audit log's entry count and last hash; every other file's SHA-256 |
| `METHOD.md` | Plain-English method note: what Mabillon did, who labelled the evidence, how to check the bundle, its limits |
| `report.html` | The claims report, rendered from exactly the rows in `tables/` |
| `tables/<table>.jsonl` | Every table `core/schema.sql` defines, one JSON object per row the scope holds, in the database's own order |
| `withheld.jsonl` | What the scope left out that the log names: evidence items and model calls by SHA-256, log entries by time, actor, action and hashes (empty in a full bundle) |

Model identity, per model run (`bundle.json` `models`, and `tables/model_runs.jsonl`):
- Local model: the model file's SHA-256, the seed, the generation settings and the prompt's
  version and SHA-256.
- Hosted model: vendor, the API model name, the effort, the prompt's version and SHA-256, and
  the line "Labels from a hosted model (Anthropic, `<model>`). They cannot be regenerated
  exactly; the recorded labels and rules are reproducible." Each request is in the audit log
  before it was sent (`cloud.sent`), and each answer after it came back (`cloud.received`: the
  model the API reported, its message id and request id, stop reason, token counts and the
  SHA-256 of the raw answer). An answer Mabillon refused (another model, a refusal, a cut-off
  answer) is logged the same way, with the reason in `refused`. `cloud.received` exists from
  this release on.
- Every model call the scope holds (all of them with `prompts`), with the prompt exactly as
  filled in and the raw output exactly as returned, is in `tables/model_calls.jsonl`, whatever
  happened to it (ok, invalid output, quote failed, error). Each claim's audit-log entry names
  the calls stored while it ran and one SHA-256 over their per-call hashes (each over the whole
  stored row and its model run: `model_calls`), one SHA-256 over the rows its verdict rests on:
  assumptions, check results with the records they cite, and a hash per evidence item (the item
  with source, locator and rationale, its AI reviews, its record and their model runs:
  `rows_sha256`), and one over the claim itself (`claim_sha256`), from this release on.
- Every expert decision with its reason (`tables/evidence_reviews.jsonl`, `evidence.decide` in
  the log), every verdict confirmation and override (`verdict.confirm`, `verdict.override`), and
  the case's cloud choice with the attestation the expert agreed to (`set_cloud`).

## Verify

```
mabillon verify-bundle bundle.zip [--inputs <folder holding the original files>]
```

Offline; it never opens the case. An encrypted bundle asks for its passphrase. It loads the
tables into a database in memory and prints what it VERIFIED, what it did NOT VERIFY and why,
and what FAILED. It exits 0 only when every check ran and passed, 2 when nothing failed but
something could not be checked, and 1 when anything failed:

1. **Files.** Each file matches its SHA-256 in `bundle.json`; the files listed are exactly a
   bundle's (`METHOD.md`, `report.html`, `withheld.jsonl`, one file per table), nothing added
   or missing. An
   encrypted bundle whose header names other key-derivation settings than Mabillon writes fails
   before any key is derived; a bundle file over 4 GiB, or one that would unpack to more than
   4 GiB, fails before it is read or unpacked; a damaged member fails without a crash.
2. **Versions.** The rules and contracts that decided the verdicts are the ones in this copy of
   Mabillon. If not, it names the commit to verify with.
3. **Tables and scope.** Each row has exactly the schema's columns; every reference resolves. A
   full bundle leaves nothing out; a scoped one's `withheld.jsonl` is well formed and names
   nothing the bundle also holds (NOT VERIFIED says what it left out).
4. **Audit log.** The hash chain holds from the first entry and every payload reads, through
   the hashes of any entries the scope left out; the last hash is the one in `bundle.json` (and
   printed in the report); every expert evidence decision
   in the log matches its stored review, and the other way round. The case's own log then
   records the export (`bundle.export`) with this bundle's SHA-256. If this check fails,
   nothing after it runs.
5. **bundle.json.** Its run, model identities, inputs, contents, timeline settings (as the
   log's `timeline.settings` entries set them) and log head are recomputed from the tables and
   must match exactly; `METHOD.md` must be the note `bundle.json` gives.
6. **Inputs.** Each import entry in the log names the hash, file name, fidelity and coverage
   record stored for that source, and every logged import's source is there. With
   `--inputs`, the files there are hashed: a file of the same name with another hash fails, and
   a folder that does not exist fails.
7. **Run and rows.** The audit run's row (start time, versions, configuration with build,
   cloud decision and quote check, finish time) is the one its `pipeline.run` entry recorded. The
   assumptions, check results, evidence items and AI reviews behind each verdict, the records
   the items and checks cite (every column: body, sender, direction, times) with the accounts,
   thread and message shown beside them, and the model runs the items, reviews and claim name
   (model, file hash, prompt, settings, seed) are the rows its claim's log entry recorded a
   digest of; a left-out item counts by the hash `withheld.jsonl` gives.
8. **Labels.** Each evidence item's id still matches its content and it cites its record's own
   source and locator; its label and rationale are the model's answer as stored, exactly, or
   exactly as the pipeline rewrites one it records as complicates; its quote is found word for
   word in the record (when the audit's quote check is this copy's). Each AI review that names
   a stored reviewer answer says exactly what it decided and why. Each expert review is on the
   evidence item, by the expert and at the time its `evidence.decide` entry names. Each audited
   claim, audited or not, is the one the latest entry recording it logged (`pipeline.claim`,
   the proposer's `claims.proposed`, the expert's `claim.add`), or what the expert's logged
   changes since (`claim.status`, which records the text it replaced) made of it; no claim the
   log names is missing.
9. **Model calls.** Each claim's stored model calls (every column, and the model run each
   names) match the digest its log entry recorded, a left-out call by its listed hash; each
   hosted answer the bundle holds that a digest names matches a `cloud.received` hash.
10. **Stipulations and identity links.** Each stored stipulation is what the expert's latest
   logged action left, about the device and owner its id names, and none the log records is
   missing. Each identity link is what the logged actions left: proposed
   (`identity.propose`) and undecided, or decided (`identity.decide`, `identity.link`) with that
   account, person, status, tier, expert and time, and a confirmed link's person keeps the name
   the expert's logged action gave; a link the log still holds is not missing.
11. **Verdicts.** The rules, re-applied to the recorded labels, checks, stipulations and the
   expert decisions as they stood when each verdict was decided (a full audit's stipulations as
   of the log position it read them at), give every verdict exactly
   (verdict, basis, reasons, coverage, citations), at the decision time the log recorded.
   Confirmations and overrides in the log replay to the stored outcome.
12. **Report.** The report rendered from the tables is byte for byte the one in the bundle. A
   scoped bundle's report says what it left out, counts each claim's left-out items, and leaves
   out the sections that read the whole phone (timeline, restore, selection, holdings, other
   explanations) unless the bundle holds `records`. A bundle exported with another report
   version, or another bundle version (whose METHOD.md wording differs), fails naming the
   commit to verify it with: only that code writes the same bytes again. This version does not
   byte-compare such a report, so a change to it is caught only by verifying at that commit.
   Bundles exported before the rename to Mabillon (report 0.12.0, bundle 1.0.0) are verified
   that way.

NOT VERIFIED lines say what could not be checked: a labeler that stored no model answers (the eval's
stand-ins), cases audited before `cloud.received` or the run, claim and row digests existed,
hosted answers no digest names, model runs no audited row names (an earlier audit's), claims
an older Mabillon proposed and no audit recorded, the
government document's import (not logged), original files not supplied, and what a scoped
bundle left out.

## Limits

- The check is as strong as its anchor: the audit log's last hash, printed in the report. Every
  row a verdict rests on is bound to the log, so editing one changes that hash. Anyone who
  rewrites every table, the whole log and `bundle.json` consistently makes a bundle that
  verifies on its own; comparing its last hash with a report produced earlier, or the bundle's
  SHA-256 with the one printed at export, catches that. There is no signature and no outside
  timestamp. `bundle.json`'s export time and exporter are as written; the case's log records
  the export.
- A hosted model's labels cannot be regenerated; what can be re-checked is the recorded labels
  and the rules applied to them.
- Regenerating a local model's labels needs the same model file, runtime and settings. Not tested
  across machines.
- Only the verdicts of the exported audit are re-derived; older runs' rows, when included, are
  carried as stored.
- A scoped bundle cannot show what it left out: a left-out entry's time, actor and action are as
  the export listed them. A left-out item a verdict rested on fails the verdict check, since the
  stored verdict was decided with it; an entry relabelled in `withheld.jsonl` does not fail.
  Give the full bundle to whoever must see everything.
- An identity link or device owner the expert changes after the audit reaches the checks only
  on the next full audit (as on the screen); the report, in the bundle as elsewhere, shows the
  links as they stand at export. Run the full audit again before exporting after such a change.
- Not bound to the log: a proposed identity link's basis text, the nearby messages and group
  members shown with a record, and imported rows no verdict or check cites. Imported rows are not
  re-parsed from the original files; `--inputs` checks the files' hashes.
- Producing a bundle is no claim that Mabillon's results are correct or court-ready; it lets them
  be checked.

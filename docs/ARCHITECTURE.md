# Baker architecture

Baker is a local-first desktop app. A Python core does the work on the expert's computer; a
Tauri UI comes later, after the audit engine scores well on the eval set. A CLI comes first.
One step may go to the cloud, per case: stance labeling (see "Local by default, cloud by opt-in").

## Pipeline

```
1. INGEST     extraction report (UFDR, Cellebrite Excel/PDF/HTML, AXIOM XML/Excel, raw ZIP)
              + government document PDF -> SHA-256 every input, read-only
2. NORMALIZE  importers write canonical rows (core/schema.sql); every row has source_ref,
              times are UTC + original offset + raw source value
3. ENRICH     full-text search (FTS5, Russian lemmas), embeddings, translation (original kept),
              derived stats, gap detection
4. CLAIMS     govdoc -> paragraphs (page, para_no, char span) -> LLM proposes atomic claims
              -> expert edits the list
5. AUDIT      per claim: assumptions -> identity resolution -> retrieval (+/-20 msg context)
              -> LLM stance per (assumption, evidence) -> verbatim quote check (else discard)
              -> deterministic checks -> verdict from versioned rules (code, not LLM)
6. REVIEW     expert confirms or changes verdicts, identity links and claims -> hash-chained log
7. REPORT     cited packet: findings, limitations, source hashes, model runs, rule version, log
```

## Where the LLM is allowed

| Step | LLM role | What makes it safe |
|---|---|---|
| Claim extraction | Proposes claims | Expert edits the list; every claim keeps its page and paragraph |
| Assumptions | Fills claim-type templates | Templates are fixed per claim type; tier starts at inferred |
| Stance | Labels one evidence item against one assumption; the cloud model for a case the expert allowed, else the local model | Quote verified verbatim by code; label is input to rules, never a verdict; SUPPORTED needs the supporting label accepted by an expert (rules 0.2.0); a "contradicts" counts only once an expert accepts it ("Contradiction found, confirm to finalize", rules 0.3.0) |
| Review | Local model accepts or dismisses one verified supporting item | Separate human-owned prompt; a sorting aid for the expert that never makes a claim SUPPORTED under rules 0.2.0; tier becomes ai_reviewed, never confirmed; a human decision overrides it; cloud models only in eval/ as benchmarks |
| Translation | ru -> en | Original text stays the citable text |

The LLM never writes a verdict, an identity merge or a confirmation.

## Module boundaries

Each module depends on `core/contracts.py` and `core/schema.sql` only, never on another
module's internals. Modules talk through the database and the contract types.

```
core/
  contracts.py        frozen: data models + function signatures (human-owned)
  schema.sql          frozen: canonical tables (human-owned)
  db.py               open a case database (plain or encrypted), apply schema
  encryption.py       case keys, encrypted copies of inputs, the keyring of unlocked cases
  ingest/             one file per input format; implements EvidenceImporter or GovDocIngester
                      ufdr_check.py: offline check of a UFDR import against its report.xml
  enrich/             search index, embeddings, translation, gap detection
  claims/             ClaimExtractor
  audit/
    assumptions.py    AssumptionBuilder
    retrieval.py      Retriever
    stance.py         StanceLabeler (wires the human-owned prompt to the local model)
    readable.py       names a model reads ("Daniel Petrov (the user of item1)"), never ids
    context.py        surrounding messages; for stance, sender lines and the chat's members
    review.py         EvidenceReviewer (second local pass; ai_accepted or dismissed)
    quotes.py         verify_quote
    checks/           DeterministicCheck implementations
    rules.py          decide_verdict (human-owned)
    prompts/          human-owned prompts
  restore/            Context Restore: find pasted exhibit quotes in the extraction (code only)
  selection/          selection audit: each message the document quotes, an exhibit quotes or the
                      examiner tagged, in its exchange with the messages around it that were not
                      picked (code only, derived each time, never changes a verdict);
                      paired.py: a curated report against a larger source of the same phone,
                      what the report left out near each claim (fails closed, never a verdict)
  identity/           propose account -> person links from names in the data (code only);
                      the expert confirms or rejects each one on the Identities page
  review/             expert actions + audit log
  report/             ReportRenderer; restore.py, selection.py, letter.py (full-extraction request),
                      hypotheses.py (other explanations, shared with the claim page)
  review/status.py    what each claim needs from the expert (shared by screen and report)
  review/flags.py     optional expert flags (wrong label, missed record, verdict disagreement):
                      audit-log entries only, never touch verdicts; redacted summary and error log
  review/redecide.py  re-run the verdict rules after expert review, no model
  llm/                runtime.py: the local GGUF runtime; cloud.py: the cloud stance model
                      (the only network call in core/), on the expert's own Anthropic key
  casework/           case folders and imports, background audit and claim-proposal jobs,
                      the model check, keeping the computer awake (used by the screen)
                      protect.py: encrypting an existing case, passphrase changes
                      cloud.py: the per-case cloud choice (attestation, CSAM flag, key)
  timeline/           Timeline check (stated times vs record times) and quiet stretches;
                      derived by code on demand, never stored, never touches verdicts
  hypotheses/         other explanations per claim, with the records that fit each (someone
                      else used the account or phone, another clock, the day boundary, another
                      app, a whole app quiet, a curated report, the same words elsewhere);
                      code only, derived on demand, never stored, never touches verdicts
cli/                  `baker import`, `baker claims`, `baker audit`, `baker report`, `baker serve`
ui/                   the expert's screen on 127.0.0.1 (stdlib server, no scripts): start a case,
                      run the audit in the background, review
eval/
  synthetic/          deterministic synthetic case generator
  gold/case01/        mock affidavit + gold verdicts (human-owned)
  run_eval.py         scores predictions against gold; the merge gate
tests/
```

## Key decisions

- **Case database.** One SQLite file per case. Nothing is shared between cases.
- **Encryption at rest.** A case can be encrypted with the expert's passphrase: the database
  with SQLCipher, each copied input with AES-256-GCM in chunks, one random key per case wrapped
  in `case.key` (core/encryption.py, docs/encryption.md). Plain cases open unchanged; only the
  expert's explicit "Encrypt this case" converts one (core/casework/protect.py). Database
  errors are caught through `core.db.Error`/`OperationalError`/`IntegrityError`, because
  SQLCipher raises its own classes.
- **Stable ids.** Ids are strings built deterministically from source and locator
  (for example `msg:<source_id>:<locator>`), so re-importing gives the same ids and gold labels
  can point at specific messages.
- **source_ref.** `source_id` plus a `locator` string whose meaning depends on the source kind:
  an XML path for UFDR, `sheet!row` for Excel, `page:para` for PDF, `Artifact[n]/Hit[m]` for an
  AXIOM XML report.
- **Fidelity.** Every source records whether it is a full extraction or a curated report.
  Absence checks and the selection audit read this; a curated report can never support an absence claim.
- **Two-stage evidence.** `StanceLabel` is raw, untrusted model output. It becomes an
  `EvidenceItem` only after `verify_quote` passes. Unverified labels are logged and dropped.
- **Reproducibility.** Every model call belongs to a `model_runs` row with the model file hash,
  prompt version, parameters and seed. Outputs are stored, not regenerated.
- **Audit log.** Append-only; each entry hashes the previous entry's hash plus its own payload.

## Local by default, cloud by opt-in

Baker runs entirely on the expert's computer unless the expert opts a case in to cloud AI.

Stance labels come from Claude (Opus 5.5, medium effort by default) for a case where all hold:
the expert attested at case setup that its protective order allows cloud AI; the case is not
marked as possibly containing CSAM; the expert's own Anthropic key is set up: `$BAKER_ANTHROPIC_API_KEY`; or, in an encrypted case,
the key saved in that case (`case.cloud-key`, AES-256-GCM under the case key, so it is unreadable
while the case is locked); or `~/.baker/cloud.json` (owner-only), in that order; and the model
passed the signed stance test at its configured effort with the cloud stance prompt (`PROBE_PASSED` in
`core/llm/cloud.py`, empty until one does; an entry needs a recorded pass on the signed
set and on new held-out items, and Arsh's sign-off). Only a cloud model reads that prompt,
`core/audit/prompts/stance_cloud.md` (v1.2); the local model keeps `stance.md` (v1.1). Otherwise
the local model labels the case, exactly as before. The choice is the latest `set_cloud` entry in the case's
audit log (inside the case database, so an encrypted case keeps it encrypted).

Only the filled-in stance prompt goes out (assumption, record, nearby messages, claim, and a
group chat's member list). The
answer is checked like the local model's: strict JSON, quote verified verbatim by code. The
verdict rules, the signed prompt and the expert's review are unchanged.

No mixed labels (`core/audit/_local_model.py` CloudPort). In a case that opted in, every
stance label comes from the cloud model. No network, a rejected key or the API down (after a
120-second timeout and two retries) pauses the audit. The expert then resumes to retry the
cloud model, or turns cloud AI off for the case and runs it again, which labels the whole case
locally (stored outputs are keyed by model, so no cloud label is reused). A refusal or a
cut-off answer drops that one label, as a local model's bad answer is. The report's "Stance
labels" row and each item's "Labeled by" line name the model. Assumption filling and the
optional AI reviewer stay local.

What was sent (`SentLog`). Before each request, Baker writes it to the case's hash-chained
audit log (action `cloud.sent`): the time, the endpoint, the attempt number and the request body
exactly as sent. The key is in a header and never logged. Baker retries a retryable failure (no
connection, a timeout, 408, 409, 429, 5xx) itself, up to twice, logging each send; the SDK's
own retries are off. If the entry cannot be written, the request is not sent and the audit
pauses; if the client cannot be built, nothing is logged. An answer reused from stored outputs
sends nothing; a stored cloud answer that failed its quote or format check is not reused.

Which model labeled an item. Evidence ids come from content (assumption, record, stance,
quote), so a case that switches between cloud and local can produce the same item twice. The
row then names the model of the latest run that produced it, with that run's rationale; the
expert's reviews of that content carry over, as on any re-run.

Retention at Anthropic. Baker sends to the Claude API (`api.anthropic.com`) under the expert's
own key, so Anthropic's terms for that account apply. Read them rather than our summary:
[commercial data retention policy](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data),
[API and data retention, including zero data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention),
and the [Commercial Terms](https://www.anthropic.com/legal/commercial-terms) ("Anthropic may not
train models on Customer Content from Services"). Two points from those pages matter here.
Content flagged by Anthropic's trust and safety systems may be kept for up to 2 years even
under zero data retention. With structured outputs, only the JSON schema is cached; Baker's
schema is fixed and holds no case data. Zero data retention is arranged with Anthropic per
organization; Baker cannot turn it on.

## Not in scope
Acquisition or extraction, deleted-file recovery, broad artifact coverage, automatic
leader/follower labels, AI-written expert opinions, cloud processing beyond stance labeling,
audio and video.

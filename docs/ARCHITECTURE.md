# Baker architecture

Baker is a local-first desktop app. A Python core does all the work offline; a Tauri UI comes
later, after the audit engine scores well on the eval set. A CLI comes first.

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
| Stance | Labels one evidence item against one assumption | Quote verified verbatim by code; label is input to rules, never a verdict; SUPPORTED needs the supporting label accepted by an expert (rules 0.2.0); an unreviewed "contradicts" cannot overrule a check that passed, it only complicates (rules 0.2.1) |
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
  enrich/             search index, embeddings, translation, gap detection
  claims/             ClaimExtractor
  audit/
    assumptions.py    AssumptionBuilder
    retrieval.py      Retriever
    stance.py         StanceLabeler (wires the human-owned prompt to the local model)
    review.py         EvidenceReviewer (second local pass; ai_accepted or dismissed)
    quotes.py         verify_quote
    checks/           DeterministicCheck implementations
    rules.py          decide_verdict (human-owned)
    prompts/          human-owned prompts
  restore/            Context Restore: find pasted exhibit quotes in the extraction (code only)
  selection/          selection audit: each message the document quotes, an exhibit quotes or the
                      examiner tagged, in its exchange with the messages around it that were not
                      picked (code only, derived each time, never changes a verdict)
  identity/           propose account -> person links from names in the data (code only);
                      the expert confirms or rejects each one on the Identities page
  review/             expert actions + audit log
  report/             ReportRenderer; restore.py, selection.py, letter.py (full-extraction request)
  review/status.py    what each claim needs from the expert (shared by screen and report)
  review/redecide.py  re-run the verdict rules after expert review, no model
  casework/           case folders and imports, background audit and claim-proposal jobs,
                      the model check, keeping the computer awake (used by the screen)
                      protect.py: encrypting an existing case, passphrase changes
  timeline/           Timeline check (stated times vs record times) and quiet stretches;
                      derived by code on demand, never stored, never touches verdicts
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

## Not in scope
Acquisition or extraction, deleted-file recovery, broad artifact coverage, automatic
leader/follower labels, AI-written expert opinions, cloud processing, audio and video.

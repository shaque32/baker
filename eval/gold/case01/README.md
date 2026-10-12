# Eval case format: case01

Everything here is synthetic. Gold verdicts are human-owned: an agent may generate the case
data and draft the affidavit, but only Arsh writes and signs off `gold.jsonl`.

| File | Owner | Contents |
|---|---|---|
| `case.json` | agent drafts, human reviews | Case metadata: seed, generator version, devices, source files, planted traps |
| `affidavit.md` | agent drafts, human reviews | The mock government document, numbered paragraphs |
| `gold.jsonl` | **human only** | One `GoldClaim` per line (see `core/contracts.py`) |
| `assumptions.jsonl` | **human only** (signed by Arsh, 2026-10-08) | The assumption sheet `make eval` fills claims from: one template entry per line. Drafted in `eval/probe_draft/case01_assumptions.py`; identical to its build except `labeled_by` |
| `sources/` | generator | Synthetic extraction reports to import (Cellebrite-style Excel/PDF, later UFDR) |

The eval goes through an importer: the generator emits report files in `sources/`, and the
pipeline must import them like real discovery. It never writes straight into the database.

## gold.jsonl line format

```json
{"claim_id": "C01", "page": 1, "para_no": 3,
 "text": "<the claim as worded in the affidavit>",
 "claim_type": "<communication|identity|timing|content_meaning|count|absence|role|event>",
 "cross_device": false,
 "gold_verdict": "<supported|contradicted|unproven>",
 "core_assumptions": ["<assumption the claim depends on>"],
 "key_evidence": ["msg:<source_id>:<locator>"],
 "trap": "<trap name from case.json, or null>",
 "rationale": "<why this verdict, in one or two sentences>",
 "labeled_by": "<name>", "labeled_at": "<ISO 8601 UTC>"}
```

## Predictions

The pipeline writes `eval/out/case01/predictions.jsonl`, one `Prediction` per line.
`make eval` scores verdict accuracy and false-supported rate against `gold.jsonl`.
A claim with no prediction counts as wrong.

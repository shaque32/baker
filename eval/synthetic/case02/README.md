# case02: hidden eval case

**Builder threads must not read `eval/synthetic/case02*`, `tests/test_synthetic_case02.py` or
`eval/out/case02/`.** case02 checks whether the engine generalizes beyond case01, so nobody
building the engine may see its story, traps or answers.

Everything here is synthetic: two fictional phones, English and Spanish, Feb 16 to Mar 31 2026,
in the same Cellebrite-style report layout as case01. The existing Excel importer reads it
unchanged.

## Regenerate

```
python -m eval.synthetic.case02_generate --db eval/out/case02/case02.db
```

The generator is seeded and byte-deterministic. `case.json` pins the SHA-256 of `item1.xlsx`
and `item2.xlsx` (rebuilt, not committed), and `tests/test_synthetic_case02.py` regenerates the
case and compares it with the committed files. `--db` also writes the expected database and the
affidavit PDF (`affidavit.pdf`) to `eval/out/case02/`, which is not committed.

| File | What it is |
|---|---|
| `case.json` | Devices, source hashes, planted traps, ground-truth people; `"hidden": true` |
| `affidavit_draft.md` | Mock affidavit excerpt; printed paragraph numbers start at 21 |
| `draft_gold.jsonl` | DRAFT key in `GoldClaim` format, `labeled_by` set to a DRAFT marker |
| `ANSWER_KEY_DRAFT.md` | The same key with reasoning and cited rows, for line-by-line review |
| `case02_assumptions.jsonl` | DRAFT assumption sheet, built by `eval/synthetic/case02_assumptions.py` |
| `CASE02_ASSUMPTIONS_REVIEW.md` | The same sheet for line-by-line review, with expected check results and gaps |

## Status

- `make eval` (and so `make check`) runs case02 model-free with the simulated expert and
  scores it **report-only** (`make eval-case02`). It never gates a merge; it gates paying
  pilots. The printed summary is aggregate only, so builders running `make check` see no claim
  or record ids; details are in `eval/out/case02/model_free/run.json`, which builders do not read.
- **Signed by Arsh on 2026-10-12**, with draft labeling rules 5 to 8. The signed key and
  assumption sheet are in `eval/gold/case02/` and `make eval` uses them; the drafts here stay as
  the build output the signed copies are tested against. An unsigned key can never gate.

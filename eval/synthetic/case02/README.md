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

## Status

- Results on case02 are reported with every eval run but **do not gate the alpha**. They gate
  paying pilots.
- **Arsh signs the gold.** The draft key is the generating agent's proposal; approved lines are
  copied into `eval/gold/case02/` by a human.

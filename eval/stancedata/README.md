# Stance data for Baker's own model

SYNTHETIC. Arsh signed labeling guide v0.3 on 2026-10-14; generated labels stay DRAFT until he
signs the label samples.

Baker's stance step labels how one phone record bears on one assumption. Today a prompted
Qwen3-14B does it at about 23 seconds per record on a 24 GB Mac. The plan is a small model
trained for this one job (a ~300M multilingual classifier with a span head first, a Qwen3-4B
LoRA second), adopted only if it clears the bars in `GO_BAR.md`. This folder holds what phase 1
needs before any training: the rules, the item format, the overlap check, the scorer and the
go bar. The two generators live next door:

| Path | What it is |
|---|---|
| `LABELING_GUIDE.md` | The rulebook: the four answers, the ground rules, 66 families with a fixed answer each (38 plain, 28 in Baker's own wording). v0.3, signed by Arsh on 2026-10-14; the signed copy is in `eval/gold/stancedata/`. |
| `families.py` | The same families as code. A generator picks a family; the label comes from it. |
| `model.py`, `chat.py` | The item format (a probe item with a wider id) and the shared mechanics: accounts, local times, item assembly. No wording. |
| `bakerform.py`, `names.py` | Items in Baker's own wording: the product's assumption templates, sender lines and call text, rendered with the names a case gives (`core/audit/readable.py`), so the model reads what Baker will show it. |
| `../train/` | Training generator: 12,000 plain items, with sibling items that share a record and differ in the assumption, then 7,250 items in Baker's own wording (`--n-baker`). |
| `../heldout/` | Held-out generator, written separately with its own names, situations and wording: a 1,846-item test split (ids H...; 1,150 plain, 696 in Baker's wording) and a 923-item dev split (ids D...; 575 plain, 348 in Baker's wording). |
| `contamination.py` | Overlap check: generated text against the probe set, case01 and case02, and training against held-out. The only code here that reads that data. |
| `score.py` | Scores any model's predictions with the exact rules of `eval/probe/run_probe.py`. |
| `GO_BAR.md`, `gobar.py` | The adoption rule, fixed before training. |
| `review_sheet.py` | The random sample Arsh checks: 200 training items and 100 held-out items. |
| `TEST_LOG.md` | Every scoring of the held-out test split. |
| `../stancemodel/` | Arm 1, the small classifier: training on CPU, export, labeling, policy tuning on dev, and the case01 speed test. |

## Build and check

    make stancedata

writes `eval/out/stancedata/` (training items, both held-out splits, manifests) and runs the
overlap check, which fails the build on any overlap. Scoring the prompted 14B on the held-out
dev split, on a Mac with the model installed, uses the existing runner, which shows an item in
Baker's own wording as Baker shows a case's records: senders without Baker's internal ids, a chat
record's members line first, and the claim once the stance prompt has a `{claim}` slot (v1.1):

    python -m eval.probe.run_probe --models eval/probe/models.local.json --stance-only \
        --repeat 1 --probe-set eval/out/stancedata/heldout_dev.jsonl

The sample Arsh checks is rebuilt from the generated files, so it always matches them:

    python -m eval.stancedata.review_sheet --train eval/out/stancedata/train.jsonl \
        --heldout eval/out/stancedata/heldout_test.jsonl --out eval/out/stancedata/review_sheet.md

Before that sample, a blind second reader (one who never saw the answers) labels 100 items of
each set from the guide alone; disagreements are fixed in the generator or the guide first.

## Why two generators

A model trained on one generator learns that generator: its names, its phrasing, its trap
shapes. If the test set came from the same code, a perfect score could mean memorization. So the
held-out generator was written separately, from this guide only, with disjoint name pools
(first letters A to M and А to Л for training, N to Z and М to Я for held-out), different area
codes, different situations and different slang. It still shares this guide's view of the task,
so it tests generalization across wording, not across authors; the real-world test is still
expert use.

## Data safety

All text is invented. Phone numbers are in the 555-0100 to 555-0199 block reserved for fiction.
No generator reads the probe set, case01 or case02; tests scan their source to keep it that way.

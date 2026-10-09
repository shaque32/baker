# Stance data for Baker's own model

SYNTHETIC. Labels are DRAFT until Arsh signs the labeling guide and the label samples.

Baker's stance step labels how one phone record bears on one assumption. Today a prompted
Qwen3-14B does it at about 23 seconds per record on a 24 GB Mac. The plan is a small model
trained for this one job (a ~300M multilingual classifier with a span head first, a Qwen3-4B
LoRA second), adopted only if it clears the bars in `GO_BAR.md`. This folder holds what phase 1
needs before any training: the rules, the item format, the overlap check, the scorer and the
go bar. The two generators live next door:

| Path | What it is |
|---|---|
| `LABELING_GUIDE.md` | The rulebook: the four answers, ten ground rules, 37 families with a fixed answer each. For Arsh to sign. |
| `families.py` | The same families as code. A generator picks a family; the label comes from it. |
| `model.py`, `chat.py` | The item format (a probe item with a wider id) and the shared mechanics: accounts, local times, item assembly. No wording. |
| `../train/` | Training generator: 12,000 items by default, with sibling items that share a record and differ in the assumption. |
| `../heldout/` | Held-out generator, written separately with its own names, situations and wording: a 1,020-item test split (ids H...) and a 510-item dev split (ids D...). |
| `contamination.py` | Overlap check: generated text against the probe set, case01 and case02, and training against held-out. The only code here that reads that data. |
| `score.py` | Scores any model's predictions with the exact rules of `eval/probe/run_probe.py`. |
| `GO_BAR.md`, `gobar.py` | The adoption rule, fixed before training. |
| `review_sheet.py` | The random sample Arsh checks: 200 training items and 100 held-out items. |
| `TEST_LOG.md` | Every scoring of the held-out test split. |

## Build and check

    make stancedata

writes `eval/out/stancedata/` (training items, both held-out splits, manifests) and runs the
overlap check, which fails the build on any overlap. Scoring the prompted 14B on the held-out
dev split, on a Mac with the model installed, uses the existing runner unchanged:

    python -m eval.probe.run_probe --models eval/probe/models.local.json --stance-only \
        --repeat 1 --probe-set eval/out/stancedata/heldout_dev.jsonl

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

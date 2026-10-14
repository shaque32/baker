# Baker's own stance model, arm 1: the small classifier

SYNTHETIC data only. Eval-only code: nothing in `core/` imports it. The product still labels
stance with the prompted Qwen3-14B until this model clears every bar in
`eval/stancedata/GO_BAR.md`.

## What it is

`microsoft/mdeberta-v3-base` (MIT, revision `a0484667b22365f84929a935b5e50a51f71f159d`), a
multilingual encoder of about 280M weights, fine-tuned on the 12,000 generated training items
(`eval/train`, SHA-256 `ce4f17d8...a320332`) to read one assumption and one record in its chat
and give:

- a stance: supports, contradicts, complicates or irrelevant (a 4-way head on the first token);
- a quote: a span head marks the quote's first and last token inside the record's text, so the
  quote is a piece of the record by construction. It is widened to whole words and kept only if
  `core.audit.quotes.verify_quote` passes; otherwise the whole record text is the quote if that
  passes, and if nothing passes the quote is empty and the label is dropped, as the product
  drops any unverified quote.

The word embeddings stay frozen (a third of the weights; words the training data never shows
keep the base model's meaning). Weights are stored as float16, like the base checkpoint, and
computed in float32. It writes no rationale; an eval adapter that needs one uses a fixed text.

What the model reads (`features.py`): the assumption, then every line of the excerpt in time
order, the record marked `RECORD:`. A line is `<local time> | <sender> | <text>`, with the time
written as assumptions write it ("10:46 p.m. on February 15, 2025 (Saturday, EST)") and +1
numbers as "+1 718-555-0122". The text is untouched.

Inside Baker the model reads what Baker sends its stance step (`time_case01.case_item`). The
assumption is Baker's own template text, ids included. Lines are Baker's context lines, and a
call or contact reads as Baker's record text. The record mark names the phone
(`RECORD (item1):`, its source id). A sender is `<app> <id>`, then the name the source showed, then
`(owner)` for the phone's own account, then `[person ids]`. Person ids come only from
expert-confirmed device-owner stipulations and identity links, matched as Baker's checks match
them (`core/audit/checks/_common.person_party`). For the meaning, role and event assumptions, whose
text points at "the claim", the claim's own text comes first (`CLAIM: <text> || <assumption>`),
on the assumption side, so a quote is never cut from it. A chat record's excerpt opens with the
chat's members line ("Members seen in this chat's records: A; B"), which is never cut. Training
items written in this form must
match `case_item` exactly, so a change to it, or to its window of 3 messages, is agreed with
the data generators first.

How a label is chosen (`policy.py`): the four probabilities go through a policy tuned on the dev
split only. "supports" needs enough probability and little "contradicts" probability;
"contradicts" needs enough probability; a label that falls short becomes "complicates", which
keeps a claim from going SUPPORTED without making it CONTRADICTED.

## Files

| Path | What it does |
|---|---|
| `features.py` | Renders an item as an (assumption, excerpt) text pair. Pure Python. |
| `encode.py` | Token ids, which tokens are the record, the gold quote as a token span, and a token span back to a verified quote. |
| `model.py` | The encoder with both heads; export and load of a model folder (local files only). |
| `train.py` | CPU training in chunks that stop at a time budget and resume at the exact batch. |
| `export.py` | Writes a checkpoint as a self-contained model folder with its SHA-256. |
| `predict.py` | Labels items in `eval.stancedata.score` format, with the probabilities. |
| `tune.py` | Picks the decision policy on the dev split, by a rule fixed before any dev result. |
| `time_case01.py` | The speed bar: seconds per stance decision on case01, through the product pipeline. |
| `hidden_case_bar.py` | Go-bar condition 5: the model as Baker's stance labeler on the hidden case02, with the simulated expert; aggregate numbers only, once per model. |

## Run it

One-time setup (Python 3.12+). On Linux, install torch's CPU wheel first so pip does not pull
the CUDA build:

    python -m pip install -e ".[dev,train]"
    python -c "from huggingface_hub import snapshot_download; snapshot_download(
        'microsoft/mdeberta-v3-base', revision='a0484667b22365f84929a935b5e50a51f71f159d',
        allow_patterns=['config.json', 'pytorch_model.bin', 'spm.model', 'tokenizer_config.json'],
        local_dir='models/mdeberta-v3-base')"

Data, then the SHA-256 check against the values in the PR that trained the model:

    make stancedata
    sha256sum eval/out/stancedata/train.jsonl eval/out/stancedata/heldout_dev.jsonl

Train (about 11 s per batch of 16 on 4 CPU cores; 3 epochs is about 7 hours). Run the same
command again after it stops: exit 75 means it paused at the time budget, 0 means done.

    python -m eval.stancemodel.train --base models/mdeberta-v3-base \
        --train eval/out/stancedata/train.jsonl --train-sha256 <sha256> \
        --dev eval/out/stancedata/heldout_dev.jsonl --run eval/out/stancemodel/run1

Export, label the dev split, tune the policy on it, export again with the policy:

    python -m eval.stancemodel.export --base models/mdeberta-v3-base \
        --run eval/out/stancemodel/run1 --out eval/out/stancemodel/run1/model
    python -m eval.stancemodel.predict --model eval/out/stancemodel/run1/model \
        --items eval/out/stancedata/heldout_dev.jsonl --out eval/out/stancemodel/run1/dev.jsonl
    python -m eval.stancemodel.tune --items eval/out/stancedata/heldout_dev.jsonl \
        --predictions eval/out/stancemodel/run1/dev.jsonl --out eval/out/stancemodel/run1/policy.json
    python -m eval.stancedata.score --items eval/out/stancedata/heldout_dev.jsonl \
        --predictions eval/out/stancemodel/run1/dev.jsonl

The speed bar, on Arsh's 24 GB Mac, with the exported folder:

    python -m eval.stancemodel.time_case01 --model <model folder>

## Rules this follows (GO_BAR.md)

- Train on the training split only. Tune (checkpoint, policy) on the dev split (ids D...) only.
- The held-out test split (ids H...) is scored at most three times in all, each logged in
  `eval/stancedata/TEST_LOG.md`, and only after Arsh's review sheet passes. Adopt only if the
  go bar passes on the first test scoring of the candidate.
- The signed probe set is scored once per finished candidate, never used to tune.
- Labels change only when Arsh decides an answer was wrong, never because a model got it wrong.
- No model weights in git. A model is named by its file's SHA-256.

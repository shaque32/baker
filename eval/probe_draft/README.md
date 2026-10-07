# Probe set draft

SYNTHETIC. DRAFT until Arsh signs each item.

The probe set judges candidate local models one decision at a time. Each item is one assumption,
one message shown with its surrounding messages, and a known right answer: the stance the labeler
should give and whether the AI reviewer should accept or dismiss it as support. About a third of
the items are overreach traps: messages that look like support but are not (a handle assumed to
be a person, slang, an unresolved "it", sarcasm, a later correction, the wrong sender or local
date, quoted speech, a plan instead of an event, a shared account, text that tries to steer the
model, and more).

- `items.py`: the items, written by hand (`ProbeItem`, see `model.py`).
- `probe_draft.jsonl`: one item per line, built from `items.py`.
- `PROBE_REVIEW.md`: the signing sheet for Arsh.

Rebuild after any change to `items.py` (a test checks both outputs match the build byte for byte):

    python -m eval.probe_draft.build

## Signing

Arsh ticks agree or change on each item in `PROBE_REVIEW.md`. Signed items are copied into
`eval/gold/` by the frozen-files thread, with `labeled_by` set to Arsh. Unsigned items stay drafts.
Agreement with a cloud model does not make an item right.

## Use and scoring

Thread 2 (local model runtime) loads `probe_draft.jsonl` with
`eval.probe_draft.model.ProbeItem.model_validate_json` and shows the model `item.lines()`.
Scoring, as in the `model.py` docstring:

- stance: the labeler's label for (assumption, target in context) against `gold_stance`;
- review: the reviewer sees `proposed_quote` as a SUPPORTS label and must answer `gold_review`
  (accept only when `gold_stance` is supports);
- pass bars: precision of "supports" >= 95%, recall >= 90%, and zero reviewer accepts on
  overreach items.

## Rule

Items are never tuned to make a model pass. If a model fails an item, the model fails it. An
item changes only when Arsh decides its gold answer was wrong.

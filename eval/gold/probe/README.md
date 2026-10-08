# Signed probe set

SYNTHETIC. HUMAN-OWNED (Arsh). Agents: do not modify.

`probe.jsonl` holds probe items P001 to P088, signed by Arsh on 2026-10-07
(`labeled_by: "Arsh, 2026-10-07"`). Each line is copied byte for byte from
`eval/probe_draft/probe_draft.jsonl`; a test checks that the two still match and that no
unsigned item is here.

- P089 to P097 are drafts and stay in `eval/probe_draft/` until Arsh signs them.
- `disputed` is set on 10 items where a reasonable expert could pick another label. Model
  tests score signed, undisputed items for the pass bars and report disputed items separately.
- Items change only when Arsh decides a gold answer was wrong, never to make a model pass.
  Change `eval/probe_draft/items.py`, rebuild the draft, then copy the signed lines here.

What the set is for, the item format and the scoring rules are in `eval/probe_draft/README.md`
and `eval/probe_draft/model.py`. Load items with
`eval.probe_draft.model.ProbeItem.model_validate_json`.

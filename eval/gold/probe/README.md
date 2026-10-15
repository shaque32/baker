# Signed probe set

SYNTHETIC. HUMAN-OWNED (Arsh). Agents: do not modify.

`probe.jsonl` holds probe items P001 to P105. Arsh signed P001 to P088 on 2026-10-07
(`labeled_by: "Arsh, 2026-10-07"`). On 2026-10-14 ("approved" in the "Custom model for Baker"
thread) he relabeled P038 to P044 and P071 from contradicts to complicates under stance guide
v0.3's strict contradicts (`labeled_by: "Arsh, 2026-10-14"`; each item's rationale gives the
new reason). On 2026-10-15 he relabeled P049 and P066 to P069 the same way (guide rules 12 and 23)
and signed P089 to P105 (`labeled_by: "Arsh, 2026-10-15"`), so 11 of the 95 signed, undisputed
items are gold contradicts. Each line is copied byte for byte from
`eval/probe_draft/probe_draft.jsonl`; a test checks that the two still match and that no
unsigned item is here.

- `disputed` is set on 10 items where a reasonable expert could pick another label. Model
  tests score signed, undisputed items for the pass bars and report disputed items separately.
- Items change only when Arsh decides a gold answer was wrong, never to make a model pass.
  Change `eval/probe_draft/items.py`, rebuild the draft, then copy the signed lines here.

What the set is for, the item format and the scoring rules are in `eval/probe_draft/README.md`
and `eval/probe_draft/model.py`. Load items with
`eval.probe_draft.model.ProbeItem.model_validate_json`.

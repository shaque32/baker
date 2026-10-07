# Red team: hunting false "supported"

Everything here is synthetic. The point is to break Baker before an expert does: one wrong
"supported" in front of an expert destroys trust.

| File | What it attacks | Test |
|---|---|---|
| `scenarios.py` | The verdict rules. 24 red-team cases that must never be SUPPORTED, plus 3 controls that must be | `tests/adversarial/test_rules_red_team.py` |
| `quote_attacks.py` | The verbatim quote check. Lookalike letters, splices, paraphrases, translations, whitespace tricks | `tests/adversarial/test_quote_red_team.py` |
| `hostile_model.py` | The whole pipeline. A labeler that calls everything support and a reviewer that accepts everything | `tests/adversarial/test_hostile_model.py` |
| `structural_blocks.py` | Which case01 claims the structure protects under the hostile model, and which only the reviewer protects | same |

The rules and quote tests skip until `core/audit/rules.py` and `core/audit/quotes.py` exist,
then run on every `make check` with no change here.

## How to read a failure

- `test_red_team_never_supported[Rxx]`: the rules said SUPPORTED where they must not. Fix the
  rules, never the scenario.
- `test_red_team_pending_decision[Rxx]`: the scenario rests on a rule Arsh has not signed
  (R09 absence, R18 and R19 identity). A failure is a question for him.
- `test_controls_supported[Kxx]`: the rules are too strict to support a clean claim, or
  their reasons do not say when SUPPORTED rests on AI review alone.
- `test_verdict_does_not_depend_on_evidence_order`: a first-match bug.
- `test_quote_attack[Qxx]`: a near-miss quote passed, or an exact one failed.

## What the hostile model shows

Under the hostile pair, every case01 claim the structure guards (`STRUCTURAL`) must stay not
SUPPORTED. For the claims guarded only by the reviewer (`MODEL_ONLY`: C06, C08, C13, C15 and
C20, 5 of the 12 gold non-supported claims), the hostile run will show a false "supported".
That is expected: it measures how much rides on the local reviewer, which the probe set's
overreach items test item by item. The pipeline thread wires the hostile mode into
`eval/run_pipeline.py`.

## Rules for changing this folder

Add scenarios freely. Never delete or weaken one to make a run pass; if a scenario is wrong,
say why in the PR and get Arsh's sign-off.

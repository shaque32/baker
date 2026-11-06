# Mabillon review guidance

Mabillon audits government claims about phone evidence for criminal defense experts. Each claim
ends up supported, contradicted or unproven, with cited evidence. A wrong "supported" is the
worst failure this code can have, so review for that first.

Read `CLAUDE.md` before reviewing. It is the rulebook; `config.json` only restates the rules that
are easiest to check from a diff.

## What to comment on, in this order

1. Anything that could make the tool show something as evidence when it is not, or make a claim
   SUPPORTED without an expert's acceptance.
2. A break of the quote, provenance, source_ref or confirmation rules.
3. A signal pointing at the wrong person: identity links merged or shown as confirmed without an
   expert.
4. Network or privacy: a new outbound call, more data sent to the cloud model, a request not
   logged first, or cloud used for a case that did not opt in.
5. Concrete bugs with a reproducible input, including Windows paths, time zones and SQLite locks.

## What not to comment on

- Formatting, naming, import order or anything ruff checks.
- Speed, query batching or ranking order, unless it changes a result.
- Wording edge cases that cannot make a denial or unrelated sentence read as evidence.
- Files under `eval/gold/`, `core/audit/rules.py` and `core/audit/prompts/` beyond saying they
  changed: their content is signed by the owner, not reviewed here.

## Held-out data

Never open, quote or describe files whose path contains `case02`. They are the hidden held-out
evaluation case.

## How comments are handled

The PR's author verifies every comment against the code, then either pushes a fix and replies
with what changed, or replies with the reason it is not a bug. Make each comment checkable: name
the input, the line, and the wrong output.

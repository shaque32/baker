# Baker: rules for every agent

Baker audits government claims about phone evidence for the criminal defense.
Each claim ends up supported, contradicted or unproven, with cited evidence.
Correctness is the product. One wrong "supported" in front of an expert destroys trust.

Read `docs/ARCHITECTURE.md` before writing code.

## Stack
- Python 3.12, type hints everywhere, pydantic v2 for data models.
- pytest for tests, ruff for lint and format.
- SQLite for storage. `core/schema.sql` is the only place tables are defined.

## Frozen, human-owned files
Never edit these. If you need a change, stop and write it in `PROPOSED_CHANGES.md`
with the reason and the exact diff you want, then finish the rest of your task without it.
- `core/contracts.py`
- `core/schema.sql`
- `core/audit/rules.py` (verdict rules)
- `core/audit/prompts/` (stance and claim prompts, once they exist)
- `eval/gold/` (gold labels and the mock affidavit)
- `CLAUDE.md`

## Evidence rules
- The LLM never decides verdicts. It only labels individual pieces of evidence.
  Verdicts come from `core/audit/rules.py`.
- A claim is never SUPPORTED on a model's stance label alone. An expert must accept the
  label on the supporting evidence first.
- Every derived record carries a `source_ref` back to the original artifact.
- Every displayed item carries a provenance tier: observed, derived, inferred or confirmed.
  An inference never becomes observed because another component consumed it.
- Any quote attributed to evidence must be verified verbatim by code before it is stored.
  Unverified quotes are discarded, never stored.
- Store times as UTC, and keep the original offset and the raw source value.
- "Not found" never means "did not happen." Absence findings state what was searched and what coverage the source had.
- Never auto-merge identities. Links stay proposed until an expert confirms them.
- The tool never says guilty, innocent, leader or deleted.

## Data safety
- Never use real case data. Synthetic data only, generated under `eval/`.
- Never put real discovery material in the repo, in prompts, in tests or in fixtures.
- No network calls anywhere in `core/`. No telemetry. Models load from local paths.
- Inputs are opened read-only and SHA-256 hashed on import.

## Before you finish
- `make check` must pass (lint, tests, eval).
- Report the eval numbers in the PR description.
- If an eval metric got worse, say so plainly. Do not tune tests or gold data to make it pass.

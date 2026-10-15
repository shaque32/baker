# Baker: rules for every agent

Baker audits government claims about phone evidence for the criminal defense.
Each claim ends up supported, contradicted or unproven, with cited evidence.
Correctness is the product. One wrong "supported" in front of an expert destroys trust.

Read `docs/ARCHITECTURE.md` and `docs/PRODUCT_STATUS.md` before writing code.

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
- A claim is never SUPPORTED on a model's stance label alone. In the alpha (rules 0.2.0) an expert
  must accept its supporting evidence (accepted). An AI reviewer acceptance (ai_accepted) only sorts
  evidence for the expert and never makes a claim SUPPORTED; such a claim stays UNPROVEN, awaiting
  expert review. AI-only coverage of event assumptions can return only after a local model accepts
  zero overreach traps on the signed probe set, and only through a change to `core/audit/rules.py`
  that bumps RULE_VERSION.
- Every derived record carries a `source_ref` back to the original artifact.
- Every displayed item carries a provenance tier: observed, derived, inferred, ai_reviewed or confirmed.
  ai_reviewed means the local AI reviewer accepted it. confirmed means a human expert accepted it.
  Under rules 0.2.0 every SUPPORTED verdict is confirmed.
  ai_reviewed never displays or exports as confirmed, and a human decision always overrides it.
- The AI reviewer only reviews evidence items. It never confirms identity links or claims.
- The AI reviewer runs on the local model in core/. Cloud models may be used only in eval/, as benchmarks.
- An inference never becomes observed because another component consumed it.
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
- case02 is the hidden held-out case. Never read `eval/synthetic/case02*`, `eval/gold/case02/`,
  `eval/out/case02/` or any test whose name contains `case02`, unless your task names case02.
  `make eval` reports it as aggregate numbers only; never tune anything to them.

## Product status docs
`docs/PRODUCT_STATUS.md` and `docs/CHANGELOG_AI.md` are the source of truth for what Baker does.
Other agents and product tools read them, so they must match the code, not the plan.
- Read `docs/PRODUCT_STATUS.md` before starting work.
- A meaningful change is one that changes a capability, a model or its job, a verdict path,
  privacy or network use, a measured benchmark, or what Baker may claim to customers.
  Refactors, test-only fixes and wording changes are not.
- In the same PR as a meaningful change, update `docs/PRODUCT_STATUS.md` and add one entry at
  the top of `docs/CHANGELOG_AI.md` with: what changed and why; where it lives (main, a named
  branch or PR, or local only); what was tested; what is open or uncertain; and whether it
  affects capabilities, privacy, performance or customer-facing claims.
- Check every statement against code, tests or a recorded run. Mark anything not measured as
  unverified, and say which hardware and date a number comes from.
- Never put secrets, API keys or real case data in these files, and nothing about case02
  beyond the aggregate numbers `make eval` prints.

## Before you finish
- `make check` must pass (lint, tests, eval).
- Report the eval numbers in the PR description.
- If an eval metric got worse, say so plainly. Do not tune tests or gold data to make it pass.
- For a meaningful change, `docs/PRODUCT_STATUS.md` and `docs/CHANGELOG_AI.md` are updated.

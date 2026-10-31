## 2026-10-30: Claims screen fixes from a design critique (#184)
- Changed: The Claims screen's progress label read "Nothing waiting on you" beside the heading
  "N claims need you"; it now reads "Settled". The Supported tile said "The verdict rules or an
  expert decided it", which suggested the rules alone can make a claim supported; under rules
  0.2.0 and later an expert must accept its evidence or override the verdict, and claims
  resting on AI review sit under Needs you (`needs_you()`), so the tile now says "An expert
  accepted its key evidence or overrode the verdict" (the override half from a Codex finding). While
  claims still wait on the expert, the Contradicted and Supported groups fold behind "Show N
  claims" (a `<details>`, no script). The Unproven tile's dot is a visible ring, and notices and
  the next-up paragraph stop at a readable line length. Look only, in `ui/pages.py` and
  `ui/theme.py`; the exported report is unchanged.
- Where: PR #184
- Verified: ruff; pytest (see PR description for the full run and eval numbers).
- Open: A reason line on Contradicted rows and clickable Unproven reason chips were proposed
  and not done. The demo banner text was not shortened, because it is shared with the report.
- Affects: customer-facing claims (the Supported tile's wording)
- Status doc: no change

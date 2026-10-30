## 2026-10-30: Report, Identities and Exhibits fixes from a design critique (branch report-identities-fixes)
- Changed: Look and layout only, from an impeccable critique of the three pages on the demo case.
  Report (0.29.0): each source's format notice reads as a plain item in Limitations instead of
  a boxed callout inside an empty bullet, and on each claim as one compact line (still on every
  claim that rests on the source, as 0.18.0 requires); the "Claim id" line is left out when the
  claim's name is its id, as the claim page already does; source ids in the evidence table wrap
  at spaces before breaking inside a word; the summary table is narrower; message sender lines
  are 12.5px. Identities: the eyebrow label is gone, the lede is one sentence and the rest of
  the link rules sit under "How links are proposed and used" (same words). Exhibits: the
  curated-coverage warning moves above the form, and "One message per" is a fieldset with its
  options stacked. Placeholder text is darker (#6f6b64, about 5:1 on white).
- Where: branch report-identities-fixes
- Verified: ruff; pytest and make eval (see PR description); rendered at 1280px and in a 390px
  frame on the demo case.
- Open: Per-claim format notices still repeat on every claim; collapsing them changes what the
  report states per claim and was not done. The absence paragraph on each phone owner is still
  one block; restructuring safety wording was left for a decision.
- Affects: none
- Status doc: no change

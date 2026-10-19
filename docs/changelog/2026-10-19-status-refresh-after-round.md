## 2026-10-19: First status refresh: merged PRs, pending entries and the 14B's signed-set result
- Changed: `docs/PRODUCT_STATUS.md` now matches main `e6e34f8`. It applies the five pending
  `docs/changelog/` entries (#77, #81, #84, #95, #96), records #71 to #96 as merged (contracts
  0.4.0, report 0.7.0, cloud #68 on main but gated off), and replaces two stale lines that said
  the local 14B had not been run on the signed set: with stance prompt v1.1 it scores
  contradicts precision 58% (11 of 19, bar 90%) and shows 6 moved traps as supports (Arsh's
  24 GB MacBook Air, commit `eee8d15`, 2026-10-19; from the "Audit our model scoring" thread).
  The archive's stale `Where:` lines now name each PR's merge. Section 10 has a fresh
  `make check` run on main.
- Where: branch `claude/changelog-per-pr-ewuqbu`
- Verified: each merge commit checked against `git log` on main; the 14B figures checked
  against `/mnt/project-files/baker/cloud-bench/2026-10-16/fair-14b-vs-opus/local-arm/RESULTS.md`;
  `make check` on this branch.
- Open: #68's own archive lines (still "draft, not merged") are left for the Cloud-first
  thread's branch. Line numbers in section 12 were not re-checked. The same Mac run also timed a
  full local case01 (no sheet, 55% accuracy, 0 false supported); that is not recorded here and
  stays with the "Audit our model scoring" thread.
- Affects: customer-facing claims (the local model's measured stance quality is now stated;
  section 12 row 6 reflects #68 merged and gated off). No capability, privacy or performance
  change.
- Status doc: applied 2026-10-19

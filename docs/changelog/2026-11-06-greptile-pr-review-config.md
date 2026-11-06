## 2026-11-06: Greptile PR review config (#227)
- Changed: adds `.greptile/` (config.json, rules.md, files.json) so the Greptile GitHub app
  reviews pull requests against the house rules in CLAUDE.md and docs/MERGING.md: signed files,
  verdicts from rules only, verbatim quotes and provenance, network and privacy limits, agents
  that only propose, synthetic data only, the changelog rule and the frozen Baker names. It
  reviews once when a PR opens (drafts included), not on every push; a new review is asked for
  by comment. case02 paths, binaries, the site and the changelog archive are excluded. Why: to
  spend fewer Codex credits on routine review. No product code changes.
- Where: PR #227
- Verified: both JSON files parse; `make check` on this branch. Greptile itself is unverified
  until the app is installed on the repository; field names follow Greptile's published docs
  and public repos using the same format (2026-11-06), not a live run.
- Open: the app is not installed yet. How a Greptile pass counts in the merge checklist
  (docs/MERGING.md line 8) is not changed here and waits for Arsh's choice. Greptile reads
  `.greptile/` from the PR's own branch, so a PR can change its own review rules.
- Affects: none (developer tooling; the public repository's code is read by a third-party
  review service, no case data or product behavior involved)
- Status doc: no change

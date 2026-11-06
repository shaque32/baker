## 2026-11-06: Greptile PR review config and merge gate (#227)
- Changed: adds `.greptile/` (config.json, rules.md, files.json) so the Greptile GitHub app
  reviews pull requests against the house rules in CLAUDE.md and docs/MERGING.md: signed files,
  verdicts from rules only, verbatim quotes and provenance, network and privacy limits, agents
  that only propose, synthetic data only, the changelog rule and the frozen Baker names. It
  reviews once when a PR opens (drafts included), not on every push; a new review is asked for
  by comment. case02 paths, binaries, the site and the changelog archive are excluded.
  docs/MERGING.md now makes a clean Greptile pass the final review gate on every PR (line 8)
  in place of the clean Codex pass: Greptile's suggestions are applied by default, it wins
  where Codex or Grok disagree, and Codex and Grok findings are still answered but no merge
  waits for them. Signed files still need Arsh's approval. Arsh chose this on 2026-11-06 in
  the project thread. Why: to spend fewer Codex credits on routine review. No product code
  changes.
- Where: PR #227
- Verified: both JSON files parse; `make check` on this branch. Field names follow Greptile's
  published docs and public repos using the same format (2026-11-06), not a live run.
- Open: Arsh installed the app 2026-11-06; the first live Greptile review is on this PR.
  The bot account name `greptile-apps[bot]` and the `@greptileai` re-review trigger are
  unverified until it posts. Greptile reads `.greptile/` from the PR's own branch, so a PR
  can change its own review rules. Verdict-path code no longer needs a second model's review
  before merge.
- Affects: none (developer tooling; the public repository's code is read by a third-party
  review service, no case data or product behavior involved)
- Status doc: no change

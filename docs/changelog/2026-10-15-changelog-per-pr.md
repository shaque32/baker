## 2026-10-15: One changelog file per PR; status edits applied after merge
- Changed: each PR now adds its own entry file in `docs/changelog/` instead of editing
  `docs/CHANGELOG_AI.md`, and states its `docs/PRODUCT_STATUS.md` edit in that entry
  (`Status doc:`) instead of editing the status file. One status refresh PR applies the pending
  edits after merges. Why: every open PR edited the same two files, so each merge left the rest
  conflicting (seen in the 2026-10-15 merge round). `docs/CHANGELOG_AI.md` is kept as the archive;
  `make changelog` prints the whole log in one view, newest first.
- Where: PR (branch `claude/changelog-per-pr-ewuqbu`), not merged. The matching CLAUDE.md wording
  needs Arsh's signature and is not in this PR until Arsh applies it.
- Verified: `tests/test_changelog.py` (entry format, ordering, assembled view, pending list);
  `make check` on this branch.
- Open: until the refresh PR runs, `docs/PRODUCT_STATUS.md` lags main; pending entries win where
  they differ. Grok bots must read `docs/changelog/` as well as `docs/CHANGELOG_AI.md`.
- Affects: none (process only; no capability, privacy, performance or claims change).
- Status doc: no change

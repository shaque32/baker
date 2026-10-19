## 2026-10-15: One changelog file per PR; status edits applied after merge
- Changed: each PR now adds its own entry file in `docs/changelog/` instead of editing
  `docs/CHANGELOG_AI.md`, and states its `docs/PRODUCT_STATUS.md` edit in that entry
  (`Status doc:`) instead of editing the status file. One status refresh PR applies the pending
  edits after merges. Why: every open PR edited the same two files, so each merge left the rest
  conflicting (seen in the 2026-10-15 merge round). `docs/CHANGELOG_AI.md` is kept as the archive;
  `make changelog` prints the whole log in one view, newest first.
- Where: main (PR #84, merge 4ed06da, 2026-10-19), with the matching CLAUDE.md wording signed by
  Arsh ("approved", 2026-10-16 01:01Z).
- Verified: `tests/test_changelog.py` (entry format, ordering, assembled view, pending list);
  `make check` on this branch.
- Open: until the refresh PR runs, `docs/PRODUCT_STATUS.md` lags main; pending entries win where
  they differ. The first refresh (the "not merged" lines for PRs merged since 2026-10-15) is a
  separate PR after #81 and #77 merge. Grok bots must read `docs/changelog/` as well as
  `docs/CHANGELOG_AI.md`.
- Affects: none (process only; no capability, privacy, performance or claims change).
- Status doc: no change

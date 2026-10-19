# AI changelog entries

One file per change, so open PRs never edit the same changelog file. Read the log in one view
with `make changelog` (or `python tools/changelog.py build`): these files and the entries in
`docs/CHANGELOG_AI.md` (the archive of entries written before the per-PR rule), merged newest
first by date. The archive takes no new entries; the status refresh may still correct its
`Where:` lines.

## Adding an entry

In the same PR as a meaningful change (CLAUDE.md, "Product status docs"), add one new file
here named `YYYY-MM-DD-<short-name>.md`: the date you write it, then a few lowercase words
joined by hyphens (for example `2026-10-16-stated-time-windows.md`). Make the short name
specific to your change, such as your branch's own words, not a generic one like `fix-report`:
two PRs that pick the same name on the same day collide. If the name is already on main or in
another open PR, pick another. Never edit another PR's entry, except to correct it or to apply
its status edit (below).

```
## YYYY-MM-DD: <change> (#PR)
- Changed: <what and why>
- Where: PR #N | main | local only
- Verified: <tests, eval numbers, runs; or "unverified">
- Open: <what is incomplete or uncertain>
- Affects: <capabilities | privacy | performance | customer-facing claims | none>
- Status doc: no change | pending: <the exact edits docs/PRODUCT_STATUS.md needs, by section>
```

`pending:` must be followed by the edits themselves; a bare `pending` fails the check.

A bullet may run over several lines; indent the continuation lines. `make test` checks the
name, the heading date and that every field is present.

## PRODUCT_STATUS.md

`docs/PRODUCT_STATUS.md` stays one file, but feature PRs no longer edit it, because every PR
editing it is what made open PRs conflict after each merge. Instead the entry's `Status doc:`
line says exactly what to change. After PRs merge, one status refresh PR (started by the
coordinator) works from main: it applies every pending edit to `docs/PRODUCT_STATUS.md`, changes
those lines to `Status doc: applied YYYY-MM-DD`, and sets `Where:` to `main (#N, merged
YYYY-MM-DD)` on every entry that still names a PR or branch, since anything on main is merged
(entries marked `local only` stay as they are). It also corrects stale `Where:` lines in the
archive.
`python tools/changelog.py pending` lists every entry with something left to do.

Until then, a merged entry marked `pending` is newer than `docs/PRODUCT_STATUS.md` and wins
where they differ; the status file's header says so.

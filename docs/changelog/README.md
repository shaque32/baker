# AI changelog entries

One file per change, so open PRs never edit the same changelog file. Read the log in one view
with `make changelog` (or `python tools/changelog.py build`): these files newest first, then the
older entries in `docs/CHANGELOG_AI.md`, which is the archive up to 2026-10-15 and is no longer
edited.

## Adding an entry

In the same PR as a meaningful change (CLAUDE.md, "Product status docs"), add one new file
here named `YYYY-MM-DD-<short-name>.md`: the date you write it, then a few lowercase words
joined by hyphens (for example `2026-10-16-stated-time-windows.md`). Never edit another PR's
entry, except to correct it or to apply its status edit (below).

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
YYYY-MM-DD)` on every entry that still names a PR or branch, since anything on main is merged.
`python tools/changelog.py pending` lists every entry with something left to do.

Until then, a merged entry marked `pending` is newer than `docs/PRODUCT_STATUS.md` and wins
where they differ; the status file's header says so.

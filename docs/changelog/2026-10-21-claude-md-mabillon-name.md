## 2026-10-21: CLAUDE.md names the product Mabillon (#115)
- Changed: Arsh renamed the product and company from Baker (a working name) to Mabillon on
  2026-10-21 and signed this CLAUDE.md edit ("approved" in the "Rename to Mabillon" thread).
  The agent rules now say Mabillon, and a new Data safety line says file format ids, the
  `baker_version` field and the `baker` command alias keep the old name, so agents never rename
  them and break old cases or bundles. No code changes; the app, CLI and installers still say
  Baker until the rename PRs in /mnt/project-files/baker/plans/rename-mabillon.md land.
- Where: main (#115, merged 2026-10-22)
- Verified: `make check`; wording only.
- Open: the code rename (display name, `mabillon` command with a `baker` alias, installers).
- Affects: none (agent instructions only).
- Status doc: no change

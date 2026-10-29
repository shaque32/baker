## 2026-10-29: Impeccable design skill for agents working on the UI (#171)
- Changed: added the Impeccable design skill (Apache-2.0, skill 4.8.0, engine 0.1.18) for coding
  agents: `.claude/skills/impeccable/`, its four helper agents in `.claude/agents/`, a project
  `.impeccable/config.json` that turns its usage pings and update checks off, and `PRODUCT.md`,
  the design context it reads (users, signed labels, the no-script CSP, vendored fonts, banned
  words, the site's pipeline animation left alone). Arsh asked for it for the next UI rework.
  Its edit hooks are not installed, and its 21 MB engine binary is not committed: the launcher
  downloads it from the project's GitHub releases on first use and checks it against
  `scripts/engine-checksums.txt`.
- Where: PR #171
- Verified: installed into a sandbox copy with `impeccable install --providers=claude
  --scope=project` from the signed 4.8.0 release bundle; engine SHA-256 matched the shipped
  checksum; `impeccable detect` ran on saved pages of the demo case (calm look, PR #167 branch).
  `make check` passed.
- Open: nothing in the app changed yet. impeccable.style is blocked in cloud sessions, so
  `npx impeccable install` fails there; the committed copy avoids it. Its detector reads HTML and
  CSS, not the CSS strings in `ui/theme.py`, so it checks rendered pages only.
- Affects: none (developer tooling; nothing in Mabillon's code, network use or privacy changes)
- Status doc: no change

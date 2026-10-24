## 2026-10-20: Status refresh after #101 (Opus 5.5 in PROBE_PASSED)
- Changed: `docs/PRODUCT_STATUS.md` now matches main `75e75f1`. It applies #101's pending edits:
  `PROBE_PASSED` lists Opus 5.5 at medium effort with the cloud prompt, stance v1.2, so a case the
  expert opts in to cloud AI can use it (sections 2, 3, 4, 5, 8, 9, 11 and 12), and section 7 gets
  the case01 row for that setup (95%, 0 false supported, $8.16, 2026-10-20) with the older Opus row
  labelled "(prompt v1.1)". Section 10 has a fresh `make check`. #99's and #101's entries now name
  their merges.
- Where: main (#102, merged 2026-10-20)
- Verified: each replaced phrase matched main exactly once; `make check` (Linux, 2026-10-20):
  2282 passed, case01 gated 1.00 / 0 false supported, unreviewed 0.55, hostile PASS, case02 0.90 /
  0 false supported.
- Open: #101's case01 numbers are copied from its entry, not re-run here.
- Affects: customer-facing claims (cloud is now usable for opted-in cases; "local by default"
  still holds). No capability, privacy or performance change beyond what #101 recorded.
- Status doc: applied 2026-10-20

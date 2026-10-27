## 2026-10-21: Expiring download links for pilot installers (#125)
- Changed: Adds `tools/pilot_link.py`, which makes a presigned (AWS Signature Version 4) link
  to an installer in a private Cloudflare R2 bucket. The link works for up to 7 days (3 by
  default). Also adds `docs/pilot-links.md` with Arsh's R2 setup steps. This way pilot
  installers reach named examiners without a sign-in on the website.
- Where: main (#125, merged 2026-10-24)
- Verified: `tests/test_pilot_link.py`. The signer reproduces the signature in AWS's published
  presigned-URL example. The R2 link uses path style with region `auto`, a link over 7 days is
  refused, and missing settings are named. Unverified against a real R2 bucket until Arsh
  makes the first link.
- Open: a link can't be revoked by itself; the only way is to delete the token, which stops
  every link. Downloads are not logged.
- Affects: none in the app. The tool lives in `tools/`, not `core/`. Only `--check` makes a
  network call: one HEAD request to R2.
- Status doc: no change

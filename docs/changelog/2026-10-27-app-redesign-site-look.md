## 2026-10-27: App, report and installer in the getmabillon.com look (#149)
- Changed: visual redesign so the product matches the new site (Arsh, 2026-10-27). Review
  screen (ui/theme.py): IBM Plex Sans for all text (replacing Inter, as on the site), Instrument Serif only for page titles and big
  numbers, no monospace or capitalised labels (ids, hashes and times are Plex Sans with tabular
  figures), tables without a header band and with roomy rows, 40px inputs with labels above
  and a focus ring, quiet secondary buttons and one navy primary, tabs as soft pills, format
  notices as one line with a dot. The new-case and add-a-claim forms get field labels.
  Downloaded report: report 0.19.0, the same type and table style; visual only, no wording,
  fact or section changed. Windows installer: wizard artwork and Setup icon drawn from the
  app's mark (packaging/windows/art/make_art.py). Mac installer: bold step titles.
- Where: PR #149
- Verified: make check (lint, tests, eval); demo case screens rendered in Chromium at 1440x900
  and 390x844 before and after. Windows installer art checked as images only; the built
  wizard is unverified until the Windows CI build and a Windows install.
- Open: dark mode (the site has it) not done; the audit log's JSON details read as Plex Sans text.
- Affects: none (look only; no capability, privacy, performance or claim change)
- Status doc: no change

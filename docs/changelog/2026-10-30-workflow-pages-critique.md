## 2026-10-30: Add a claim, Set up and run, Audit progress, Audit log and Activity: fixes from a design critique
- Changed: screen-only fixes from an /impeccable critique of the five pages; no verdict path,
  model, check or report output changes.
  - Add a claim: paragraphs are grouped by document (optgroup) instead of repeating the title in
    every option; claim types read "content meaning" (the submitted value is unchanged).
  - Set up and run: Remove now comes after Up, Down and Edit the wording, away from the reorder
    buttons; the Files table shows the first 16 characters of each SHA-256 with the full hash on
    hover (the full hashes stay in the report's chain of custody).
  - Audit progress: a run's note reads as its own sentence after the status, and "Findings show
    here and on Claims once this run is the one on screen" is said once above the table instead
    of on every row.
  - Audit log: Details shows a 120-character summary, with the full entry in a "Full entry"
    disclosure.
  - Activity: the time-on-page caveats sit in a "How time on page is counted" disclosure.
  - Input placeholders are #75716a (about 4.6:1 on white, was 2.9:1).
  Why: the critique found raw machine text, a filler column and a destructive button beside the
  reorder buttons; placeholder contrast failed WCAG AA.
- Where: branch pages-critique-fixes
- Verified: on the owner's Mac, 2026-10-30. Rendered each page from the scripted demo and
  checked the new markup; `make check` lint and tests (one environment-only failure, see the
  PR); case01 model-free eval PASS, accuracy 1.00, 0 false supported.
- Open: the paragraph option text stays cut at 70 characters: longer cuts can show affidavit
  words the page text guard refuses, and an option cannot carry the cited-text span.
- Affects: no capability, privacy, performance or customer-facing claim change
- Status doc: no change

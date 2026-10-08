# Expert review screen

`baker serve --db case.db` starts a local web server on `127.0.0.1` (port 8765 by default) and
the expert reviews the case in their own browser. Nothing leaves the computer: the server binds
the loopback address only, pages contain no scripts and load nothing from outside, and
`core/`, `core/review/`, `core/report/` and `ui/` import no network client (a test enforces it).

## What the expert does

1. **Case page.** Enter your name once; it is recorded with every decision. Check the sources
   and their SHA-256 hashes, and stipulate who used each phone (a stipulation, not a finding;
   every report lists it as a limitation).
2. **Claims queue.** Claims sorted by what needs you: AI-accepted supporting evidence first, then
   supporting evidence nobody reviewed, then contradicting or complicating items, then verdicts to
   confirm. A claim whose supporting evidence no expert has decided shows as
   **Unproven, awaiting expert review**, never as supported.
3. **Claim page.** The claim, its paragraph as printed, the verdict and the rules' reasons, the
   assumptions and what each check searched, and every evidence item grouped by review state.
   Accept, dismiss or reopen each item with a one-sentence reason. "See about 20 messages around
   it" shows the conversation around the record in the phone's local time.
4. **Re-run verdicts.** Decisions do not change a verdict by themselves. "Re-run verdicts" runs
   `core/audit/rules.py` and the invariants again on the stored evidence with the current review
   statuses (`core/review/redecide.py`, also `baker redecide`). No model is called, so it takes
   seconds. Claims edited or added since the audit need a full `baker audit`.
5. **Confirm or override** each verdict. An override needs a note and prints as an expert
   override.
6. **Report.** View it, save it (`Report` page, or `/report?download=1`), or print it to PDF from
   the browser; the print layout is built in. **Audit log** verifies the hash chain.

## Rules the screen keeps

- Every change goes through `core/review/actions.py`, so the hash-chained audit log records it.
  The screen never sets a verdict; only `rules.py` does, through a full audit or a re-run.
- Under rules 0.2.0 no claim is supported until an expert accepts its key evidence. An item the
  local AI reviewer accepted shows its tier as `ai_reviewed` ("AI-reviewed, not confirmed"); only
  an expert's acceptance shows as `confirmed`.
- The screen and the report use the same labels (`core/review/status.py`).
- Every page passes the same forbidden-word check as the report.

## Local-server protections

Another web page open in the same browser can send requests to `127.0.0.1`, so the server
checks the Host header (blocks DNS rebinding), requires a per-session random token on every
form, refuses cross-site requests, and sends a Content-Security-Policy that forbids scripts,
framing and outside loads.

## Known gap

The expert can only accept evidence the audit retrieved. If retrieval missed the key record (in
synthetic case01, C01's contact row and C09's call rows), the claim cannot reach supported on the
screen; the expert can override the verdict with a note, which prints as an expert override.

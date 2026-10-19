# Baker AI changelog

One entry per meaningful change, newest first. Each entry is the handoff for that change and
answers five questions: what changed and why; where it lives (local, branch or main); what was
tested; what is open; what it affects (capabilities, privacy, performance, customer-facing
claims). Add the entry in the same PR as the change, and update `docs/PRODUCT_STATUS.md` with it.
Earlier history (PRs #1 to #43) is in git; this log starts with the 2026-10-13 build wave.

Template:

```
## YYYY-MM-DD: <change> (#PR, commit)
- Changed: <what and why>
- Where: main | branch #N (not merged) | local only
- Verified: <tests, eval numbers, runs; or "unverified">
- Open: <what is incomplete or uncertain>
- Affects: <capabilities | privacy | performance | customer-facing claims | none>
```

---

## 2026-10-16: Forwarded messages marked on the record (signed schema change)
- Changed: Arsh signed the `messages.forwarded` and `messages.forwarded_from_raw` columns
  (PROPOSED_CHANGES.md, "approved" 2026-10-16 02:53Z in the UFDR thread), applied to
  `core/schema.sql` and the `Message` model in `core/contracts.py`. The UFDR and Excel importers
  now mark each message the extraction labels Forwarded; the UFDR importer records the original
  author when the package embeds the original and names exactly one sender, as written. The
  claim page and report name that author in the record's warning ("which Baker has not checked"),
  as a cited span: it is the source's text, never Baker's words, so a name such as "Deleted
  Account" passes the forbidden-word check. Contracts 0.3.0 -> 0.4.0 (`core/contracts.py` and the
  `core/schema.sql` header, as that file's own rule asks); report 0.4.0 -> 0.6.0 (0.5.0 is #91's).
  Fail-closed handling from #73 is unchanged: a forwarded message still cannot support or
  contradict a claim, checks resting on it stay inconclusive, and SenderCheck never credits the
  forwarder. Cases made before the columns keep working from the coverage list. After Codex
  review: no author is recorded when the embedded message is itself forwarded (it would name an
  intermediate forwarder), and the claim, stance, check and coverage notes now say Baker "has not
  verified" who first wrote the words, which stays true when the extraction names an author.
- Where: branch `claude/project-thread-hz9jqt` (fresh from main), PR #89, not merged.
- Verified: 4 new or extended tests (UFDR marks with and without a named author, quote not a
  forward; Excel label; a case made on the old schema still fails closed; an author named
  "Deleted Account" renders cited in the report and on the claim page, which pass the
  forbidden-word check); full `make check` and eval in the PR description. Grok's audit of
  31f2993 (standing in for Codex, Arsh 2026-10-19) found the cited-span and version issues,
  fixed here.
- Open: AXIOM does not read forwarded marks yet; only forwards the extraction labels are caught;
  the original author is the extraction's claim, not checked. The stance prompt is not told the
  message was forwarded (prompts are signed); the stored stance is still downgraded. No in-place
  migration: an existing case database is not upgraded, so its messages lack the
  columns and keep the coverage-list behaviour.
- Affects: capabilities (forwarded marked on the record and shown with its author). No verdict,
  privacy or performance change. Customer-facing claims unchanged; UFDR stays unverified.

## 2026-10-15: Pilot gates, onboarding kit, methods note, security pack (#82)
- Changed: four documents, no code (Grok Product review #80 items 9, 10, 11, 13).
  `docs/PILOT_GATES.md` defines pilot-ready as pass/fail gates (12, then 18 after Grok's pilot-ready list) with today's state;
  `docs/PILOT_ONBOARDING.md` covers hardware, Mac and Windows install (Windows unsigned), the
  `baker demo` walkthrough, a first case, unverified imports and blocked cases;
  `docs/METHODS.md` describes claim, assumption, check and rules, the expert gate, verdict meanings,
  provenance and hashing, and limits, with no accuracy figures; `docs/SECURITY_PRIVACY.md` has the
  data-flow diagram (local today; #68's opt-in cloud gated, no model passed), encryption, key handling, retention
  and deletion with Anthropic's pages linked, the cloud policy with the CSAM rule, and how to verify
  the no-network claim. Codex rounds 1 (10 findings) and 2 (8: overrides bypass the rule
  prerequisites, evidence reasons not hash-chained, coverage locators capped at 50, cloud retries,
  no copying of an installed Mac folder, gated cloud option, anchor limits, #68 merge state) and 3 (5: checksum by a separate route, stop Baker before a
  backup copy, request draft and ufdr-check output in deletion, gate 6 scoped to time fields, the
  import-mismatch bug disclosed) fixed. On 2026-10-16 Grok's pilot-ready list was folded in
  (Arsh agreed): gates 13 to 18 added (integrity fixes #86 and #88, signed case02 answer key,
  stopped runs, pilot agreement, one-pager and support, feedback form); runtime gate names the
  24 GB Mac and AWS g5 (A10G); real-export gate covers Cellebrite, UFDR and AXIOM. After #76 merged, gates 2 and 3 are met;
  gate 14 is met by the case02 key Arsh signed 2026-10-12. Codex round 4 (5) fixed;
  round 5 found the printed Baker version is a constant, not the build, so gate 3 is back to not
  met: 8 of 18. Round 6 (5) fixed: verdicts scoped to finished claims, provenance tiers scoped
  to the objects that carry them, the installer-download test described as what it checks, key
  destruction leaves `case.json` and input names readable, and the feedback form published as
  `docs/PILOT_FEEDBACK_FORM.md` (pricing question left out of the public repo) so gate 18 has
  evidence on main. `install-mac.md` and `demo.md` no longer state the 6 to 8 h runtime as
  current. PRODUCT_STATUS section 11 links the gates.
- Where: branch `claude/project-thread-390z80`, PR #82 (main once merged).
- Verified: each statement checked against main `8ed89f9` code and docs, and #68 head `de219c1`
  for cloud facts; the 6 no-network tests named in the pack pass (Linux, 2026-10-15); Anthropic's
  API retention page and Commercial Terms read 2026-10-15 (the privacy-center article did not load
  from the cloud session and was not re-read).
- Open: gate 11 (an outside person completes the kit on a clean Mac) needs a human; 8 of 18 gates
  are met (gate 2 by #76; gate 14 by the case02 key signed 2026-10-12; gates 6, 7, 8 by #72, #74, #68; gate 12 by this PR; gate 15 already in place; gate 18 by the form this PR publishes); the Mac installer's uv, Python and
  PyPI downloads are not hash-pinned (disclosed in the pack); gate 4 waits on #89 (signed
  forwarded-message schema); gate 13 on #86 and #88.
- Affects: customer-facing claims (what buyers and examiners are told, all checked against code);
  no capability, privacy or performance change.

## 2026-10-15: Curated report against a larger source of the same phone (#78)
- Changed: when a case holds an examiner-curated report and a larger source of the same phone
  (a UFDR), each report message, call and contact is found once, found more than once, or not
  found in the larger source; the messages and calls the larger source holds that the report
  does not are listed near each claim, by conversation then time distance, with no model
  ranking. Fails closed: ambiguous candidates, and records near a report record not found, are
  "may be in the report", never counted; under 95% found lists nothing. Selection tab, report
  section (one renderer) and a line on each claim page. Never changes a verdict; nothing stored. (Grok Product item 9.)
- Where: branch `claude/project-thread-y7z11i`, PR #78, not merged.
- Verified: 29 tests on two synthetic pairs (case01 item1 report vs a UFDR with planted records;
  a small new pair): planted omissions found per claim in the expected order, ambiguous and
  unmatched cases held back, screen and report list the same records, read-only. Headless-
  Chromium smoke passed (no external requests, Referrer-Policy same-origin). case02 not used:
  it is held out.
- Open: not checked on real Cellebrite or AXIOM exports (no public UFDR, #73); Grok made this
  depend on item 8. Pairing rests on a shared phone-owner account plus the same stated device
  model (no serial number or IMEI is stored); records after the report's extraction are not
  counted, and contacts (which carry no time) are never counted (Codex review). Speed
  measured only on case01 size (about 0.2 s) and a 120,000-message in-memory match (about
  1 s); not on a real case.
- Affects: capabilities (new analysis, branch only); no privacy or network change; customer
  claims unchanged until merged and checked on real exports.

## 2026-10-16: Training data for the small model's runs 6 to 8: harder sender and time traps (#87)
- Changed: the training-data generators (`eval/train/`) write harder traps, because the small
  model kept calling some of them supports. Run 6's data (`eval.train 1.4.0`): run 5 showed 10 of
  26 dev sender traps as supports; in its data every sender trap gave the record's exact words
  while every supports item reported the message, so the frame alone said supports. Now half the
  sender traps use the supports items' report frames, 3 in 10 name an account outside the chat
  (some with the same first name as the chat's contact), and the exact-value scene draws one too
  (400 to 515 sender traps); a report of "only if X will I Y" keeps "only". Run 7's data
  (`eval.train 1.5.0`): run 6 still showed 5 of 40 dev time traps as supports; in its data no
  time trap missed by under 15 minutes while 11% of supports bounds were that close, so closeness
  said supports. Now a bound, or a range's nearest end, lands 3 to 14 minutes from the record
  about as often whether it holds or misses (run 8's clock bounds: 33% of supports items', 40%
  of time traps'); time traps also miss at the record's own clock on the day before or after, at
  its UTC clock, and by a part of the day; the time scene pairs a time that holds with one that
  misses; time traps go from 355 to 823; irrelevant items carry a time half the time (from 35%),
  so a clock reading does not point away from irrelevant.
  Run 8's data is the same code drawn with seed 4. The Baker-wording items are unchanged
  (`eval.train.baker 1.4.1`); the guide is unchanged (signed v0.3).
- Where: branch `claude/project-thread-czwpc8`, PR #87, not merged. The data drops are in
  `/mnt/project-files/baker/stancedata/run6/`, `run7/` and `run8/`, each with its README, sha256
  and overlap reports.
- Verified: this head writes run 7's and run 8's generator output byte for byte (seed 1
  `6358fbc4…`, seed 4 `c292c424…`), and its run 6 commit (c16018e) writes run 6's (`4627aa11…`).
  Held-out files unchanged (test `4f106386…`, dev `36cd0d79…`). Overlap check on each delivered
  file against Baker's test data, the held-out files and the told-frame test sets: PASS, 0
  flagged, after dropping the 6, 3 and 6 chance matches the check flagged in the generator's
  output (listed in each drop's README). Blind reads from the signed guide alone: two readers each
  agreed with all 26 run 6 items (18 sender traps, 8 supports controls) and all 32 run 7 items (22
  time traps, 10 supports controls). New tests: frame-shaped and outside-account sender traps;
  bounds and ranges come as near the record whether they hold or miss, never nearer than 3
  minutes; another date's bound runs away from the record's date; a UTC miss gives the record's
  UTC clock. `make check`: lint clean, 2,014 tests passed, eval unchanged (case01 1.00, 0 false
  supported).
- Open: on dev, run 6 showed 9 moved traps as supports and run 7 showed 4 (3 time traps, 1 later
  correction). With supports needing p >= 0.99, run 7 meets every go-bar level on dev but misses
  tune.py's pre-set recall margin (0.95), so there is no candidate yet; run 8's result is
  pending. Contact and call rows still use the signed guide's rule 28 format (`<saved name>
  <number>`, `outgoing call from … at …, 604s`), not #76's text.
- Affects: none in the product (eval only). It changes what the candidate small stance model
  trains on.

## 2026-10-15: Training data for the small model's run 5 (#79)
- Changed: the training-data generators (`eval/train/`, `eval/stancedata/bakerform.py`) write
  more varied wording, because run 4 fit its training wording better than the held-out wording
  (on dev it showed 20 moved traps as supports). Supports items and the traps beside them now
  share report frames and time phrases; contact supports and denials share verbs and window
  shapes; Baker's window wording goes from 12 shapes to 218, each read back by Baker's own
  window reader; attachment captions show as context lines. Run 5 trained on the first commit
  (56e0da4: `eval.train 1.3.0`, `eval.train.baker 1.4.0`). A full review of that commit (Codex
  had no credits) found label and wording problems, fixed in `eval.train 1.3.1` and
  `eval.train.baker 1.4.1`: a part of the day missed a record by its narrow reading ("the
  evening" against a late-evening record); "the night of" only ever held a record and a range
  of dates only ever missed one, so the wording hinted at the answer; some sender and time
  traps said "the message "x" was sent by ...", words that name one message, which leaves
  their label unclear under guide rule 23; a zone-edge window could cross New Year or end at
  "12 p.m.". New tests check each one; 5 of them fail on the first commit.
- Where: branch `claude/project-thread-czwpc8`, PR #79, not merged.
- Verified: 56e0da4 regenerates run 5's training file byte for byte (19,250 items, sha256
  `00ceae8f…`); the head writes `c4031e1f…`, with the same counts by family and label. The
  held-out files are unchanged (test `4f106386…`, dev `36cd0d79…`). Overlap check on both
  training files against Baker's test data (the probe set and both synthetic cases) and the
  held-out files: PASS, 0 flagged. Every Baker window passes main's window check. Blind reads
  of the new wording from the signed guide alone: 59 of 60 agreed; the slips were fixed.
  `make check` on the head: lint clean, 1,891 tests passed, eval unchanged (case01 1.00, 0
  false supported).
- Open: run 5 (trained on the first commit's data) and run 6 (data from the head plus later
  generator changes, not yet in a PR) finished on #50's branch; neither is a candidate. What run
  5's data holds from the review: 0 wrong labels from the narrow part-of-day reading, 0 New Year
  windows, 1 window ending "12 p.m.", 6 time traps with a range of dates, 9 supports with "the
  night of" or "late in the evening", and 118 items (59 traps, 59 supports) whose words name one
  message. Contact and call rows read as main's quote check cites them, which is also the text
  #50's case items give the small model: `<saved name> <number>` (539 items) and `outgoing call
  from … at …, 604s` (1,041 items) of 19,250. #76 moves the check to the text Baker shows the 14B
  (contacts `<saved name>: <number>`, calls `outgoing Phone call from … to …, duration 604 s`).
  Once it merges, runs 5 and 6 meet the new text on those rows only, and a later data drop writes
  it.
- Affects: none in the product (eval only). It changes what the candidate small stance model
  trains on.

## 2026-10-15: Rules 0.2.2 for the stricter time windows (#75)
- Changed: `RULE_VERSION` 0.2.1 -> 0.2.2 with no rule logic change; it marks #66's new reading of
  stated time windows, so verdicts decided under 0.2.1 can differ. "Re-run verdicts" now refuses
  an audit made under rules older than 0.2.2 and asks for a full audit, since its stored
  assumptions were built the old way (`core/review/redecide.py`, `INPUTS_CHANGED_AT`).
- Where: branch `claude/project-thread-ia32bq`, PR #75, not merged. Arsh approved the bump
  2026-10-15 07:20Z.
- Verified: `make check` green; new redecide test; eval unchanged (case01 1.00, 0 false
  supported; case02 0.90, 0 false supported; hostile PASS). Codex's one finding fixed.
- Open: an existing case audited before 0.2.2 needs a full audit (hours on a laptop) before its
  verdicts can be re-run.
- Affects: verdicts on time-bound claims; the version printed on reports; the re-run button for
  older cases.

## 2026-10-15: Audit log checked on open and before every report; cut-off entries caught (#74)
- Changed: opening a case, and building or saving its report, now checks the audit log (before,
  the chain was only verified at report build, which printed the result and exported anyway, and
  at encryption). Two checks: the hash chain, and anchors: the newest entry's number and hash,
  written to `case.db.anchors.jsonl` beside `case.db` when a case opens and when a report is built,
  must still be in the log. Anchors catch entries cut from the end of the log, which the chain
  alone cannot. The screen checks again on every page and upload while a case is open, and encrypting or
  changing the passphrase checks first. A failed check fails closed: Cases shows "Review
  blocked" with the reason, an open case closes (a background job on it is told to stop) and an
  encrypted one locks, no report is built, CLI commands (`report` and `encrypt` included) stop
  and write nothing; `verify-log` says why. `docs/review-screen.md` gives the
  expert's steps when a case is blocked (keep the folder, restore a whole-folder backup, or
  rebuild from the original files). (Grok Product item 5 on #70 and its follow-up on #80.)
- Where: main, with PR #74.
- Verified: 33 tests in `tests/test_chain_on_open.py` (chain, anchors: truncation, rewrite,
  unreadable or non-text file, out-of-range anchor numbers, a last line missing its newline,
  dedupe, numbers and hashes only; CLI and screen, report and log page and upload refusal,
  non-text log values, a removed audit table, unwritable anchor file (found before anything is
  written; a new case that cannot be anchored is not kept and the open case stays open), one
  anchor file per database name, job stop, encrypt and passphrase refused, encrypted re-lock);
  full suite passes;
  headless-Chromium smoke (report refused after the newest entry was cut; intact report builds);
  eval unchanged (case01 1.00, 0 false supported, hostile PASS).
- Open: entries added after the newest anchor and cut before the next open or report are not
  caught, nor a change to the database and the anchor file together; a saved report's last hash
  is the anchor no one can change. Cases made before anchors are checked from their next open.
- Affects: customer-facing claims (tamper evidence enforced on open and export, truncation
  detected back to the newest anchor); a new unencrypted file per case holding entry numbers
  and hashes only (no case content, no times); one hash pass over the log per page while a case
  is open, per report and per Cases listing (2.3 ms for the 225-entry synthetic case01 log of a
  cloud bench run, this cloud container, 2026-10-15; unmeasured on a large real case).

## 2026-10-15: Count check no longer says "deleted" (#83)
- Changed: the count check's detail now reads "N of them carry the source's deletion flag"
  instead of "N of them are flagged deleted"; check version 1.0.0 to 1.0.1. The old text broke
  the CLAUDE.md rule against Baker saying "deleted", and the report's forbidden-words check would
  stop the report build whenever a counted message had the source's deletion flag. Found by Codex
  on #82. A grep of core/ and ui/ found no other Baker-authored prose with a forbidden word;
  `baker ufdr-check` output names the package's own `deleted_state` field and was left as is.
- Where: branch `claude/fix-count-deleted-wording-oxal24`, PR #83, not merged.
- Verified: new unit test (fails on main, passes here) checks the detail and search text against
  FORBIDDEN_WORDS and `check_report_text`. `make check` passed 2026-10-15 in a Linux cloud
  container: 1884 passed, 6 skipped; case01 model-free accuracy 1.00, 0 false supported.
- Open: none known.
- Affects: customer-facing text on the review screen and report (wording only); no verdict,
  privacy or performance change.

## 2026-10-15: UFDR reader checked on public test files; forwarded messages fail closed (#73)
- Changed: attachments linked only by file_id now resolve through taggedFiles and are hashed; a
  phone-owner UserAccount no longer takes a ProfilePicture URL as its identifier; `ufdr-check`
  mirrors both and checks owner account identifiers, and its direction check counts UserID-only
  owners (fallback ids count as the owner's, per Codex). (Grok Product item 8.)
  Forwarded messages fail closed (Grok #80 item 1): the UFDR and Excel importers list every
  message marked Forwarded (UFDR Labels or MessageExtraData; Excel Label column) or carrying an
  embedded forwarded or quoted original, by id, in the import's coverage record
  (`core/ingest/forwarded.py`). Downstream, a model's supports or contradicts on such a message
  is stored as complicates, so a claim resting on it stays Unproven; any check resting on it is
  inconclusive; SenderCheck never names the forwarder as the writer; the claim page and the
  report warn on the claim and on each record. The embedded original is never stored as the
  forwarder's words. Coverage (Grok #80 item 6): picture entries skipped as identifiers are
  counted (info); a taggedFiles id listed with two different paths links to no file and is
  listed under Limitations (attention). Rules 0.2.x untouched; full author and forwarder columns
  proposed in PROPOSED_CHANGES.md (needs Arsh's signature).
- Where: main (PR #73, merge 7655056).
- Verified: 6 tests for the sample bugs and 13 for item 1 and 6 (forwarded, quoted and nested
  forwards, Excel label, fail-closed stance after an expert accept, inconclusive checks,
  SenderCheck, claim-page and report warnings, picture count, repeated tagged ids, ufdr-check
  clean); lint clean; full suite and eval in the PR description (case01 1.00, 0 false supported
  before this change). Hand check 27 of 27 records match on autopsy-udfr `test.ufdr`
  (LGPL-2.1, hand-made) and IPED's UFED fixtures (GPL-3); neither committed, hashes in
  `docs/ingest/ufdr.md`. No public Cellebrite-made UFDR with a usable license exists; Digital
  Corpora and CFReDS return 403 from cloud sessions.
- Open: neither sample is Cellebrite output; 27 records, not the 50 asked for; no Reader count
  comparison. Until the schema change is signed, a forwarded message's sender field still shows
  the forwarder (with a warning beside it), and only labels Baker recognises ("Forwarded",
  "Auto-forwarded") are caught; a forward the extraction does not label is not detected.
- Affects: capabilities (UFDR import, forwarded handling) and verdict paths (fails closed only:
  can turn Supported or Contradicted into Unproven, never the reverse). Customer-facing claims
  unchanged: UFDR and AXIOM stay unverified. Next: a pilot examiner makes a UFDR from a public
  image and runs `ufdr-check`.

## 2026-10-15: Screen and report agree; reports are repeatable (#72)
- Changed: `tests/test_report_consistency.py` checks that the screen and the report agree on
  status, verdict label and evidence ids at 7 points in a synthetic case01 review. A repeatability
  test checks that the same inputs, versions and expert decisions give a byte-identical report
  with clocks pinned, and the same SHA-256 across times once the time fields documented in
  `core/report/html.py` are masked (8, including stipulation and identity-link times; Codex).
  Bug fixed: the verdict "decided" time came from the wall clock, not the run's clock; the
  pipeline and re-decide now stamp the run's clock. Report evidence rows carry evidence-id
  anchors. `core/audit/rules.py` unchanged. (Grok Product items 6 and 7.)
- Where: branch `claude/project-thread-kq0r95`, PR #72, not merged.
- Verified (as reported by the owning thread): ruff clean; 1862 tests pass, 1 fails (the known
  test #65 fixes); eval case01 1.00, 0 false supported, hostile PASS, case02 aggregate 0.90; no
  verdict changed.
- Open: synthetic case01 only, not real exports; does not compare every rendered sentence.
- Affects: customer-facing claims (supports "reproducible audit packet", on synthetic data with
  time fields masked). No privacy or performance change.

## 2026-10-15: Quote check reads contacts and calls as the model sees them (#76, fixes #69)
- Changed: the quote check (`core/audit/invariants.record_text`) now reads a contact
  ("Name: +1...") and a call ("outgoing Phone call from +1... to +1..., duration 84 s") exactly
  as retrieval shows them to the labeler (`core.enrich.records`), so correct quotes are no longer
  discarded. Why it matters: the check drops a label before its stance is used, so a dropped
  "contradicts" or "complicates" could let a claim with other accepted support go SUPPORTED.
  The report still shows a call's time beside its line. Evidence a run stored before #76 still
  passes the stored-quote re-check in the contact or call text of its day, so an older case
  re-decides; a run that records a quote-check version gets no such fallback (fails closed).
  The small model's generated contact rows follow the product too. The synthetic case01 affidavit PDF embeds DejaVu Sans for lines
  Helvetica can't draw ("Катя" read as boxes).
  Grok review on #80, item 3: the quote check now has a version. `core/audit/quotes.VERSION`
  1.1.0 -> 1.2.0 is stored in every audit run's config (a rules-only re-run carries its evidence
  run's; a run with another quote verifier, such as the eval's stand-ins, names it) and printed
  in the report beside the rule version; a test pins the check's answers to it, so a change
  without a bump fails. A quote now verifies only if it takes in a letter or digit of the
  record's own fields: at a word-aligned place in the pipeline, whatever verifier a run is
  given (`cites_record`), and at any place in the stored re-check
  (`core/audit/invariants.quote_is_verbatim`), which holds evidence to the check of its day only
  for a run that records no quote-check version (Grok merge-bot review on #76). "(no name)", "unknown" or "call from" alone fail; "(no name): +1..." passes. `core/audit/quotes.record_text`, which still said calls had no
  citable text, now reads every record as the labeler sees it, as the pipeline already did.
- Where: main once PR #76 merges (branch `claude/project-thread-01fybj`, from the "Audit our
  model scoring" thread). Includes the C17 font fix.
- Verified: new regression tests (each fails without its fix), among them a contact and a call
  labeled "contradicts" and quoted as shown: before, the label was dropped and C01 went
  SUPPORTED; now CONTRADICTED. A test checks every case01 record reads the same for the labeler
  and the check. A stored "call from" on a run recording 1.2.0 stops a re-run of the verdicts;
  the same case with no recorded version re-decides. A test checks that the claim page shows each
  call with the same UTC and printed time as the report (both use `record_line`).
  `make check` green on the branch with main at 79ad922 merged in (2045 passed, lint clean); `make eval` same as
  main (case01 1.00, 0 false supported; case02 aggregate 0.90); hostile run keeps 494 items and
  drops 4 labels (main 462 and 36), 0 supported. Offline, on stored answers: Opus case01 85% to
  95% (signed sheet), 60% to 70% (no sheet), 0 false supported; replayed through the new check,
  every Opus supports, contradicts and complicates label of the no-sheet run passes (108), and
  Sonnet and Haiku (2026-10-14) each lose 2, all on a message whose whole body is "?".
- Open: a label whose quote is not verbatim, has no letter or digit, or takes in only Baker's
  words or a placeholder is still dropped whatever its stance, and the report shows only a count
  of dropped labels. Runs from before #76 show "not recorded (1.1.0 or earlier)" for the quote
  check; re-running only their verdicts does not bring back labels the old check dropped, a
  full audit does (it reuses stored model answers). Generated call rows
  for the small model still print the report's time (signed guide rule 28), unlike the product;
  aligning them is for the "Custom model for Baker" thread. The guide's contact rows lack the
  colon (proposed for Arsh in PROPOSED_CHANGES.md); small-model run 5 trained on the old rows.
- Affects: capabilities (more correct evidence kept, for Opus and the 14B); closes, for contacts
  and calls, a path where a dropped "contradicts" or "complicates" let a claim go SUPPORTED.
  Report 0.3.0 -> 0.4.0 (`core/report/html.REPORT_VERSION`): a call's line shows its UTC and
  printed time, as on the review screen, and the versions show the quote check.
  No privacy, network, performance or customer-claim change.

## 2026-10-15: Stricter reading of stated time windows (#66, 9d24024)
- Changed: "after March 3" now starts on March 4 (it started on March 3, which could produce a
  false contradicted). Offsets like "two days after", and weekdays that don't match the date, are
  refused, so those claims stay unproven. Code: `core/audit/assumption_filler.py`.
- Where: main (merged 2026-10-15 07:22Z, `6b859fe`).
- Verified: new tests in `tests/test_assumption_filler.py`; all 3 Codex findings fixed (per the
  owning thread); CI green before merge.
- Open: the 0.2.2 bump (no rule logic change) is in PR #75 (Arsh approved it 2026-10-15).
  Verdicts decided under 0.2.1 can differ after this change.
- Affects: capabilities (which claims get a time window), verdicts on time-bound claims.

## 2026-10-15: Opus fails the signed probe; quote-check bug found (issue #69)
- Changed: nothing in the product yet. Opus re-run on the signed P001-P105 set: contradicts
  precision 73% (bar 90%) in both arms, every miss a told-frame or undated denial. A grading audit
  found the quote check renders contacts and calls differently from what the model is shown.
- Where: results in `/mnt/project-files/baker/cloud-bench/2026-10-15/` (RESULTS.md,
  GRADING_AUDIT.md); signed labels on main via #64; bug is on main, open
  as issue #69 (fix in PR #76).
- Verified: preregistered run ($5.21); blind readers 12/12 with the signed labels; offline replay
  shows the #69 fix lifts Opus case01 from 85% to 95%, 0 false supported.
- Open: a signed stance prompt line for told-frame and undated denials; the #69 fix; the local
  14B has not been run on the signed set; 3 answer-key labels and 1 guide gap flagged for Arsh.
- Affects: customer-facing claims (Opus no longer passes the full cloud rule), capabilities
  (#69 loses correct contact and call evidence for every model).

## 2026-10-15: Positioning narrowed; cloud is opt-in
- Changed: Arsh agreed to position Baker as a verification layer on Cellebrite and AXIOM for
  forensic examiners, and chose "Opt-in cloud" (07:10Z): local by default, cloud AI only when the
  case allows it and the expert opts in. PRODUCT_STATUS section 12 checks each claim in the line.
- Where: decision only; #68 still a draft.
- Verified: claims 1, 2, 5 true; 3 true for absence and count findings; 4 partly true; 6 depends
  on #68.
- Open: none.
- Affects: customer-facing claims.

## 2026-10-15: Process: Grok review PR and small model run 5
- Changed: every tenth PR (#70, #80, ...) is an empty Grok Product review PR, never merged.
  Small model run 5 (more varied training wording) started on branch #50.
- Where: #70 (draft); #50 (draft).
- Verified: nothing to measure yet.
- Open: run 5 results.
- Affects: none yet.

## 2026-10-15: Source-of-truth docs (this change)
- Changed: added `docs/PRODUCT_STATUS.md`, this log, and a CLAUDE.md rule to keep both current,
  so Grok Product and coding agents read one verified description of Baker.
- Where: PR #71 (branch `claude/project-thread-d7xp9z`, not merged). CLAUDE.md wording signed by
  Arsh ("approved", 2026-10-15 07:19Z).
- Verified: facts checked against main `7a14437`, open PR branches and recorded bench runs.
  Section 12 checks the six claims in the proposed positioning line, with file:line.
- Open: entries before 2026-10-13 are summarized by git only.
- Affects: none (documentation).

## 2026-10-15: Cloud stance labels gated on the signed stance test (#68)
- Changed: a case uses the cloud model only if that model passed the signed stance test with
  the current stance prompt (`PROBE_PASSED`, `core/llm/cloud.py`). The list ships empty, so every
  case labels locally on #68 for now. Reason: Codex P1 on #68 and the signed-set run (Opus
  contradicts precision 73%, bar 90%); an unreviewed "contradicts" on an event assumption can
  make a claim CONTRADICTED (rule 1b), and Arsh's earlier decision was cloud "after a check".
  Also from Codex round 6: nothing is logged as sent when the client cannot be built; a cloud
  answer that failed its quote or format check is asked again on re-run; a damaged sealed key
  reads as a config error; the "saved in this case" message checks the exact sealed path; the
  key is dropped from memory when a cloud audit ends; the Mac install guide no longer promises
  offline use for a cloud case.
- Where: branch `claude/project-thread-a2fjkc`, PR #68, draft, not merged.
- Verified: `make check` passes, 1940 tests; gates unchanged (case01 1.00, 0 false supported,
  unreviewed 0.60, hostile PASS, case02 0.90); new tests for the gate, preflight, re-ask and a
  damaged sealed key. No real API call.
- Codex on 82090a4 (fixed): a gate entry names the effort too, so an untested effort never passes;
  a client that cannot be built pauses the audit instead of dropping labels; the header pill
  follows a running cloud audit even if the key file changes; the Windows installer text says
  offline by default.
- Open: adding an entry needs a signed prompt fix, a recorded passing run on the signed set and
  on new held-out items not used to write the prompt, and Arsh's sign-off. The report already
  shows each set_cloud entry (expert, time, attestation text) in its audit-log table; a test now
  covers it.
- Affects: capabilities (cloud labels off until a model passes), privacy (no case data leaves
  the computer on #68 until then), customer-facing claims (do not offer cloud labeling yet).

## 2026-10-15: Cloud AI by per-case opt-in for stance labels (#68, 3c6c1ec)
- Changed: Baker is local by default. A case uses Opus 5.5 for stance labels only after the
  expert attests the protective order allows it, the case has no CSAM flag, and they supply their
  own Anthropic key. If the cloud fails mid-case, the audit pauses and the expert retries or
  re-runs the whole case locally, so models are never mixed within a case. Every request is
  written to the hash-chained audit log (`cloud.sent`) before it is sent. The endpoint is pinned
  to api.anthropic.com (120 s timeout, 2 retries). In an encrypted case, the key the expert saves
  is sealed under the case key (`case.cloud-key`, AES-256-GCM) and unreadable while the case is
  locked; a plain case keeps the owner-only `~/.baker/cloud.json`; the env var still wins.
  Claim proposal, assumption filling and the AI reviewer stay local. Reason: Arsh chose
  "Opt-in cloud" (2026-10-15 07:10Z).
- Where: branch `claude/project-thread-a2fjkc`, PR #68, draft, not merged (main merged in after #71).
- Verified (as reported by the owning thread; `cloud.sent` and the pause checked in
  `core/audit/_local_model.py` on the branch): `make check` passes, 1933 tests; gates unchanged
  (case01 1.00, 0 false supported, unreviewed 0.60, hostile PASS, case02 0.90); a simulated
  outage pauses the run with the chain intact; logged retries (each send logged, SDK retries
  off) and a log failure that blocks the send; an item relabeled by another model names the
  latest; sealed-key tests (sealed, unreadable once
  locked, refused in another case, env var and plain case unchanged); Codex rounds 1 to 4
  clean, later commits under review. No real API call since this change.
- Open: Opus fails the signed probe's contradicts bar (73%, entry below), so a signed prompt fix
  should land first; Arsh approved the revised CLAUDE.md wording (07:29Z), applied on the
  branch at his request (14:00Z); a fair 14B-vs-Opus
  test of claim proposal and assumption filling waits on Arsh; when a case switches models, an
  evidence row names the latest run's model and rationale (the earlier answer stays in
  model_calls); a key saved for a plain case stays an owner-only plain file.
- Affects: capabilities (optional cloud labels per case), privacy (only the filled stance prompt
  leaves the computer, and every request is logged), performance (about 3 s per stance call; local 22 to 43 s per call was
  measured 2026-10-09/12 on older code, and no full local case is timed on current code), customer-facing claims ("local by default; cloud AI only when your
  case allows it and you opt in"; never "no network calls" without that qualifier).

## 2026-10-15: Opus on claim proposal and assumption filling (eval only)
- Changed: nothing in the product. A preregistered check of moving two more steps to Opus.
- Where: `eval/bench/cloud_steps.py` on branch #68; results in
  `/mnt/project-files/baker/cloud-first/steps-check/RESULTS.md`.
- Verified: claim recall 80% (bar 90%); sheet-free audit 60% accuracy, 0 false supported (bar
  80%). Both failed, so both steps stay local.
- Open: the "Scoring audit" thread found most misses were grading artifacts
  (`/mnt/project-files/baker/cloud-bench/2026-10-15/GRADING_AUDIT.md`): all 4 claim misses, and
  60% becomes 70% with the contact quote fix (#76). The 14B has never been scored sheet-free, so
  "stay local" has no baseline. A fair 14B-vs-Opus sheet-free test after #76 waits on Arsh.
- Affects: performance (the 14B stays required).

## 2026-10-15: Opus 5.5 benchmark (eval only)
- Changed: nothing in the product. Probe and case01 runs for Opus at medium and high effort.
- Where: results in `/mnt/project-files/baker/cloud-bench/2026-10-14c/`.
- Verified: probe 27/27 supports, 0 wrong contradicts, 0 traps as support; case01 85%, 0 false
  supported. Cost $13.04.
- Open: only 8 gold contradicts; the signed probe follow-up is expected to cut contradicts
  precision until a prompt fix (not yet re-run).
- Affects: none until #68 merges.

## 2026-10-15: Fixes merged (#64, #65, #67)
- Changed: #65 fixes main's red test (test only). #67 fixes a flaky recovery-key test. (#66 has
  its own entry above.) #64 fixes the
  go-bar scorer and holds the probe follow-up proposal for guide v0.3.
- Where: main (merged 2026-10-15 07:21Z to 07:22Z). #65 fixes the v1.1 test that turned main red.
- Verified: CI green on each head.
- Open: none. The signed probe (105 items) is on main via #64.
- Affects: test or eval only.

## 2026-10-14: Prompt v1.1 with readable names, members line and the claim (#62, 53268d9)
- Changed: the 14B now reads people's names (from confirmed stipulations or identity links), a
  chat's members (capped at 20) and the claim for meaning, role and event assumptions. Reason:
  case01 ¶10.1 got a wrong "contradicts" from an id the model could not read.
- Where: main.
- Verified: model-free gate; v1.1 text pinned by digest. Not re-run on the Mac with the 14B.
- Open: Mac re-run of case01 to confirm ¶10.1; the AI reviewer still reads ids.
- Affects: capabilities.

## 2026-10-14: Probe scored as the product sees it (#63, 7a14437)
- Changed: the probe shows items in the product's layout; the scorer verifies quotes like the
  product. Reason: a grading audit found the probe input differed from the product's.
- Where: main. Combined with #62 it turned main's CI red (fixed on #65).
- Verified: re-scored runs in `/mnt/project-files/baker/cloud-bench/2026-10-14/`.
- Open: none beyond #65.
- Affects: benchmark numbers (earlier cloud scores are superseded).

## 2026-10-14: Stance data v0.3, signed (#59, 084a255)
- Changed: strict contradicts labels ("only when the record's own words rule the claim out"),
  Baker's own wording, 8 probe relabels (gold contradicts 16 to 8), new go bar.
- Where: main.
- Verified: blind label rounds; contamination check.
- Open: 5 disputed denials resolved by the signed follow-up, not yet applied (#64).
- Affects: benchmark numbers.

## 2026-10-14: Rules 0.2.1 (#53, af49c17)
- Changed: an unreviewed model "contradicts" cannot overrule a passing check; it only
  complicates. The sender is read from the claim.
- Where: main.
- Verified: model-free gate and rules tests.
- Open: none.
- Affects: verdicts (fewer false CONTRADICTED).

## 2026-10-14: New readers and analysis pages (#55, #56, #57, #58)
- Changed: AXIOM XML and Excel import (unverified); `baker ufdr-check`; Other explanations per
  claim; Windows code-signing path and clean-install tests.
- Where: main.
- Verified: synthetic tests, CI.
- Open: AXIOM and UFDR need real samples; installer signing needs Azure.
- Affects: capabilities, customer-facing claims (say "unverified" for AXIOM and UFDR).

## 2026-10-13: Review, identity, timeline, selection, encryption (#44 to #52)
- Changed: demo kit and Mac installer (#44); Identities page (#45); Timeline check and Gaps
  (#46); UFDR import, unverified (#47); cloud bench harness (#48); encryption at rest (#49);
  Selection audit (#52).
- Where: main.
- Verified: synthetic tests, CI, headless-Chromium UI checks.
- Open: real-data checks for UFDR.
- Affects: capabilities, privacy (encryption by default for new cases).

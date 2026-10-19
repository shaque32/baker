## 2026-10-19: Demo shows an inconclusive absence claim and, with `--paired`, the paired selection audit (#96)
- Changed: `baker demo` adds one demo-only absence claim, D01 ("PETROV and REYES exchanged no
  WhatsApp messages between March 20 and March 23, 2026", from paragraph 11; eval/demo_claims.jsonl,
  not in the signed answer key). No WhatsApp record falls in the window, but both phones are
  curated reports, so the absence check is inconclusive and the rules leave D01 unproven: the demo
  now shows Baker declining to treat "not found" as "did not happen". New `baker demo --paired`
  builds the same scripted case and then imports the synthetic UFDR of Item 1 from
  eval/synthetic/paired.py, so the Selection tab and claim pages show the paired selection audit
  (#78) in one command. The UFDR is imported after the audit, so verdicts match the plain demo.
  Why: Grok Product's two demo fixes; Arsh chose "Build both" (2026-10-19).
- Where: PR #96 (branch `claude/demo-inconclusive-and-paired-c0jsf7`)
- Verified: tests/test_demo.py (D01 unproven with an inconclusive absence check naming the
  curated reports; paired demo keeps every verdict, Selection tab lists the planted "or sunday
  works too", C05's page names 4 nearby records; CLI `--paired`); `make check` on this branch.
- Open: synthetic data only. The scripted demo queue now shows 21 claims (7 unproven, was 6).
  D01 is in the scripted build only: a demo saved with `--from-case` is restored as audited,
  with the 20 answer-key claims. A paired
  demo case cannot be saved as the demo with `--from-case` (its UFDR is not one of case01's
  reports). No signed file changed; no rules, prompt, schema or gold change.
- Affects: capabilities (demo only); no privacy, performance or customer-facing claims change.
- Status doc: pending: §8 item 5, change "`baker demo`" to "`baker demo` (with a demo-only
  inconclusive absence claim, and `--paired` for the paired selection audit)".

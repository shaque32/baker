## 2026-10-21: Site and one-pager format wording, "Built for scrutiny" section (#119)
- Changed: site/index.html and docs/ONE_PAGER.md now say the UFDR reader is tested on real-format
  Cellebrite UFDR exports from public test phones (Reader 7.48), and that
  other Cellebrite versions, Cellebrite Excel and AXIOM are not yet tested on real exports (Grok
  Product memo on #100). The site adds a "Built for scrutiny" section listing only built features:
  rules decide and the expert confirms, input hashes, hash-chained audit log, offline re-check
  bundle (#104), examiner activity trail off in reports by default (#111), local by default.
- Where: main (#119, merged 2026-10-24)
- Verified: wording checked against #117's description and PRODUCT_STATUS section 12; the UFDR
  result itself is unverified until Baker Eval re-runs the three Hickman packages and Arsh signs
  off gate 5. No accuracy or speed numbers added.
- Open: holds on #117, #104, #111 and Arsh's preview sign-off.
- Affects: customer-facing claims
- Status doc: applied 2026-10-27

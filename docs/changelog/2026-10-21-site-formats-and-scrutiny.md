## 2026-10-21: Site and one-pager format wording, "Built for scrutiny" section (#PR)
- Changed: site/index.html and docs/ONE_PAGER.md now say the UFDR reader is tested on real
  Cellebrite UFDR exports of public test phones (Digital Corpora Hickman images, Cellebrite Reader
  report 7.48), with message, call and contact counts matching Cellebrite's own report, and that
  other Cellebrite versions, Cellebrite Excel and AXIOM are not yet tested on real exports (Grok
  Product memo on #100). The site adds a "Built for scrutiny" section listing only built features:
  rules decide and the expert confirms, input hashes, hash-chained audit log, offline re-check
  bundle (#104), examiner activity trail off in reports by default (#111), local by default.
- Where: PR #PR
- Verified: wording checked against #117's description and PRODUCT_STATUS section 12; the UFDR
  result itself is unverified until Baker Eval re-runs the three Hickman packages and Arsh signs
  off gate 5. No accuracy or speed numbers added.
- Open: holds on #117, #104, #111 and Arsh's preview sign-off.
- Affects: customer-facing claims
- Status doc: pending: section 12, replace "and that UFDR or AXIOM imports are verified" with
  "that UFDR imports are verified beyond Cellebrite Reader 7.48 exports of public test phones, or
  that Cellebrite Excel or AXIOM imports are tested on real exports"; add a row: "UFDR counts
  match Cellebrite's report on Reader 7.48 public test phones | True after #117 and gate 5 sign-off
  | #117, Baker Eval re-run | Tested on real Cellebrite UFDR exports of public test phones (Reader
  report 7.48); other versions not yet tested".

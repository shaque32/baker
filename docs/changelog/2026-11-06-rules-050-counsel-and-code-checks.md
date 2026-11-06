## 2026-11-06: rules 0.5.0, supported by code checks (option C) and counsel review (option B) (#228)
- Changed: Arsh signed options B and C of the AI-native forensic checker plan on 2026-11-06
  (the signed diffs are in `PROPOSED_CHANGES.md`; plan at
  `/mnt/project-files/baker/plans/confirm-rule-b-c.md`). Contracts and schema go to 0.8.0 and rules
  to 0.5.0.
  - C, rule 3c': a communication, timing or count claim is SUPPORTED with the new basis
    `checked`, shown as "Supported by the records (code checks)", when every core assumption
    passed all its deterministic checks, at least one passing check names the records it rests on,
    and nothing blocks under rules 3d and 3e. It cites checks and stipulations, never evidence. It
    uses no model label and no reviewer. Content meaning, identity, role and absence claims never
    take this path.
  - Exact counts stay with the expert: rule 3c' does not apply when a core assumption is an
    "exactly N" count. The count check (unchanged, 1.2.0) passes one on a curated report that may
    omit records (found by the Greptile review on #228). Making the check inconclusive instead
    would have contradicted the signed assumption sheets of case01, case03, case04, case05 and
    case06, which expect it to pass. The other checks were audited for the same gap. Sender,
    time, weekday and contact pass only on records that are present; "at most" counts and
    absence already need a full extraction; "at least" counts hold on any report. The
    same-account check can still pass on a curated report that omits a second account with the
    same name (see Open).
  - B: new review kind `counsel` (`counsel:<name>`), status `counsel_accepted`, tier
    `counsel_reviewed` and basis `counsel_reviewed`, shown as "Supported (reviewed by counsel)".
    It never displays or exports as confirmed. A contradiction counsel accepted counts under rule
    1b, and its reason says "accepted by counsel, not an expert". Counsel cannot dismiss items.
    The basis order is confirmed, then checked, then counsel_reviewed, then ai_reviewed.
  - The invariants re-check a checked SUPPORTED on their own terms: the claim type, cited checks
    that all passed, no cited evidence, at least one cited record, and every check on every core
    assumption passed. They also refuse a counsel review row after an expert's.
  - Screen, report (0.38.0) and plain "why" lines show the two new labels, and the report defines
    them in Limitations. The demo's live claim C05 now opens as "Supported by the records (code
    checks)", and the expert's acceptance turns it expert-confirmed. `docs/demo.md` says so.
  - A case made under schema 0.7.0 keeps the old `verdicts` CHECK, which refuses the new bases
    (found by the Greptile review on #228). `core/db.py` `upgrade_verdicts()` now rebuilds that
    one table to the 0.8.0 definition, every row and column kept, before an audit or a verdict
    re-run writes to it. Nothing else references `verdicts`, so the copy is safe.
- Where: PR #228
- Verified: `make check` (lint, tests, eval) on this branch, run 2026-11-06 in a Linux x86_64
  cloud container (4 vCPU, Python 3.13.18, no GPU). `make eval` there is model-free: no model
  runs, gold assumption sheets, scripted labels and the simulated expert, so these numbers do
  not depend on the hardware. They are synthetic only. Synthetic case01 unreviewed: accuracy 0.55 to 0.70, with C05, C09 and C12
  supported (checked), all gold-supported, and 0 false supported. After the simulated expert:
  1.00 and 0 false supported, unchanged. `make eval-hostile`: none of 7 structural and 0 of 5
  model-only claims supported. case02 aggregate as `make eval` printed it is in the PR
  description. New tests in `tests/contract/test_rules_050.py` and
  `tests/contract/test_upgrade_verdicts.py`.
- Open: B's actor is not wired yet. Nothing in the app or CLI writes a counsel review, so the
  counsel paths are reachable only from tests until the follow-up PR (counsel actor in
  `core/review/actions.py` that refuses to overwrite an expert review, activity trail, flags,
  bundle verify of `counsel:` rows, and the reviewer role at case setup). C's 0 false supported
  holds only on synthetic data with signed assumption sheets. It is unmeasured on filler-made
  assumptions and on real exports. Residual gap: the same-account check can pass on a curated
  report that leaves out a second account with the same name. Cases made under schema 0.7.0
  store checked verdicts after the upgrade above, but their `evidence_reviews` table still
  cannot store counsel reviews. It is append-only with triggers, so its upgrade is left to the B
  follow-up PR that first writes one.
- Affects: capabilities, customer-facing claims (a claim can now be supported with no expert's
  acceptance, by code checks; "nothing is supported until an expert accepts it" is no longer true)
- Status doc: pending: header: rule version 0.5.0, contracts 0.8.0 (#228). Section 4, "Opus's
  influence on verdicts": a "supports" label never makes a claim SUPPORTED by itself; an expert or
  counsel must accept it, or code checks alone carry a communication, timing or count claim with
  no label used. Section 6 table, SUPPORTED row: add "or, for communication, timing and count
  claims, every core assumption passed all its checks and one cites records (basis checked, no
  label, no reviewer)", and "expert- or counsel-accepted support". Under the table, replace "so
  every SUPPORTED verdict is expert-confirmed" with "a SUPPORTED verdict is expert-confirmed,
  supported by the records (code checks), or reviewed by counsel; the last two never display as
  confirmed". Display tiers: add counsel_reviewed. Section 12 claim 2, "Nothing is Supported until
  the expert accepts it": mark it no longer true and say that code checks alone can support
  communication, timing and count claims (rule 3c'), and that counsel review gives "Supported
  (reviewed by counsel)". Section 9: add the same-account gap on curated reports.

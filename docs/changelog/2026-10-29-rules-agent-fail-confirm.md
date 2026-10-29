## 2026-10-29: Rules 0.4.0: a failed check on an agent's assumption waits for the expert's confirm
- Changed: Arsh's choice on 2026-10-28 (23:52Z) to guard against a wrong Contradicted before the
  testability agent goes on for pilots: "Rules change first, then measure". Under rules 0.3.0 a
  failed deterministic check contradicts a claim with no further review, so an examiner who
  accepts an agent's proposal naming a wrong phone or time window could turn a true claim
  Contradicted. Under rules 0.4.0 (`core/audit/rules.py`, Arsh's file: he signed the diff in
  `PROPOSED_CHANGES.md` on 2026-10-29 and applied it himself in 75ea6eb) such a failure counts
  only once an expert confirms it, the same way a model's "contradicts" already does. Until
  then the claim stays Unproven and says "Contradiction found, confirm to finalize".
  - `decide_verdict` gains two keyword-only arguments, empty by default, so every call that
    passes neither decides as 0.3.0 did: `agent_proposed` (the claim's assumptions the audit
    took from the testability step under an expert's acceptance) and `confirmed_fails` (failed
    checks an expert confirmed exactly as they failed). The audit, the verdict re-run and
    verify-bundle compute both with `testability.verdict_inputs`. No contracts change.
  - A confirm (`testability.confirm`, under the expert's actor, with a reason) holds for that
    failure only: the same claim text, proposal and check result, hashed. If a later audit's
    check fails another way, it waits again. A rejection of the proposal logged after a confirm
    undoes it, and the next audit does not use the proposal. If that rejection comes after the
    verdicts already counted the confirm (a stale tab), the claim says the verdicts are not
    current and asks for a re-run (Codex).
  - A waiting failure no longer settles the claim (`pipeline.settled_by_check`): its evidence is
    labeled, since an accepted contradicting item could still decide it.
  - The claim page shows a card for each waiting failure, with the check's detail and what it
    searched, a reason field and "Confirm this failure", plus "Or reject the agent's proposal".
    There is no confirm-all. A confirm re-runs the verdicts at once, as the evidence confirm
    does. `actions.confirm_agent_fail` refuses a non-expert, an empty reason and a failure the
    audit on screen does not show as waiting. It also refuses a failure other than the one the
    page showed: the form carries a hash of the shown result, its proposal and the claim text,
    so a page left open across a later audit whose check failed another way, or across a claim
    edit, confirms nothing (Codex, twice).
  - The overview, the claim page and report 0.26.0 give the step to confirm it (numbered 0.24.0
    until #167's 0.25.0 merged first; no report was released as 0.24.0). The report's key
    to the verdicts says such a failure counts once an expert confirms it. `verify-bundle`
    re-applies the rules with the same inputs, read at each verdict's log position, and fails a
    confirm that is not an expert's.
  - `docs/METHODS.md` names rules 0.4.0 and the new wait.
- Where: PR #166, branch `claude/project-thread-6i2msb-agent-fail-confirm`
- Verified: `make check` passes with Arsh's applied rules (75ea6eb and after); its eval numbers
  are in the PR. Under rules 0.3.0 the 21 new tests fail, as they should. New tests:
  - `tests/contract/test_rules.py`: a waiting failure keeps the claim unproven with the rule 1a
    reason and no citation; a confirmed one contradicts and cites the check; without the new
    arguments a failed check contradicts as in 0.3.0; a confirm or an agent id that belongs
    elsewhere changes nothing; a waiting failure blocks supported while another failed check
    still contradicts; a failure on an agent's context assumption blocks supported as before;
    the version is 0.4.0.
  - `tests/test_fewer_calls.py`: an agent's failed check settles nothing until confirmed, and
    once confirmed the real rules keep the claim contradicted whatever the evidence, for every
    claim type.
  - `tests/test_agent_fail_confirm.py` (synthetic case01, scripted models; the contact check is
    made to fail on C01's accepted proposal): the claim waits with the step on the screen and in
    the report and its evidence is labeled; a confirm is refused for a non-expert, an empty
    reason or an unknown check, changes nothing until the verdicts re-run, and then the claim is
    contradicted citing the check; a later rejection undoes the confirm and the next audit leaves
    the claim untested; a rejection after the verdicts counted a confirm marks them not current,
    and one with no confirm to undo does not; a confirm from a page that showed an earlier
    failure of the same check is refused, on the page too, and so is one from a page shown
    before a claim edit after which the check fails the same way; a confirm carries to a later
    audit only while the check fails the same way; verify-bundle passes each run and fails a
    forged non-expert confirm; the claim page shows one confirm per failure and a reject, and a
    posted confirm re-runs the verdicts.
- Open: the Mac go/no-go still reports how often an accepted proposal fails a check on a true
  claim (now a confirm the expert must decide, not a verdict). The demo has no claim whose
  agent proposal fails a check; a demo claim for it is a possible follow-up. PR 3 (the agent on
  for pilots) still needs CAP, X, Y, a held-out signed synthetic set, the Mac run and Arsh's
  re-signed CLAUDE.md line.
- Affects: verdict path (rule 1a, rules 0.4.0, only for assumptions the testability agent
  proposed; the agent stays off by default), capabilities (the confirm card), customer-facing
  claims (`docs/METHODS.md`). No privacy, network or model change.
- Status doc: pending: section "11. Verdict" row: "applies rules 0.3.0" becomes "applies rules
  0.4.0 (#<this PR>)". The outcome table's heading "(rules 0.3.0)" becomes "(rules 0.4.0)", and
  its Contradicted row adds: "a failed check on an assumption the testability agent proposed
  counts once the expert confirms it". Section 8 item 2 ("Audit"), after #163's pending line:
  "A failed check on an assumption the agent proposed waits for the expert's confirm (rules
  0.4.0)".

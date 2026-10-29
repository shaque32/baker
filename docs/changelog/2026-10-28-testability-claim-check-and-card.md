## 2026-10-28: Testability agent: claim-only check, the examiner's card, and the demo's D02 and D03 (#163)
- Changed: PR 2 of `plans/agents-on-by-default.md`, after Arsh's choice on 2026-10-28 (07:50Z)
  to build the claim-only check and the accept card now, and Arsh's ask that the agents' work be
  featured in the demo. The step stays off by default: the review screen's audit and `mabillon
  audit` never turn it on. Only the eval and the scripted demo build (`eval/demo.py`) do.
  - Claim-only check (`testability.outside_claim`, step 0.2.0): every person, phone and account
    a repair names must be one code's lookups find in the claim's own text, not its paragraph,
    and every handle must be written there. The filler's own checks already read apps, quoted
    words, durations and time ranges from the claim's text. A try that names anything else is
    rejected whole ("outside"). This is the whole check on a case without a signed sheet. In the
    eval it runs first, then the signed sheet's check as before. The eval's wrong-entity rate is
    now the share of tries that passed the filler's checks and the claim-only check that the
    sheet then rejected: how often the claim's words alone would let a wrong one through. Until
    the go/no-go fixes one definition, the eval also reports #159's rate on the same tries (of
    the tries that passed the filler's checks, the share the sheet rejects, an "outside" try
    counted by what the sheet says of its names), and counts "outside" tries. It is stricter
    than the filler: a name only the paragraph writes is refused here.
  - The examiner's card: on an untested claim with a proposal from the audit on screen, the
    claim page shows "Proposed by agent", the proposed assumptions, what code checked and code's
    lookups, a reason field, and Accept or Reject. There is one card per claim and no accept-all.
    `actions.decide_repair` logs `testability.accept` or `testability.reject` under the
    expert's actor, with the reason. It refuses a non-expert, an empty reason, a proposal not in
    the log, and a claim whose text changed after the proposal. Nothing is used then. The next
    audit uses an acceptance when the step gives the same assumptions again for the same claim
    text. An expert's latest decision stands, and a rejection keeps the proposal out. The
    overview lists such a claim as waiting on the expert ("Proposed by agent: ..."). "What has
    to be true" marks an accepted assumption "Proposed by agent, accepted by examiner (<name>)",
    as the report does. Both read one function (`testability.used_repairs`), for the audit
    shown only: the proposals that audit used under an expert's acceptance in force then, the
    same rule verify-bundle checks. A rejection or a claim edit after that audit is said beside
    the mark ("later rejected by <name>, so the next audit does not use it"); the next audit
    then shows no mark. Another audit's acceptance, or an assumption the filler made itself,
    is never marked. Before, the mark read every acceptance ever logged (Grok Product).
  - Each `testability.repair` entry now records which checks ran (`check`) and the proposed
    assumptions with their texts (`proposed`), which is what the card shows. `verify-bundle`
    re-runs both and fails a decision by a non-expert. A kept proposal must have an expert's
    acceptance as its latest decision when the audit used it (the step's own rule), so an
    acceptance a later rejection overrode fails, and a rejection after the audit does not. Each
    try re-runs on the claim as it stood, rebuilt from any later claim edit's log entry and
    checked against the try's hash; a row the log does not explain fails.
  - Demo: two demo claims outside the signed key (`eval/demo_agent_claims.jsonl`). The product's
    filler and testability step run on them with their signed prompts. Only the answers are
    scripted: a first answer code refuses for a refusal kind run 2 saw, then the agent's answer,
    which passes. The step has no sheet (the claim-only check, as a real case) and CAP 1.
    - D02 ("Item 1 holds a contact saved as "Alex" with the number +1 (212) 555-0182"): the
      first answer writes the phone as an account. The agent's proposal was accepted in the
      build by "Demo examiner (scripted from the demo claims)", with its contact record.
      Code's contact check passed, and D02 is "Supported (expert-confirmed)".
    - D03 ("At about 7:58 p.m. on March 9, 2026, Item 1 placed a call to +1 (212) 555-0122"):
      the first answer names a call with no party. The agent's proposal waits on its page, and
      D03 is "Next up" on the claims queue.
    - The demo's queue is now 23 claims: 8 supported, 6 contradicted, 9 unproven.
      `docs/demo.md` gains step 5 (the presenter accepts D03's proposal, then opens D02) and
      says that the answers are scripted and the checks are real. Report 0.23.0: the demo
      banner, on every page and in the report, says so too when the demo's audit ran the step:
      the agent's answers and the examiner who accepted one were scripted, and its work there
      is not evidence of how often the agent is right.
  - Merges #162 into this branch (challenge step on by default), so it merges after #159 and
    #162 (#149 is on main). Report 0.23.0 follows #162's 0.22.0.
- Where: branch `claude/project-thread-6i2msb-testability-accept` (PR #163)
- Verified: `make check` passes; its eval numbers are in the PR. New tests:
  - `tests/test_testability.py`:
    - the claim-only check counts what the claim's own words name (a person only the paragraph
      names, another phone, a handle and an account the claim does not write are refused);
    - a repair naming a person only the paragraph names is "outside" in both modes, before the
      sheet (which names that person) is read;
    - without a sheet the step proposes, logs the proposed texts and uses nothing;
    - through the audit: a proposal waits for the examiner, `decide_repair` refuses a
      non-expert, an empty reason and an unknown try, an acceptance changes nothing until the
      next audit, which uses it with no new acceptance entry, and the report marks it;
      verify-bundle passes;
    - a rejection after an acceptance keeps the proposal out of the next audit;
    - a claim whose text changed cannot be accepted;
    - verify-bundle fails a kept proposal whose latest decision before the audit was a
      rejection, and passes one rejected after the audit;
    - verify-bundle re-runs the tries of a claim edited after the audit on its audited text, and
      fails a claim row changed with no log entry;
    - the agent mark on the claim page and in the report follows the decision the shown audit
      used: none before the audit uses an acceptance, the mark once it does, a later rejection
      said beside it, none on the next audit or on an audit without the step; an acceptance
      does not carry over to an edited claim;
    - the claim page shows one card with one accept and one reject and no accept-all, and
      posting an acceptance logs it under the examiner with the reason.
  - `tests/test_demo.py`:
    - D02's proposal was accepted, used and reaches supported, and is marked on the screen and
      in the report;
    - the presenter accepts D03 on its card, nothing changes until the next audit, and that
      audit tests D03 with the accepted assumption;
    - the queue, counts and "Next up" follow the new claims;
    - the demo banner names the scripted agent answers on the screen and in the report.
  - `tests/test_testability.py` also checks that the eval reports both wrong-entity rates on
    the same tries.
- Open: the step's effect with the local model is unmeasured. The go/no-go needs the 14B on the
  Mac, a held-out synthetic set and Arsh's X, Y and CAP. CAP has no default, and the demo uses
  1. Turning the step on for pilots is PR 3 of the plan. Arsh re-signs the CLAUDE.md line for
  it. Arsh signed this PR's wording change to that line, which names the scripted demo
  (`PROPOSED_CHANGES.md`, 2026-10-28 13:17Z), and applied it in 2aded2d. The sharper risk on a
  real case stays a false Contradicted: an accepted wrong window or phone can fail a
  deterministic check (rules 0.3.0). The claim-only check narrows that, and the sheet check
  measures it, but neither removes it. Arsh chose (2026-10-28 23:52Z) a rules change for it
  first, in its own PR: a failed check on an agent-proposed assumption counts only once the
  expert confirms it.
- Affects: capabilities (the testability agent's claim-only check and the examiner's card; still
  off by default), customer-facing demo (D02 and D03)
- Status doc: pending: section 8 item 2 ("Audit"): after #159's pending line on the testability
  step, add "With no signed sheet the step checks each try against the claim's own words (every
  person, phone and account one the claim's text names), and the claim page shows the try as
  "Proposed by agent" for the examiner to accept or reject; only an acceptance is used, from
  the next audit on. Off by default; only the eval and the scripted demo turn it on (#163)".
  Section 7 (demo), if it lists the demo's claims: add D02 and D03 as the agent's demo claims,
  with scripted answers.

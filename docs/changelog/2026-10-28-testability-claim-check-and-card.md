## 2026-10-28: Testability agent: claim-only check, the examiner's card, and the demo's D02 and D03 (branch to follow)
- Changed: PR 2 of `plans/agents-on-by-default.md`, after Arsh's choice on 2026-10-28 (07:50Z)
  to build the claim-only check and the accept card now, and his ask that the agents' work be
  featured in the demo. The step stays off by default: the review screen's audit and `mabillon
  audit` never turn it on. Only the eval and the scripted demo build (`eval/demo.py`) do.
  - Claim-only check (`testability.outside_claim`, step 0.2.0): every person, phone and account
    a repair names must be one code's lookups find in the claim's own text, not its paragraph,
    and every handle must be written there. The filler's own checks already read apps, quoted
    words, durations and time ranges from the claim's text. A try that names anything else is
    rejected whole ("outside"). This is the whole check on a case without a signed sheet. In the
    eval it runs first, then the signed sheet's check as before. The eval's wrong-entity rate is
    now the share of tries that passed the filler's checks and the claim-only check that the
    sheet then rejected: how often the claim's words alone would let a wrong one through. The
    eval also counts "outside" tries. It is stricter than the filler: a name only the paragraph
    writes is refused here.
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
    as the report does.
  - Each `testability.repair` entry now records which checks ran (`check`) and the proposed
    assumptions with their texts (`proposed`), which is what the card shows. `verify-bundle`
    re-runs both and fails a decision by a non-expert.
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
      says that the answers are scripted and the checks are real.
  - Merges #162 into this branch (challenge step on by default), so it merges after #149, #159
    and #162. The report version stays 0.22.0: the report's mark is #159's.
- Where: branch `claude/project-thread-6i2msb-testability-accept` (PR to follow)
- Verified: `make check` passes; its eval numbers are in the PR. New tests:
  - `tests/test_testability.py`:
    - the claim-only check counts what the claim's own words name (a person only the paragraph
      names, another phone, a handle and an account the claim does not write are refused);
    - a repair naming a person only the paragraph names is "outside" in both modes, before the
      sheet (which names him) is read;
    - without a sheet the step proposes, logs the proposed texts and uses nothing;
    - through the audit: a proposal waits for the examiner, `decide_repair` refuses a
      non-expert, an empty reason and an unknown try, an acceptance changes nothing until the
      next audit, which uses it with no new acceptance entry, and the report marks it;
      verify-bundle passes;
    - a rejection after an acceptance keeps the proposal out of the next audit;
    - a claim whose text changed cannot be accepted;
    - the claim page shows one card with one accept and one reject and no accept-all, and
      posting an acceptance logs it under the examiner with the reason.
  - `tests/test_demo.py`:
    - D02's proposal was accepted, used and reaches supported, and is marked on the screen and
      in the report;
    - the presenter accepts D03 on its card, nothing changes until the next audit, and that
      audit tests D03 with the accepted assumption;
    - the queue, counts and "Next up" follow the new claims.
- Open: the step's effect with the local model is unmeasured. The go/no-go needs the 14B on the
  Mac, a held-out synthetic set and Arsh's X, Y and CAP. CAP has no default, and the demo uses
  1. Turning the step on for pilots is PR 3 of the plan. Arsh re-signs the CLAUDE.md line for
  it. This PR also proposes a wording change to that line (`PROPOSED_CHANGES.md`) so it names
  the scripted demo. The sharper risk on a real case stays a false Contradicted: an accepted
  wrong window or phone can fail a deterministic check (rules 0.3.0). The claim-only check
  narrows that, and the sheet check measures it, but neither removes it.
- Affects: capabilities (the testability agent's claim-only check and the examiner's card; still
  off by default), customer-facing demo (D02 and D03)
- Status doc: pending: section 8 item 2 ("Audit"): after #159's pending line on the testability
  step, add "With no signed sheet the step checks each try against the claim's own words (every
  person, phone and account one the claim's text names), and the claim page shows the try as
  "Proposed by agent" for the examiner to accept or reject; only an acceptance is used, from
  the next audit on. Off by default; only the eval and the scripted demo turn it on (#N)".
  Section 7 (demo), if it lists the demo's claims: add D02 and D03 as the agent's demo claims,
  with scripted answers.

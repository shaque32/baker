## 2026-10-20: Opus 5.5 at medium passes the cloud gate with the cloud prompt (#101)
- Changed: `core/llm/cloud.PROBE_PASSED` lists one entry, (claude-opus-5-5, medium,
  `sha256:2863d8dbf66960f6`): Opus 5.5 at medium effort with the cloud stance prompt, stance
  v1.2 (`core/audit/prompts/stance_cloud.md`, #93). Arsh signed the entry on 2026-10-20 ("Sign
  the entry", 00:39Z, "Audit our model scoring"). Why: it is the last lock on #68's opt-in cloud
  labels, and Opus met the signed bars with v1.2 on the signed set and on new held-out items. A
  case uses Opus only when an expert attested for that case that its protective order allows
  cloud AI, the case is not marked as possibly containing CSAM, and the expert's own key is set
  up; otherwise the local 14B labels it, as before. The entry is tied to the cloud prompt's
  version, so any change to that prompt turns cloud off again until it passes and is signed.
  Another effort or model still labels locally. `ClaudeModel.generate_json` now also refuses an
  answer whose `model` field is not the model it asked for (a sticky failure, so the audit
  pauses): `claude-opus-5-5` is a pinned snapshot (Anthropic's models overview), so this guards
  against mixed labels rather than a known path (Codex on #101). `docs/SECURITY_PRIVACY.md`
  (the opening, the data-flow diagram and table, cloud policy item 4, the network check),
  `docs/install-mac.md`, `docs/PILOT_ONBOARDING.md` (with the Internet row: an opted-in case
  needs internet while it is audited), `docs/PILOT_GATES.md` (gate 8) and `docs/ARCHITECTURE.md`
  say so.
- Where: PR #101 (branch `claude/project-thread-01fybj`), not merged.
- Verified: the evidence is the preregistered runs of 2026-10-15
  (`/mnt/project-files/baker/cloud-bench/2026-10-15/told-frame-line/RESULTS-medium.md`, $4.52 of
  API spend, synthetic data only): on the signed set (95 gated items) contradicts precision 10/10
  (Wilson 95% 0.722-1.0), supports recall 33/33 (0.896-1.0), nothing contradicting shown as
  supports, contradicts recall 10/11 (misses P065); on this thread's 24 new items, at medium,
  no wrong contradicts and every scored control kept (22 scored; the same items without v1.2's two
  sentences ran only at high, where 2 were wrong). T022 and T023, both supports controls, are
  not scored, under a rule written before any call: blind readers disagreed with their draft
  labels. Opus still answered them (T022 complicates, T023 supports), and both rows are in the
  results file. On 26 fresh items from "Custom model for Baker", at medium, no wrong
  contradicts, contradicts recall 8/8, supports recall 4/4. Every item's gold label and both
  answers, for all three sets: `eval/probe/results/2026-10-15-opus-5-5-medium-stance-v1-2.jsonl`
  (item ids and labels only, no item text; the new items' labels are drafts, not signed).
  Tests: the shipped list is exactly this entry and
  matches the cloud prompt's version, an attested case uses Opus at medium but not at high, and
  an answer naming another model, or none, pauses the run. One API call on 2026-10-20 (18 input
  and 4 output tokens) showed the API names `claude-opus-5-5` as the answering model.
  `make check` in the PR description. No new model run.
- Open: the case01 audit with the signed assumption sheet was not run again with v1.2 (with
  v1.1: 85% accuracy, 0 false supported, 2026-10-15); the 14B-vs-Opus test's case01 audit
  without the sheet labeled with v1.2 (70%, 0 false supported, 2026-10-16; its stance run
  records `sha256:2863d8dbf66960f6`). Opus misses one real contradiction (P065), which leaves a
  claim UNPROVEN.
  Under rules 0.3.0 (#98) an Opus "contradicts" counts only once the expert confirms it, so a
  wrong one costs the expert a look, not a verdict.
  Real protective orders, the expert's key handling and the API's retention terms are the
  expert's to check per case; not legal advice.
- Affects: capabilities (opted-in cases can be labeled by Opus 5.5); privacy and network use
  (for an opted-in case only, the filled-in stance prompt goes to the Anthropic API, one request
  per stance pair, each logged before it is sent); customer-facing claims ("local by default;
  cloud AI only when your case allows it and you opt in" stays true; "no case can use cloud" is
  no longer true). No change for a case that is not opted in.
- Status doc: pending: section 2, row 8: replace "opt-in per case once it passes the signed stance
  test (#68, on main; none has: `core/llm/cloud.py` `PROBE_PASSED` is empty)" with "opt-in per
  case (#68); `PROBE_PASSED` lists Opus 5.5 at medium effort with the cloud prompt, stance v1.2
  (signed 2026-10-20, #101)". Section 3: in the Qwen3-14B row replace "(every case, until a
  cloud model passes the signed stance test)" with "(every case not opted in to cloud)"; in the
  Opus row replace "once it passes the signed stance test (not yet: `PROBE_PASSED` is empty)"
  with "with the cloud prompt, stance v1.2 (`PROBE_PASSED`, signed 2026-10-20)" and its status
  "main (#68, merged 2026-10-15), gated off" with "main (#68; entry #101)". Section 4, "When
  Opus is used": replace the sentences on `PROBE_PASSED` being empty (and #93's sentence on an
  entry still to sign) with "That list holds one entry: Opus 5.5 at medium effort with the cloud
  prompt (signed by Arsh 2026-10-20, #101). Another model or effort labels locally."; "Merge
  state": replace "`PROBE_PASSED` is empty, so no case can use the cloud yet." with
  "`PROBE_PASSED` lists Opus 5.5 at medium (#101), so a case the expert opts in uses it."
  Section 5: replace "while cloud is gated off (below), `core/` makes no network calls." with
  "`core/` makes no network calls except for a case the expert opted in to cloud AI (below)."
  and "**#68 (on main, gated off):**" with "**#68 (on main; used for opted-in cases since
  #101):**". Section 11, "Before a first real case" item 3: replace the item with "Opt-in
  cloud (#68) is available for a case whose protective order allows it: `PROBE_PASSED` lists
  Opus 5.5 at medium (#101, signed 2026-10-20)." Section 12, row 6: replace "**True today;
  #68 merged, gated off**" with "**True for every case not opted in to cloud**", "main: true
  while `PROBE_PASSED` is empty." with "main: true for every case not opted in; `PROBE_PASSED`
  lists Opus 5.5 at medium (#101).", "gated off until a model passes the signed stance test"
  with "used only for a case the expert opts in", and drop "; today no case can use cloud".

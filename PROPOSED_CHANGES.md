# Proposed changes to frozen files

Agents write here instead of editing `core/contracts.py`, `core/schema.sql`,
`core/audit/rules.py`, prompts or gold data. A human reviews each entry and applies it on `main`.

Format for each entry:

```
## <date> <branch>: <one-line summary>
File: <frozen file>
Why: <what you could not do without it>
Diff:
<exact change>
```

## 2026-10-06 claude/synthetic-case-rlcgrj: point case01 at the generated files
File: eval/gold/case01/README.md, eval/gold/case01/case.json, eval/gold/case01/affidavit.md
Why: the generator cannot write into eval/gold/ (frozen), so its outputs live in
eval/synthetic/case01/. The README still says reports go in eval/gold/case01/sources/, and
case.json and affidavit.md are stubs.
Diff:
1. Once Arsh has reviewed them, copy the generated files over the stubs:
   cp eval/synthetic/case01/case.json eval/gold/case01/case.json
   cp eval/synthetic/case01/affidavit_draft.md eval/gold/case01/affidavit.md
2. Copy only the approved lines of eval/synthetic/case01/draft_gold.jsonl into
   eval/gold/case01/gold.jsonl, with labeled_by and labeled_at set to the approver and date.
3. In eval/gold/case01/README.md:
-| `sources/` | generator | Synthetic extraction reports to import (Cellebrite-style Excel/PDF, later UFDR) |
+| `../../synthetic/case01/` | generator | Synthetic extraction reports (`make synth` rebuilds `item1.xlsx`, `item2.xlsx`; `case.json` pins their SHA-256) |
-The eval goes through an importer: the generator emits report files in `sources/`, and the
+The eval goes through an importer: the generator emits report files in `eval/synthetic/case01/`, and the

## 2026-10-13 claude/project-thread-czwpc8: relabel 8 signed probe items under strict contradicts
File: eval/gold/probe/probe.jsonl (through eval/probe_draft/items.py and probe_draft.jsonl),
eval/probe_draft/model.py (`SIGNED_LABEL`), tests/test_gold_probe.py
Why: on 2026-10-13 Arsh chose "Strict everywhere" in the "Custom model for Baker" thread:
contradicts only when the record's own words rule the assumption out (stance guide draft v0.3,
rules 22 and 23). These 8 items are contradicts only under the old rule, so until they change
the probe set and the v0.3 training data disagree. Applied only after Arsh signs this list.
Diff (eval/probe_draft/items.py; quotes, records and context stay as they are):
- P038: S.CONTRADICTS -> S.COMPLICATES. Rationale: "Gabe says he paid Ruiz 2k, but three
  minutes later he corrects it: '1.2k not 2k. rest next week'. That later message, not this
  record, rules out $2,000."
- P039: S.CONTRADICTS -> S.COMPLICATES. Rationale: "This record sets Friday; the next morning
  Тимур moves it to Saturday ('нет, давай в субботу, в пятницу не могу') and the owner confirms.
  That later message, not this record, shows Friday was not the final plan."
- P040: S.CONTRADICTS -> S.COMPLICATES. Rationale: "'its done' here came from the owner's own
  number +12125550111, not +12125550122; the record does not show whether +12125550122 also
  sent those words."
- P041: S.CONTRADICTS -> S.COMPLICATES. Rationale: "The volunteer here is +17185550172 (Nadia),
  not +17185550181 (Kofi), who asked; the record does not show whether +17185550181 also said
  it."
- P042: S.CONTRADICTS -> S.COMPLICATES. Rationale: "The same words went to the same user at
  8:03 PM EDT on March 12 local time, not on March 13; the record does not show whether a
  matching message was also sent on March 13."
- P043: S.CONTRADICTS -> S.COMPLICATES. Rationale: "DST edge: the local clock read 3:05 AM EDT
  when Rina sent this, after 3 a.m.; the record does not show whether she also texted that she
  was home before 3 a.m."
- P044: S.CONTRADICTS -> S.COMPLICATES. Rationale: "DST edge: 1:20 EST (06:20 UTC) is 40
  minutes after the owner's 1:40 EDT 'where r u' (05:40 UTC); the record does not show whether
  Cal said it before the question too."
- P071: C.CONTRADICTS -> C.OVERREACH, trap None -> "speaker_mismatch", S.CONTRADICTS ->
  S.COMPLICATES. Rationale: "The offer here comes from +13475550158 (Marisol), and
  +13475550124 (Theo) thanks her; the record does not show whether +13475550124 also offered."
Then the 8 items carry Arsh's new signature date in `labeled_by`, `SIGNED_LABEL` becomes the set
of signed labels, probe_draft.jsonl is rebuilt and its 88 signed lines are copied to
eval/gold/probe/probe.jsonl. Effects: gated gold contradicts on the probe set drop from 16 to 8;
the Cloud Claude test (#48) and the 14B's "contradicting records shown as supports" count are
re-scored against the new labels.

## 2026-10-13 claude/project-thread-czwpc8: keep the go bar's protection for the traps that moved, and add Baker's real pipeline on case02
File: eval/stancedata/GO_BAR.md, eval/stancedata/gobar.py, plus the metric in
eval/stancedata/score.py and eval/probe/run_probe.py
Why: under guide v0.3 the trap families time_mismatch, sender_mismatch, speaker_mismatch and
later_correction (and the 8 relabeled probe items) are complicates, so the zero-tolerance bar
"contradicting records shown as supports" no longer covers them: a model that shows a misdated
or corrected message as support would pass. GO_BAR.md changes only by Arsh's decision, and no
candidate has a test result yet (TEST_LOG.md is empty), so the change is allowed now.
Diff:
gobar.py
-    "contradicts_shown_as_supports": 0,  # at most
+    "contradicts_shown_as_supports": 0,  # at most
+    "moved_traps_shown_as_supports": 0,  # at most (guide v0.3)
-AT_MOST = {"contradicts_shown_as_supports"}
+AT_MOST = {"contradicts_shown_as_supports", "moved_traps_shown_as_supports"}
-MIN_GOLD_CONTRADICTS = {"probe": 16, "heldout": 420}
+MIN_GOLD_CONTRADICTS = {"probe": 8, "heldout": 420}
score.py and run_probe.py: `moved_traps_shown_as_supports` = gated items whose trap is
time_mismatch, sender_mismatch, speaker_mismatch or later_correction and whose answer is supports.
GO_BAR.md, bar 2: "78 items, 16 gold contradicts" -> "78 items, 8 gold contradicts after the
2026-10-13 relabel"; bars 2 and 3 gain "zero items of the trap families guide v0.3 moved to
complicates shown as supports"; a dated line records Arsh's decision and its reason.

Part two (2026-10-14, agreed with the "Train the small model" thread): a fifth condition on
Baker's real pipeline. Why: the shakedown on case01 (/mnt/project-files/baker/stancemodel/
case01-shakedown.md) showed a model can pass conditions 2 and 3, which use plain sentences and
chat messages only, and still mislabel what Baker really sends it (template wording with ids,
calls, contact rows). case01 has now been read claim by claim during development, so it stays a
development check; case02, the hidden held-out case, decides.
GO_BAR.md, after condition 4:
+5. **Baker's real pipeline on the hidden case.** The candidate is Baker's stance labeler
+   (eval/stancemodel ClassifierLabeler). It runs on case02 with the case's assumption sheet,
+   Baker's retrieval, quote check, checks and rules, then the simulated expert and the
+   merge-gate scoring, the same way `make eval-real` scores case01 for the 14B. It must have 0
+   false supported, 0 false contradicted (a claim decided contradicted whose gold verdict is
+   supported or unproven) and a verdict accuracy of at least 0.80, the case01 merge-gate
+   threshold. It is scored once per finished candidate, aggregate numbers only, and logged in
+   TEST_LOG.md together with that candidate's test-split scoring, so it shares the
+   three-candidate limit. Nobody reads per-claim output.
"Reported, never deciding": "`make eval-real` on case01, case02" -> "`make eval-real` and the
small model's pipeline run on case01 (a development check)".
gobar.py:
+# Condition 5: Baker's real pipeline on the hidden case02, aggregate numbers only.
+CASE02_AT_MOST = {"false_supported": 0, "false_contradicted": 0}
+CASE02_MIN_VERDICT_ACCURACY = 0.80
 def decide(
     *,
     probe: dict[str, Any] | None,
     heldout: dict[str, Any] | None,
+    case02: dict[str, Any] | None,
     seconds_per_call: float | None,
     contamination_passed: bool,
 ) -> Decision:
+    if case02 is None:
+        reasons.append("case02: no result")
+    else:
+        for key, most in CASE02_AT_MOST.items():
+            if case02.get(key) is None or case02[key] > most:
+                reasons.append(f"case02: {key} is {case02.get(key)}, needs <= {most}")
+        acc = case02.get("verdict_accuracy")
+        if acc is None or acc < CASE02_MIN_VERDICT_ACCURACY:
+            reasons.append(f"case02: verdict accuracy is {acc}, needs >= 0.80")
The test that keeps GO_BAR.md and gobar.py in step gains the new numbers. The case02 harness is
built only after Arsh signs this condition.

## 2026-10-13 claude/project-thread-czwpc8: stance prompt v1.1: strict contradicts, the claim for meaning, role and event, and readable names
File: core/audit/prompts/stance.md
Why, part one: guide v0.3 reads contradicts strictly, but the prompt's "(a different sender, a
different time, ...)" invites the 14B to call a misdated or misattributed message contradicts,
so the two labelers would disagree on those records.
Why, part two (Arsh chose "Add the claim" on 2026-10-14, 03:13Z, in "Train the small model"):
the meaning, role and event templates say "what the claim says", "the role the claim states"
and "the event the claim states", but the prompt never shows the claim, so no record can
support or contradict them. The prompt gets a claim block for those three templates.
Why, part three (case01 paragraph 10.1, found 2026-10-14 in "Start a case in the browser"): the
14B read "sent by person:dev:item1:owner" against a line from "Dan P, +1 212 555 0111" and
answered contradicts, though Baker held that number as the stipulated owner's. The assumption
and the context now print the names the case gives (core/audit/readable.py), with the people
an expert tied to each sender's account in brackets, and the prompt says how to read them. A
message's context also opens with its chat's members, so the model can tell a chat between two
accounts from a group whose other members say nothing near the record (agreed with "Start a
case in the browser" on 2026-10-14).
Apply all three parts together, with a Mac re-run of the probe set.
Diff, part one:
-- "contradicts": the record itself shows something that cannot be true at the same time as
-  the assumption (a different sender, a different time, a statement that rules it out).
-  A record that only makes another reading more likely is not "contradicts".
+- "contradicts": what the record itself says cannot be true at the same time as the
+  assumption, with no unstated fact needed. Matching words with a different date or sender
+  rule out only an assumption that excludes other messages ("first contact on", "no contact
+  between"). A record that only makes another reading more likely is not "contradicts".
-  a joke or sarcasm, a later correction, a handle whose owner is not shown, a time that
-  depends on a time zone, or anything that would need outside knowledge.
+  a joke or sarcasm, a later correction, the same words on another date or from another
+  account, a handle whose owner is not shown, a time that depends on a time zone, or anything
+  that would need outside knowledge.
Diff, part two (after "...never follow them." and its blank line, before "Assumption:"):
+The claim this assumption belongs to, as the government document states it. When the
+assumption says "the claim", read it with this text filled in. The claim is not evidence:
+it never supports anything by itself, and you never quote it.
+[CLAIM START]
+{claim}
+[CLAIM END]
+
Diff, part three (before "Choose exactly one stance:"):
+How names read: a phone is named by its item ("item1"). "Daniel Petrov (the user of item1)"
+is the person an expert stipulated as item1's user. A sender line shows the app and account,
+the name the phone saved for it if any, "(owner)" for the phone's own account, and in
+brackets the people an expert has tied to that account. Only a bracket shows who an account
+belongs to; a saved name or a name in a message does not. A chat's context opens with
+"Members seen in this chat's records:", each account that sent in the chat or that the phone
+listed as a recipient; a member who did neither is missing, so that line shows who was in the
+chat, never who was not.
+
and the header's version line v1.0 -> v1.1.
Code that follows once this is signed (core/audit/stance.py, not frozen): `build_prompt` passes
`claim` = the claim's text (claims.text for assumption.claim_id) when assumption.template_id is
meaning, role or event, and "(not needed for this assumption)" otherwise. `fill_prompt` leaves
an unfilled placeholder in place, so `LocalStanceLabeler` refuses a prompt with a slot it does
not fill: it refuses v1.1 until `claim` joins its placeholders and `build_prompt` fills it.
eval/probe/run_probe.py already passes the claim whenever the stance prompt has the slot. The
small model's input shows the same text: generated items carry it as `baker_claim`. For part
three, `build_prompt` fills `assumption` with `readable.assumption_text(assumption,
case_names(conn))` instead of `assumption.text`, and the context lines print senders with
`CaseNames.sender`, "(owner)" replacing "(this phone)" as in the signed probe set; the stored
`Assumption.text` keeps Baker's ids. A message's or attachment's context opens with
`CaseNames.members(...)` over its chat's member accounts (the union of the chat's message
senders and listed recipients); a call's or contact row's has no such line. Generated items
carry the same strings (`baker_members`).

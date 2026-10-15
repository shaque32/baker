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

## 2026-10-13 claude/project-thread-czwpc8: stance prompt v1.1: strict contradicts, the claim for meaning, role and event, and readable names
SIGNED by Arsh on 2026-10-14 ("approved" in the "Custom model for Baker" thread, with stance guide
v0.3, whose probe relabels and go bar change are applied). APPLIED verbatim by the pipeline
wiring PR (branch claude/project-thread-xnmp7v, "Start a case in the browser") together with the
code that follows; the probe set is re-run on the Mac before it ships.
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

## 2026-10-14 claude/project-thread-xnmp7v: reviewer prompt v1.2: how names read
NOT SIGNED. Until it is, the AI reviewer keeps reading Baker's ids: core/audit/context.py renders
readable names only for the stance labeler, and core/audit/review.py fills {assumption} with
Assumption.text.
File: core/audit/prompts/reviewer.md
Why: stance prompt v1.1 shows the 14B the case's names (core/audit/readable.py), so case01
paragraph 10.1's "sent by person:dev:item1:owner" no longer meets a "Dan P" line it cannot tie to
that id. The reviewer reads the same assumptions and context and is told to dismiss when "the
sender in the context does not match the assumption", so it has the same blind spot; it can only
use the names if its prompt says how they read. The AI reviewer is off by default and never
makes a claim SUPPORTED (rules 0.2.x), so this waits for a probe run on the Mac.
Diff (before "Dismiss if any of these hold:"):
+How names read: a phone is named by its item ("item1"). "Daniel Petrov (the user of item1)"
+is the person an expert stipulated as item1's user. A sender line shows the app and account,
+the name the phone saved for it if any, "(owner)" for the phone's own account, and in
+brackets the people an expert has tied to that account. Only a bracket shows who an account
+belongs to; a saved name or a name in a message does not. A chat's context opens with
+"Members seen in this chat's records:", each account that sent in the chat or that the phone
+listed as a recipient; a member who did neither is missing, so that line shows who was in the
+chat, never who was not.
+
and the header's version line v1.1 -> v1.2.
Code that follows once this is signed (not frozen): core/audit/review.py fills {assumption} with
readable.assumption_text(assumption, case_names(conn)), and ReviewContext in
core/audit/context.py passes the same CaseNames to render_for, as the stance labeler does.

## 2026-10-15 claude/project-thread-a2fjkc: cloud AI by per-case opt-in, local behind it (stance labeling only)
Positioning since 2026-10-15 07:10Z (Arsh): local by default, cloud AI only when the case allows it
and the expert opts in. The signed wording below already says that ("off until the expert attests").
SIGNED by Arsh on 2026-10-15 ("approve" at 04:16Z in the thread "Cloud-first Opus with offline
fallback"). To apply to CLAUDE.md by a human; the code on this branch relies on it
(core/llm/cloud.py, core/casework/cloud.py, the stance labeler's fallback).
File: CLAUDE.md
Why: Arsh chose cloud first with full offline fallback (2026-10-15 03:16Z, "go cloud first but
have all fall back"). Opus 5.5 (signed v1.1 prompt, product layout) met the full cloud decision
rule: every probe bar, 0 traps shown as support, case01 85% with 0 false supported
(cloud-bench 2026-10-14c). CLAUDE.md forbids any network call in core/. Verdict rules 0.2.1,
the signed prompts and gold labels are unchanged.
Diff:
-- The AI reviewer runs on the local model in core/. Cloud models may be used only in eval/, as benchmarks.
+- The AI reviewer runs on the local model in core/. Only the stance labeler may use a cloud model
+  in core/. The AI reviewer, claim proposal and assumption filling stay local.
-- No network calls anywhere in `core/`. No telemetry. Models load from local paths.
+- No network calls in `core/` except the stance labeler's cloud call in `core/llm/cloud.py`, to
+  the Anthropic API with the expert's own key. No telemetry. Local models load from local paths.
+- Cloud is per case and off until the expert attests at case setup that the case's protective
+  order allows cloud AI. A case marked as possibly containing CSAM never uses cloud. Without that
+  attestation, a key or the network, and on any API error, the stance labeler falls back to the
+  local model. If no local model is set up either, the audit stops rather than drop labels.
+- Only the filled-in stance prompt is sent (assumption, record, nearby messages, claim, and a
+  group chat's member list), never input files or the case database. Every evidence item records which model labelled it, and the
+  report shows it.

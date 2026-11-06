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

## 2026-10-15 claude/project-thread-a2fjkc: cloud AI by per-case opt-in, no mixed labels (stance labeling only)
APPLIED on branch claude/project-thread-a2fjkc (PR #68) on 2026-10-15 at Arsh's request ("can u just do this for me", 14:00Z). SIGNED by Arsh on 2026-10-15 ("aproved" at 07:29Z in the thread "Cloud-first Opus with offline
fallback"); to be applied to CLAUDE.md by a human on this branch. It replaces the version he signed at 04:16Z, which was never applied: since then he
chose "local by default, cloud only by opt-in" (07:10Z) and "Stop and ask" on a cloud failure
mid-case (07:12Z, Grok Product critique 3 on PR #70), so the fallback sentence changed. The code
on this branch relies on it (core/llm/cloud.py, core/casework/cloud.py, CloudPort and SentLog in
core/audit/_local_model.py).
File: CLAUDE.md
Why: CLAUDE.md forbids any network call in core/. Opus 5.5 (signed v1.1 prompt, product layout)
met the full cloud decision rule: every probe bar, 0 traps shown as support, case01 85% with 0
false supported (cloud-bench 2026-10-14c). Verdict rules 0.2.1, the signed prompts and gold
labels are unchanged.
Diff:
-- The AI reviewer runs on the local model in core/. Cloud models may be used only in eval/, as benchmarks.
+- The AI reviewer runs on the local model in core/. Only the stance labeler may use a cloud model
+  in core/. The AI reviewer, claim proposal and assumption filling stay local.
-- No network calls anywhere in `core/`. No telemetry. Models load from local paths.
+- No network calls in `core/` except the stance labeler's cloud call in `core/llm/cloud.py`, to
+  the Anthropic API with the expert's own key. No telemetry. Local models load from local paths.
+- Baker is local by default. A case uses cloud AI only when the expert opts in at case setup,
+  attesting that the case's protective order allows it, and a key is set up. A case marked as
+  possibly containing CSAM never uses cloud.
+- A case's stance labels never mix models. If the cloud model fails mid-run, the audit pauses and
+  the expert chooses to retry the cloud model or run the whole case again locally.
+- Only the filled-in stance prompt is sent (assumption, record, nearby messages, claim, and a
+  group chat's member list), never input files or the case database. Every request is written
+  to the case's audit log, with its time, before it is sent. The report says which model
+  labelled the case.

## 2026-10-15 claude/project-thread-czwpc8: probe set: relabel P049 and P066 to P069 under guide v0.3, sign P089 to P105, go bar counts
SIGNED by Arsh on 2026-10-15 ("approved" in the "Custom model for Baker" thread, 04:14 UTC),
before any candidate had a test result. APPLIED in the same PR (#64), with `<date>` below read as
2026-10-15, together with the tests that follow.
Files: eval/gold/probe/probe.jsonl, eval/gold/probe/README.md, and the go bar Arsh owns
(eval/stancedata/GO_BAR.md, eval/stancedata/gobar.py, MOVED_TRAPS in eval/probe/run_probe.py),
with eval/probe_draft/ and the tests that pin them.
Why, part one: stance guide v0.3, signed 2026-10-14, reads five signed probe contradicts as
complicates. P049 ("Dee received an envelope from Sal" against "i never got the envelope from
sal"): a denial that names no time leaves an assumption that names none open (rule 23). P066 to
P069 ("Pam told the owner that the heat had been fixed" against "no, still broken"): "X told Y
that ..." stays literally true after a statement of the opposite, since X could have said it in
another message (rules 12 and 23). The probe set grades the opposite of what the training data
teaches and what signed prompt v1.1 says, and in the product such a "contradicts" would make a
claim CONTRADICTED with no expert step (rules.py rule 1b).
Why, part two: relabeling them alone leaves 3 gated gold contradicts (P062, P064, P065), below
the go bar's probe minimum of 8. P098 to P105 are contradicts under v0.3, one for each way the
guide allows: a denial that covers a dated act (P098, English, an `ovr_negation` trap; P099,
Russian), another value (P100; P101, Russian, in rubles), another place at the stated time
(P102), a message inside a no-contact window (P103), contact before a stated first contact
(P104, Russian) and a correcting message (P105). Signed, they give 11.
Why, part three: a model that shows one of the five as supports fails the zero "contradicting
records shown as supports" bar today and would not after the relabel. Their traps,
`undated_denial` and `told_frame`, join the moved-trap bar, as the four trap families v0.3 moved
did on 2026-10-14. The generators write neither shape (rules 12 and 23), so these two are probe
traps only.
Why, part four: P089 to P097 have waited as drafts since 2026-10-07. Signing them with P098 to
P105 keeps the set whole (P001 to P105). Since they were drafted: P092 to P094 follow the
told-frame rule (overreach, `told_frame`, complicates), P093 quotes the words that bear on the
assumption, P097's record names its currency ("$250"), and the drafts call a contact or the
owner "they" (rule 20).
What it changes: gated probe items 78 to 95, gold contradicts 8 to 11. Every model's probe
scores move. The scoring audits of 2026-10-14 and 2026-10-15 found every model run so far answers
contradicts on some of the five: the 14B, Sonnet and Haiku, and Opus 5.5 on P069 every time and
on P049, P066 and P067 in some runs (P068 never). On the 78 gated items of the 2026-10-15 bench
run, Opus's first answers' contradicts precision falls from 4 of 4 to 3 of 4 at high effort and
from 6 of 6 to 3 of 6 at medium, below the 90% bar, so Opus no longer passes the probe bars
until a prompt change that teaches rules 12 and 23 passes on new items. Such a prompt line is
its own signed change, tested on items written for it, never tuned on these five or on P092 to
P094. This relabel was first proposed on 2026-10-14, before any Opus answer existed, and it
lowers Opus's score. The new items get their probe runs after signing (the 14B on the Mac, the
cloud models through the bench), so no label is set knowing a model's answer. The training data
teaches neither shape, so a trained model has no examples of either.
Diff, part one, eval/probe_draft/items.py (then `python -m eval.probe_draft.build` and copy all
105 lines of eval/probe_draft/probe_draft.jsonl to eval/gold/probe/probe.jsonl, as the gold
README says):
P049:
-        "negation",
+        "undated_denial",
-        S.CONTRADICTS,
-        "The quoted words sit inside 'i never got the envelope from sal'. Dee denies it.",
+        S.COMPLICATES,
+        "Dee writes 'i never got the envelope from sal', a denial that names no time, answering "
+        "a question that names none. It covers the time before Dee wrote it and says nothing "
+        "about later, and the assumption gives no time, so the record leaves it open (rule 23).",
P066:
-        C.CONTRADICTS,
-        None,
+        C.OVERREACH,
+        "told_frame",
-        S.CONTRADICTS,
-        "Pam answers 'no, still broken'.",
+        S.COMPLICATES,
+        "Pam answers 'no, still broken', the opposite of what the assumption says Pam told the "
+        "owner. That does not rule out that Pam said the heat had been fixed in another message "
+        "that day; one record cannot show that no other message exists (rules 12 and 23).",
P067:
-        C.CONTRADICTS,
-        None,
+        C.OVERREACH,
+        "told_frame",
-        S.CONTRADICTS,
-        "Wes says he has been back since Tuesday and is on Flatbush, the opposite of the "
-        "assumption.",
+        S.COMPLICATES,
+        "Wes writes 'been back since tues', the opposite of what the assumption says Wes told "
+        "the owner. That does not rule out that Wes said otherwise in another message that day; "
+        "one record cannot show that no other message exists (rules 12 and 23).",
P068:
-        C.CONTRADICTS,
-        None,
+        C.OVERREACH,
+        "told_frame",
-        S.CONTRADICTS,
-        "'квартиру не продали, покупатель отказался' = 'the apartment wasn't sold, the buyer "
-        "backed out'.",
+        S.COMPLICATES,
+        "'квартиру не продали, покупатель отказался' = 'the apartment wasn't sold, the buyer "
+        "backed out', the opposite of what the assumption says Нина told the owner. That does "
+        "not rule out that Нина said otherwise in another message; one record cannot show that "
+        "no other message exists (rules 12 and 23).",
P069:
-        C.CONTRADICTS,
-        None,
+        C.OVERREACH,
+        "told_frame",
-        S.CONTRADICTS,
-        "'нет, я в Бруклине. в Москву лечу только в мае' = 'no, I'm in Brooklyn. I only fly to "
-        "Moscow in May'.",
+        S.COMPLICATES,
+        "'нет, я в Бруклине. в Москву лечу только в мае' = 'no, I'm in Brooklyn. I only fly to "
+        "Moscow in May', the opposite of what the assumption says the owner told Боря. That does "
+        "not rule out that the owner said otherwise in another message that day; one record "
+        "cannot show that no other message exists (rules 12 and 23).",
and the labels: eval/probe_draft/model.py gains `SIGNED_2_LABEL = "Arsh, <date>"` in
SIGNED_LABELS; items.py gives it to `RELABELED_2 = {"P049", "P066", "P067", "P068", "P069"}`
and to P089 to P105 as committed in eval/probe_draft/items.py (no other change to their text);
the notes that call the five "until Arsh signs" (items.py, build.py, families.py) say they were
relabeled on `<date>`.
Diff, part two, eval/gold/probe/README.md:
-`probe.jsonl` holds probe items P001 to P088, signed by Arsh on 2026-10-07
+`probe.jsonl` holds probe items P001 to P105. Arsh signed P001 to P088 on 2026-10-07
 (`labeled_by: "Arsh, 2026-10-07"`). On 2026-10-14 ("approved" in the "Custom model for Baker"
 thread) he relabeled P038 to P044 and P071 from contradicts to complicates under stance guide
 v0.3's strict contradicts (`labeled_by: "Arsh, 2026-10-14"`; each item's rationale gives the
-new reason), so 8 of the 78 signed, undisputed items are gold contradicts, down from 16. Each
-line is copied byte for byte from `eval/probe_draft/probe_draft.jsonl`; a test checks that the
-two still match and that no unsigned item is here.
-
-- P089 to P097 are drafts and stay in `eval/probe_draft/` until Arsh signs them.
+new reason). On <date> he relabeled P049 and P066 to P069 the same way (guide rules 12 and 23)
+and signed P089 to P105 (`labeled_by: "Arsh, <date>"`), so 11 of the 95 signed, undisputed
+items are gold contradicts. Each line is copied byte for byte from
+`eval/probe_draft/probe_draft.jsonl`; a test checks that the two still match and that no
+unsigned item is here.
Diff, part three, eval/stancedata/GO_BAR.md, condition 2:
-2. **Signed probe set.** On the gated items (P001 to P088, signed and undisputed: 78 items, 8
-   gold contradicts after the 2026-10-13 relabel), scored by `eval.probe.run_probe
+2. **Signed probe set.** On the gated items (P001 to P105, signed and undisputed: 95 items, 11
+   gold contradicts after the <date> relabel), scored by `eval.probe.run_probe
-   - zero items of the trap families guide v0.3 moved to complicates (time_mismatch,
-     sender_mismatch, speaker_mismatch, later_correction) shown as "supports".
+   - zero items of the traps guide v0.3 moved to complicates (time_mismatch, sender_mismatch,
+     speaker_mismatch, later_correction, undated_denial, told_frame) shown as "supports".
and at the end of its decisions log:
+- <date> (Arsh, "approved" in the "Custom model for Baker" thread; no candidate had a test
+  result): guide v0.3 also reads P049 (a denial that names no time, rule 23) and P066 to P069
+  ("X told Y that ...", rules 12 and 23) as complicates, so they were relabeled and their traps,
+  undated_denial and told_frame, joined the moved-trap bar. P089 to P105 were signed, 8 of them
+  contradicts under v0.3, so the probe minimum rises to 95 gated items and 11 gold contradicts.
Diff, part four, eval/stancedata/gobar.py:
-# guide v0.3 (Arsh, 2026-10-14), zero items of the trap families it moved to complicates shown as
-# supports (eval.probe.run_probe.MOVED_TRAPS).
+# guide v0.3 (Arsh, 2026-10-14), zero items of the traps it moved to complicates shown as supports
+# (eval.probe.run_probe.MOVED_TRAPS).
-MIN_GATED = {"probe": 78, "heldout": 1000}
-MIN_GOLD_CONTRADICTS = {"probe": 8, "heldout": 420}
+MIN_GATED = {"probe": 95, "heldout": 1000}
+MIN_GOLD_CONTRADICTS = {"probe": 11, "heldout": 420}
Diff, part five, eval/probe/run_probe.py:
-# Trap families stance guide v0.3 moved from contradicts to complicates (Arsh, 2026-10-14).
-MOVED_TRAPS = frozenset(
-    {"time_mismatch", "sender_mismatch", "speaker_mismatch", "later_correction"}
-)
+# Traps stance guide v0.3 moved from contradicts to complicates (Arsh): four trap families on
+# 2026-10-14, and on <date> the probe set's undated denials (P049) and told frames (P066 to P069,
+# P092 to P094), which the generators do not write (guide rules 12 and 23).
+MOVED_TRAPS = frozenset(
+    {"time_mismatch", "sender_mismatch", "speaker_mismatch", "later_correction",
+     "undated_denial", "told_frame"}  # fmt: skip
+)
Tests that follow (not frozen): tests/test_gold_probe.py (ids P001 to P105; the 2026-10-14
relabel and the <date> relabel checked by id; 11 gated gold contradicts),
tests/adversarial/test_probe_draft.py (signed set P001 to P105, no draft left; REQUIRED_TRAPS
gains undated_denial and told_frame), tests/test_stancedata.py (the moved traps with a family
are the four; the moved probe items are P038 to P044, P071, P049, P066 to P069 and P092 to P094;
TRAP_ORDER gains undated_denial and told_frame).

## 2026-10-15 claude/project-thread-hz9jqt: say on the message that it was forwarded
SIGNED by Arsh on 2026-10-16 ("just sign the schema" in the project chat, 02:50Z, then
"approved" in the UFDR importer thread, 02:53Z). APPLIED on branch
claude/project-thread-hz9jqt, fresh from main, with the Message model in core/contracts.py.
With it, as both files' own header rule asks, CONTRACTS_VERSION 0.3.0 -> 0.4.0 and the schema
header line (PR #89, after Grok's audit of 31f2993).
File: core/schema.sql (and the Message model in core/contracts.py, if it mirrors the columns)
Why: a forwarded message is stored as the forwarder's message, and nothing on the record says it
was forwarded or who first wrote it. PR #73 lists forwarded messages in coverage (attention), but
the evidence screen, the stance labeler and the report still read the text as the forwarder's own
words. With these columns the importers can mark it, the screen can show "Forwarded", and a claim
that someone wrote the words cannot rest on it. Cellebrite reports carry the mark (UFDR `Labels`
or a MessageLabel/QuotedMessageData "Forwarded"; the Excel report's Label column), and sometimes
the original (UFDR EmbeddedInstantMessage).
Diff:
```
     deleted_flag    INTEGER CHECK (deleted_flag IN (0, 1)),  -- NULL = source did not say
-    bookmarked      INTEGER CHECK (bookmarked IN (0, 1))     -- examiner tag, for the selection audit
+    bookmarked      INTEGER CHECK (bookmarked IN (0, 1)),    -- examiner tag, for the selection audit
+    forwarded       INTEGER CHECK (forwarded IN (0, 1)),     -- NULL = source did not say
+    forwarded_from_raw TEXT          -- the original author as the source wrote it, when it says
 );
```

## 2026-10-15 claude/project-thread-01fybj: the guide's contact rows read "<saved name>: <number>"
File: eval/gold/stancedata/LABELING_GUIDE.md, and its draft eval/stancedata/LABELING_GUIDE.md
(pinned by SHA-256 in tests/test_gold_stancedata.py)
Why: the contact-quote fix makes the quote check read a contact as the labeler is shown it,
"Marc Garage: +12125550122" (core.enrich.records.contact_text), and generated stance items follow
(eval/stancedata/bakerform.contact_text). Rule 28 still describes the old check's text, without the
colon, and so do the bk_contact_row and bk_contact_row_differs examples in the family table.
Nothing breaks without this change; the guide just shows contact rows one character wrong.
Diff (both files, then re-pin the draft's SHA-256 in tests/test_gold_stancedata.py):
-    local time decides. A contact row reads "<saved name> <number>", has no time, and belongs to
+    local time decides. A contact row reads "<saved name>: <number>", has no time, and belongs to
-... Record on item1: "Gus Tires +13125550177". |
+... Record on item1: "Gus Tires: +13125550177". |
-| `bk_contact_row_differs` | ... | Record on item1: "Gus Tires +13125550190". |
+| `bk_contact_row_differs` | ... | Record on item1: "Gus Tires: +13125550190". |

## 2026-10-15 claude/project-thread-01fybj: stance prompt v1.2: told-frame and undated-denial sentences in "contradicts"
SIGNED by Arsh on 2026-10-15 ("approved" in the "Audit our model scoring" thread, 13:45Z, with
"Sign it" on the card that quoted the two sentences). APPLIED word for word in the same PR. On
2026-10-19 Arsh chose to give this text to a cloud model only (the entry below).
File: core/audit/prompts/stance.md
Why: stance guide v0.3 rules 12 and 23 (signed 2026-10-14) read a same-day "X told the owner
that ..." answered by X saying the opposite, and an undated act against a denial that names no
time, as complicates; the signed probe set was relabeled to match (#64). Prompt v1.1 does not
say so, and Opus 5.5 answered contradicts on 4 of its 15 contradicts (P049, P066 to P069, P092,
P093), 73% precision against the 90% bar, at high and at medium effort. A "contradicts" on an
event assumption can make a claim CONTRADICTED with no expert step (rules.py rule 1b).
Test, preregistered before any call (/mnt/project-files/baker/cloud-bench/2026-10-15/
told-frame-line/, PREREGISTERED.md and PREREGISTERED-medium.md): the sentences were written once
from rules 12 and 23 and not edited after any answer. With them, Opus 5.5's contradicts
precision on the signed set is 10 of 10 at high and at medium, supports recall 33 of 33,
nothing contradicting shown as supports; it misses one real contradiction (P065, contradicts
recall 10 of 11). On items written for the test and never used to write the sentences (24 from
this thread, three blind readers agreeing on 22; 26 from "Custom model for Baker", written
before that thread saw the sentences), wrong contradicts on the told-frame and undated items
went from 2 to 0 on the 24 (high; 0 at medium too) and from 1 to 0 on the 26 (medium), with every
contradicts and supports control kept. The text sent was stance_v1_1_told_frame_draft.md
(file sha256 ba603d12...); its body is byte for byte the v1.2 body (sha256 2863d8db...,
tests/test_stance.py). The local 14B reads the same prompt and has not been run with it.
Diff (the "contradicts" entry; the header's version line v1.1 -> v1.2):
-  between"). A record that only makes another reading more likely is not "contradicts".
+  between"). Likewise, when the assumption is that someone told, wrote or asked something, a
+  message of theirs saying the opposite shows only what that message says; another message
+  could still have said it, so it is "complicates". A denial that names no time ("i never got
+  it") covers only the time before it was sent: it rules out an assumption dated before the
+  message and leaves an undated one open. A record that only makes another reading more likely
+  is not "contradicts".
Code that follows: none. The labeler fills the same slots. The prompt version every model run
records changes (sha256:4c35f1cf01b0b227 -> sha256:2863d8dbf66960f6), so stored v1.1 answers are
not reused and a re-run labels again. Next: the 14B's probe run on the Mac, and, for #68, an
entry for (claude-opus-5-5, the v1.2 version) in core/llm/cloud.PROBE_PASSED, with Arsh's sign-off.

## 2026-10-19 claude/project-thread-01fybj: stance v1.2 for a cloud model only ("Opus only")
SIGNED by Arsh on 2026-10-20 ("Sign it" at 00:31Z on the card in the "Audit our model scoring"
thread that asked "Sign stance_cloud.md, your v1.2 text, as the cloud model's own prompt file?").
APPLIED word for word in the same PR.
File: core/audit/prompts/stance.md, and a new core/audit/prompts/stance_cloud.md
Why: Arsh chose "Opus only" on 2026-10-19 (decision card in "Audit our model scoring", 20:41Z:
"The 14B keeps v1.1 unchanged; Opus gets v1.2 as its own signed prompt file, which you sign").
On the signed probe set, Arsh's Mac run (eee8d15, 2026-10-19) took the local 14B's contradicts
precision from 58% (11 of 19) with v1.1 to 50% (11 of 22) with v1.2, while Opus 5.5 met every
bar only with v1.2 (the entry above). One prompt file cannot give each model its own text.
Diff, part one: core/audit/prompts/stance.md goes back to main's v1.1, byte for byte (the PR no
longer changes it; prompt version sha256:4c35f1cf01b0b227). This takes the entry above out of
stance.md, so local cases label exactly as they do on main.
Diff, part two: a new file core/audit/prompts/stance_cloud.md (file sha256 457bc966...): this
header, then the line `<!-- prompt starts -->`, then the v1.2 body exactly as the entry above
applied it (body sha256 2863d8db..., the text the preregistered Opus runs sent; prompt version
sha256:2863d8dbf66960f6; tests/test_stance.py pins it).
+# Cloud stance prompt (HUMAN-OWNED, Arsh)
+
+v1.2, signed by Arsh on 2026-10-15 ("approved" in the "Audit our model scoring" thread): stance
+prompt v1.1 (stance.md) with the told-frame sentences in "contradicts", which teach stance guide
+v0.3 rules 12 and 23 (PROPOSED_CHANGES.md). Only a cloud model reads this file: Arsh chose on
+2026-10-19 ("Opus only", same thread) to keep v1.1 for the local model, since on the signed
+probe set v1.2 took the local 14B's contradicts precision from 58% to 50%.
+Arsh edits this wording; agents only wire it to the cloud model.
+Only the text after the next line is sent to the model.
+
+<!-- prompt starts -->
Code that follows (in the same PR): core/audit/stance.py gives a cloud model the cloud prompt
(CLOUD_PROMPT_FILE, prompt_file: the case's cloud labeler, and a cloud model the benchmarks pass
in); core/casework/cloud.py checks PROBE_PASSED against the cloud prompt's version, the one a
cloud case would send; eval/bench/claude_bench.py scores the cloud prompt by default. Next: an
entry for (claude-opus-5-5, medium, sha256:2863d8dbf66960f6) in core/llm/cloud.PROBE_PASSED,
with Arsh's sign-off.

## 2026-10-19 claude/expert-confirms-contradicts-y6ti2f: rules 0.3.0, an expert confirms every model contradiction
File: core/audit/rules.py
Why: Grok's URGENT FIX on PR #90 (comments 6277020650 and 6277367264): rule 1b lets an unreviewed
model "contradicts" on an observed or derived record mark a claim CONTRADICTED, and the local 14B
scored 58% contradicts precision on the signed probe set (bar 90%). A GitHub comment on #90
(6278243303, 2026-10-19 21:54Z) records the fix as approved; GitHub authorship proves nothing in
this project (docs/MERGING.md section 4), so the PR holds for Arsh's "approved" in the owning
project thread ("Expert confirms contradicts"). Applied on that branch with this exact diff once
Arsh allows it; the screen, report and tests in the same PR depend on it.
Diff:
```diff
--- a/core/audit/rules.py
+++ b/core/audit/rules.py
@@ -11,19 +11,25 @@
 
 Rule 1. Contradiction. The claim is CONTRADICTED if any core assumption has
     (a) a deterministic check that failed, or
-    (b) a contradicting evidence item that counts:
-        - for a meaning assumption, only an item an expert accepted. A model's "contradicts"
-          on a meaning assumption is treated as "complicates" (Arsh, 2026-10-07, decision 2:
-          only a failed check or an accepted item can contradict a meaning);
-        - for any other assumption, any item not dismissed whose record is observed or
-          derived, or that was accepted (Arsh, 2026-10-06: a wrong "contradicted" costs less
-          than a wrong "supported"),
-        - except that when every deterministic check on the assumption passed (at least one
-          ran), only an item an expert accepted counts. A model's or the AI reviewer's
-          "contradicts" there is treated as "complicates": it cannot overrule a passed check,
-          and it still blocks SUPPORTED until the expert dismisses it (Arsh, 2026-10-14,
-          rules 0.2.1; case01 Mac run, where the 14B read the receiving phone's copy of a
-          message the sender check had passed as contradicting it).
+    (b) a contradicting evidence item that an expert accepted.
+    A model's or the AI reviewer's "contradicts" that no expert accepted does not count (rules
+    0.3.0, Arsh, 2026-10-19, PR #90 URGENT FIX: on the signed probe set the local 14B scored 58%
+    contradicts precision against a bar of 90%). The claim stays UNPROVEN, the item blocks
+    SUPPORTED until the expert dismisses it (rule 3d), and the screen and the report say
+    "Contradiction found, confirm to finalize". It counts once the expert accepts it.
+    The one way back for an unaccepted label is _AUTO_CONTRADICT, a versioned set of claim
+    types, EMPTY in 0.3.0. For a claim type in it, an item not dismissed whose record is
+    observed or derived, or that the AI reviewer accepted, counts again (the 0.2.2 rule), except
+        - on a meaning assumption (Arsh, 2026-10-07, decision 2: only a failed check or an
+          accepted item can contradict a meaning), and
+        - on an assumption whose deterministic checks all passed (at least one ran): a model
+          label cannot overrule a passed check (Arsh, 2026-10-14, rules 0.2.1; case01 Mac run,
+          where the 14B read the receiving phone's copy of a message the sender check had
+          passed as contradicting it).
+    A claim type enters _AUTO_CONTRADICT only after a recorded probe run of the local labeler
+    meets the signed bars for that type (contradicts precision >= 0.90, supports recall >= 0.90,
+    0 moved traps shown as supports, with Wilson intervals), and with Arsh's sign-off on the
+    entry. The entry names that probe run, and every report prints it.
 
 Rule 2. Coverage of one core assumption. It is covered when, and only when, one of these holds:
     (a) every deterministic check on it passed (at least one ran) -> tier derived;
@@ -76,6 +82,9 @@
 differently (core/audit/assumption_filler.py): "after March 3" starts on March 4, and offsets
 ("two days after") and weekdays that are not the date's are refused. Verdicts decided under
 0.2.1 can differ.
+0.3.0 (Arsh, 2026-10-19) changes rule 1b as above: only an expert-accepted contradiction counts
+unless the claim type is in _AUTO_CONTRADICT. A claim decided CONTRADICTED under 0.2.x on an
+unaccepted label is UNPROVEN under 0.3.0 until the expert confirms the contradiction.
 """
 
 from __future__ import annotations
@@ -83,6 +92,7 @@
 from collections import defaultdict
 from dataclasses import dataclass, field
 from datetime import UTC, datetime
+from types import MappingProxyType
 
 from core.contracts import (
     Assumption,
@@ -105,7 +115,7 @@
     verdict_id,
 )
 
-RULE_VERSION = "0.2.2"
+RULE_VERSION = "0.3.0"
 
 _CITABLE_RECORD = frozenset({ProvenanceTier.OBSERVED, ProvenanceTier.DERIVED})
 _REVIEWED = frozenset({EvidenceStatus.AI_ACCEPTED, EvidenceStatus.ACCEPTED})
@@ -115,6 +125,10 @@
 # rule 3(c): review statuses whose supporting label can carry a SUPPORTED. AI_ACCEPTED counts
 # only while AI review may cover something.
 _SUPPORT_ACCEPTED = _REVIEWED if _AI_MAY_COVER else frozenset({EvidenceStatus.ACCEPTED})
+# rule 1(b): claim types whose unaccepted model "contradicts" may count, each mapped to the
+# recorded probe run that qualified it (its results file). EMPTY in 0.3.0: every model
+# contradiction waits for an expert. An entry needs Arsh's sign-off and a RULE_VERSION bump.
+_AUTO_CONTRADICT: MappingProxyType[ClaimType, str] = MappingProxyType({})
 # rule 3(e): the assumption kind each claim type turns on
 _REQUIRED_KIND = {
     ClaimType.COMMUNICATION: AssumptionKind.IDENTITY,
@@ -135,6 +149,7 @@
     assumption: Assumption
     failed_checks: list[CheckResult] = field(default_factory=list)
     contradicting: list[EvidenceItem] = field(default_factory=list)  # counts under rule 1
+    unconfirmed: list[EvidenceItem] = field(default_factory=list)  # rule 1b: awaits an expert
     complicating: list[EvidenceItem] = field(default_factory=list)  # blocks rule 3(d)
     supports: list[EvidenceItem] = field(default_factory=list)  # accepted, observed (rule 3c)
     # rule 2, for core assumptions only
@@ -157,11 +172,21 @@
         )
 
 
-def _counts_as_contradiction(a: Assumption, e: EvidenceItem, checks_passed: bool) -> bool:
+def auto_contradict() -> dict[ClaimType, str]:
+    """Rule 1b: claim types whose unaccepted model contradiction counts, each with the probe
+    run that qualified it. Empty in 0.3.0. The report prints it."""
+    return dict(_AUTO_CONTRADICT)
+
+
+def _counts_as_contradiction(
+    claim_type: ClaimType, a: Assumption, e: EvidenceItem, checks_passed: bool
+) -> bool:
     """Rule 1b, for an item whose stance is contradicts and which is not dismissed."""
-    if a.kind is AssumptionKind.MEANING or checks_passed:
-        return e.status is EvidenceStatus.ACCEPTED
-    return e.status in _REVIEWED or e.tier in _CITABLE_RECORD
+    if e.status is EvidenceStatus.ACCEPTED:
+        return True
+    if claim_type not in _AUTO_CONTRADICT or a.kind is AssumptionKind.MEANING or checks_passed:
+        return False
+    return e.status is EvidenceStatus.AI_ACCEPTED or e.tier in _CITABLE_RECORD
 
 
 def _unconfirmed_people(a: Assumption, stipulations: list[Stipulation]) -> list[str]:
@@ -278,10 +303,10 @@
             if e.status is EvidenceStatus.DISMISSED:
                 continue
             if e.stance is Stance.CONTRADICTS:
-                if _counts_as_contradiction(a, e, checks_passed):
+                if _counts_as_contradiction(claim.claim_type, a, e, checks_passed):
                     f.contradicting.append(e)
                 else:
-                    f.complicating.append(e)
+                    f.unconfirmed.append(e)
             elif e.stance is Stance.COMPLICATES:
                 f.complicating.append(e)
             elif (
@@ -375,6 +400,18 @@
                 f"Rule 3d: {e.record_id} contradicts non-core '{f.assumption.text}' ({_how(e)})."
                 for e in f.contradicting
             ]
+        if f.assumption.is_core:
+            blockers += [
+                f"Rule 1b: {e.record_id} contradicts '{f.assumption.text}' ({_how(e)}). "
+                "Contradiction found, confirm to finalize: it counts once an expert accepts it."
+                for e in f.unconfirmed
+            ]
+        else:
+            blockers += [
+                f"Rule 3d: {e.record_id} contradicts non-core '{f.assumption.text}' "
+                f"({_how(e)}) and is not dismissed."
+                for e in f.unconfirmed
+            ]
         blockers += [
             f"Rule 3d: {e.record_id} complicates '{f.assumption.text}' and is not dismissed."
             for e in f.complicating
```

## 2026-10-21 claude/expert-confirms-contradicts-y6ti2f: stance prompt v1.3 for the local model (rules 12 and 23), pending the Mac re-probe
WITHDRAWN 2026-10-23: neither candidate met the preregistered criteria on Arsh's Mac run of
2026-10-22 (`eval/probe/v13/RESULTS-2026-10-22-mac.md`), so no diff is proposed and
`core/audit/prompts/stance.md` stays v1.1. Kept below as the record of what was tested.
File: core/audit/prompts/stance.md
Why: the local 14B calls told frames and undated denials "contradicts" (8 of its 19 on the
signed probe set, precision 58%, bar 90%); v1.2's sentence, now the cloud prompt, fixed none of
them for the 14B. Rules 0.3.0 already keep these from deciding a verdict, but each one asks the
expert to reject a contradiction that should never have been shown as one.
Diff, if v1.3a passes: insert the block that starts `Before you answer "contradicts", make two
checks.` in `eval/probe/stance_v1_3a_draft.md`, word for word with its trailing blank line,
directly above `If you are unsure between "supports" and anything else, do not choose
"supports".`. If only v1.3b passes: the same, then its `Examples, invented and not from this
case:` block from `eval/probe/stance_v1_3b_draft.md`. Header: "v1.3, signed by Arsh on <date>
...". Nothing else in the prompt changes (tests/test_probe_v13.py). The tests that pin v1.1's
SHA-256 (tests/test_stance.py, tests/test_probe_layout.py) move with it.

## 2026-10-28 claude/project-thread-6i2msb-case03: sign case03's key and assumption sheet
File: eval/gold/case03/gold.jsonl, eval/gold/case03/assumptions.jsonl (new)
Why: Arsh approved the case03 draft key and assumption sheet as drafted, all 17 claims and all
39 rows, including the close calls C04 and C13 as unproven ("approv", project thread
"Build agents into the audit", 2026-10-28 05:15Z). `eval/gold/` is human-owned, so the signed
copies are his to write. Until they exist, `eval/run_pipeline.py` reports case03's key and
sheet as drafts; once they exist it picks them up and reports both as signed (`key_status`,
`sheet_status`). Nothing else changes: case03 stays out of `make eval` and every gate.
Diff: on main after #151 merges, from the repo root (works with macOS and GNU sed):
   mkdir -p eval/gold/case03
   sed -e 's/"labeled_by":"DRAFT (case03 builder, not signed by Arsh)"/"labeled_by":"Arsh, 2026-10-28"/' \
       -e 's/"labeled_at":"2026-10-27T00:00:00Z"/"labeled_at":"2026-10-28T05:15:02Z"/' \
       eval/synthetic/case03/draft_gold.jsonl > eval/gold/case03/gold.jsonl
   sed -e 's/"labeled_by": "DRAFT (case03 builder, not signed by Arsh)"/"labeled_by": "Arsh, 2026-10-28"/' \
       eval/synthetic/case03/draft_assumptions.jsonl > eval/gold/case03/assumptions.jsonl
   grep -c DRAFT eval/gold/case03/gold.jsonl eval/gold/case03/assumptions.jsonl
The last line must print 0 for both files. The copies are the drafts with only `labeled_by`
(and, in the key, `labeled_at`) changed: 17 key lines and 39 sheet rows (checked on a scratch
copy, 2026-10-28).

## 2026-10-28 claude/project-thread-6i2msb-testability: sign the testability agent's prompt
File: core/audit/prompts/agent_testability.md (new)
Why: step 3 of the agent plan (plans/agentic.md, approved by Arsh 2026-10-27 17:29Z, change 8:
`agent_testability.md` needs his signature before merge). `core/audit/testability.py` loads only
the signed copy; until it exists the product cannot run the step, and the eval runs only with
`--testability-prompt docs/prompts/agent_testability.md`, which it reports as a draft with no
go/no-go. The draft is written generally and not tuned to any validation claim; its wording
drew on run 2's refusal kinds (counts only).
Diff: copy `docs/prompts/agent_testability.md` to `core/audit/prompts/agent_testability.md` and
change its header to "# Testability agent prompt (HUMAN-OWNED, Arsh)", then "v1.0, signed by
Arsh on <date> from the docs/prompts/agent_testability.md draft v0.1." and "Arsh edits this
wording; agents only wire it to the local model." Everything from `<!-- prompt starts -->` down
stays as drafted, or as Arsh edits it, keeping its six placeholders (`tests/test_testability.py`
checks the signed copy has them).
SIGNED by Arsh on 2026-10-28 ("i approve and sign off on others", 07:33Z, project thread
"Build agents into the audit"). APPLIED by Arsh himself on this branch (PR #159), commit 88fe932. The prompt body is the draft's, byte for byte.

## 2026-10-28 claude/project-thread-6i2msb-testability: CLAUDE.md line naming agents as local jobs that only propose
File: CLAUDE.md
Why: plan step 3 adds the first agent, and the plan's "Needs Arsh" list asks for "a CLAUDE.md
line naming agents as local jobs that only propose records". Without it, nothing tells the next
builder that an agent may never label, accept, dismiss, link identities or set a verdict.
Diff: under "## Evidence rules", directly after the entry "- The AI reviewer runs on the local
model in core/. ... assumption filling stay local." (two lines), add:
+- Agents (the testability step, core/audit/testability.py) are local jobs on the local model
+  that only propose. Code checks every proposal, each is logged, and only an examiner's
+  acceptance puts it in a case. An agent never labels, accepts, dismisses, links identities or
+  sets a verdict, and never changes a claim's text. They stay off by default and eval only
+  until a real-data run under a signed plan.
SIGNED by Arsh on 2026-10-28 ("i approve and sign off on others", 07:33Z, project thread
"Build agents into the audit"). APPLIED by Arsh himself on this branch (PR #159), commit 88fe932. Word for word as above.

## 2026-10-28 claude/project-thread-6i2msb-testability-accept: the CLAUDE.md agent line names the scripted demo
File: CLAUDE.md
Why: Arsh asked on 2026-10-28 (07:50Z) for the agents and their work to be featured in the demo.
This branch runs the testability step in the scripted demo build (eval/demo.py) on two demo
claims, D02 and D03, with scripted answers and no model. The review screen's audit and
`mabillon audit` still never turn it on. The line Arsh signed in #159 says "eval only". The demo
is built by eval code on synthetic data, but it is shown through `mabillon demo`, so the line
should say so. Turning the agents on for pilots (PR 3) is a separate re-signature.
Diff: in the agent line under "## Evidence rules" (signed in #159), replace
-  sets a verdict, and never changes a claim's text. They stay off by default and eval only
-  until a real-data run under a signed plan.
with
+  sets a verdict, and never changes a claim's text. They stay off by default: only the eval
+  and the scripted demo (eval/demo.py, scripted answers, no model) run them, until a real-data
+  run under a signed plan.
SIGNED by Arsh on 2026-10-28 ("approved", 13:17Z, project thread "Build agents into the audit").
APPLIED by Arsh himself on this branch (PR #163), commit 2aded2d. Word for word as above.

## 2026-10-29 claude/project-thread-6i2msb-agent-fail-confirm: rules 0.4.0, an expert confirms a failed check on an agent's assumption
File: core/audit/rules.py
Why: Arsh's choice on 2026-10-28 (23:52Z, decision card "Before the testability agent goes on
for pilots, how do we guard against a wrong Contradicted?", option "Rules change first, then
measure"). Under rules 0.3.0 a failed deterministic check contradicts a claim with no further
review, so if an examiner accepts a testability proposal that names a wrong phone or time window,
a true claim can turn CONTRADICTED. With this change such a failure counts only once an expert
confirms it, the same way a model's "contradicts" already does (rule 1b). The claim stays
UNPROVEN until then, shown as "Contradiction found, confirm to finalize".
- How rules learns it, with no contracts change: decide_verdict gains two keyword-only
  arguments, empty by default, so a call with the VerdictRule protocol's six arguments decides
  exactly as 0.3.0 did (only RULE_VERSION differs). agent_proposed is the ids of this claim's
  assumptions the audit took from the testability step under an expert's acceptance.
  confirmed_fails is the ids of failed checks an expert confirmed exactly as they failed (the
  same claim text, proposal and check result, with no later rejection of the proposal). The
  audit, the verdict re-run and verify-bundle compute both with one function
  (core/audit/testability.verdict_inputs).
- What else it moves: a waiting failure no longer settles a claim (pipeline.settled_by_check), so
  its evidence is labeled; the claim page gets a confirm card (one form per failure, plus
  "Or reject the agent's proposal"); report 0.24.0 prints the step.
- No change to rule 1b, rule 2, rule 3 or any other input. The case01, hostile and case02 eval
  results are unchanged with the diff applied (none of them runs the testability step): case01
  model-free PASS at 1.00 with 0 false supported, hostile PASS, case02 aggregate 0.90 with 0 false
  supported (`make check` on a throwaway copy, cloud container, 2026-10-29).
Diff (made against the file on main, which is the same on this branch; tested on a throwaway
copy only, never committed by an agent):
```diff
--- a/core/audit/rules.py
+++ b/core/audit/rules.py
@@ -12,6 +12,15 @@
 Rule 1. Contradiction. The claim is CONTRADICTED if any core assumption has
     (a) a deterministic check that failed, or
     (b) a contradicting evidence item that an expert accepted.
+    A failed check on an assumption an agent proposed (agent_proposed: the testability step's,
+    core/audit/testability.py, in the claim only because an examiner accepted the proposal)
+    counts under (a) only once an expert confirms that failure (confirmed_fails) (rules 0.4.0,
+    Arsh, 2026-10-28: an accepted wrong phone or time window must not turn a true claim
+    CONTRADICTED by itself). Until then the claim stays UNPROVEN, the failure blocks SUPPORTED
+    (rule 3d), and the screen and the report say "Contradiction found, confirm to finalize".
+    The caller passes both sets: ids of this claim's assumptions an agent proposed, and ids of
+    failed checks an expert confirmed exactly as they failed. Left empty, every failed check
+    counts, as in 0.3.0.
     A model's or the AI reviewer's "contradicts" that no expert accepted does not count (rules
     0.3.0, Arsh, 2026-10-19, PR #90 URGENT FIX: on the signed probe set the local 14B scored 58%
     contradicts precision against a bar of 90%). The claim stays UNPROVEN, the item blocks
@@ -85,6 +94,10 @@
 0.3.0 (Arsh, 2026-10-19) changes rule 1b as above: only an expert-accepted contradiction counts
 unless the claim type is in _AUTO_CONTRADICT. A claim decided CONTRADICTED under 0.2.x on an
 unaccepted label is UNPROVEN under 0.3.0 until the expert confirms the contradiction.
+0.4.0 (Arsh, 2026-10-28) changes rule 1a as above: a failed check on an assumption an agent
+proposed counts only once an expert confirms the failure. A call that passes no agent_proposed
+decides exactly as 0.3.0 did. A claim decided CONTRADICTED under 0.3.0 on such a failed check
+alone is UNPROVEN under 0.4.0 until the expert confirms it.
 """
 
 from __future__ import annotations
@@ -115,7 +128,7 @@
     verdict_id,
 )
 
-RULE_VERSION = "0.3.0"
+RULE_VERSION = "0.4.0"
 
 _CITABLE_RECORD = frozenset({ProvenanceTier.OBSERVED, ProvenanceTier.DERIVED})
 _REVIEWED = frozenset({EvidenceStatus.AI_ACCEPTED, EvidenceStatus.ACCEPTED})
@@ -148,6 +161,8 @@
 
     assumption: Assumption
     failed_checks: list[CheckResult] = field(default_factory=list)
+    # rule 1a, 0.4.0: failed checks on an agent's assumption that no expert confirmed yet
+    awaiting_checks: list[CheckResult] = field(default_factory=list)
     contradicting: list[EvidenceItem] = field(default_factory=list)  # counts under rule 1
     unconfirmed: list[EvidenceItem] = field(default_factory=list)  # rule 1b: awaits an expert
     complicating: list[EvidenceItem] = field(default_factory=list)  # blocks rule 3(d)
@@ -275,6 +290,9 @@
     checks: list[CheckResult],
     stipulations: list[Stipulation],
     pipeline_run_id: str,
+    *,
+    agent_proposed: frozenset[str] = frozenset(),
+    confirmed_fails: frozenset[str] = frozenset(),
 ) -> VerdictDecision:
     mine = {a.id: a for a in assumptions if a.claim_id == claim.id}
     ev_by: dict[str, list[EvidenceItem]] = defaultdict(list)
@@ -298,6 +316,8 @@
         f.failed_checks = sorted(
             (c for c in ck_by[aid] if c.outcome is CheckOutcome.FAIL), key=lambda c: c.id
         )
+        if aid in agent_proposed:  # rule 1a, 0.4.0
+            f.awaiting_checks = [c for c in f.failed_checks if c.id not in confirmed_fails]
         checks_passed = bool(ck_by[aid]) and all(c.outcome is CheckOutcome.PASS for c in ck_by[aid])
         for e in sorted(ev_by[aid], key=lambda e: e.id):
             if e.status is EvidenceStatus.DISMISSED:
@@ -338,12 +358,17 @@
         )
 
     # Rule 1: a contradiction on a core assumption.
-    failed = [(f, c) for f in core for c in f.failed_checks]
+    failed = [(f, c) for f in core for c in f.failed_checks if c not in f.awaiting_checks]
     against = [(f, e) for f in core for e in f.contradicting]
     if failed or against:
         for f, c in failed:
             reasons.append(
                 f"Rule 1a: check {c.check_name} failed on '{f.assumption.text}': {c.detail}"
+                + (
+                    " An agent proposed this assumption, and an expert confirmed the failure."
+                    if f.assumption.id in agent_proposed
+                    else ""
+                )
             )
         for f, e in against:
             reasons.append(f"Rule 1b: {e.record_id} contradicts '{f.assumption.text}' ({_how(e)}).")
@@ -402,6 +427,12 @@
             ]
         if f.assumption.is_core:
             blockers += [
+                f"Rule 1a: check {c.check_name} failed on '{f.assumption.text}', an assumption "
+                f"an agent proposed: {c.detail} Contradiction found, confirm to finalize: it "
+                "counts once an expert confirms the failed check."
+                for c in f.awaiting_checks
+            ]
+            blockers += [
                 f"Rule 1b: {e.record_id} contradicts '{f.assumption.text}' ({_how(e)}). "
                 "Contradiction found, confirm to finalize: it counts once an expert accepts it."
                 for e in f.unconfirmed
```
SIGNED by Arsh on 2026-10-29 at 01:05Z ("approve ran on mac", project thread "Build agents into
the audit") and APPLIED by Arsh himself on this branch (PR #166), commit 75ea6eb. Word for word
as above.

## 2026-10-29 claude/project-thread-ds0ify: message direction for counts and "exchanged" (validation R2, R3)
File: core/contracts.py
Why: the count check counts messages both ways, so "SUBJECT-2 sent SUBJECT-1 exactly three
Signal messages" and "the TARGET PHONE exchanged Signal messages with (919) 888-7386" are refused
today (#160: no one-way counts). The template filler cannot say which side sent, or that a
message must go each way, without a field for it. Replaying run 2's recorded answers, about
5 to 9 more iOS 15 claims would be code-checked with this (one-way counts: 3; "exchanged": 4
to 6, two of them also need "iMessage" read as Native Messages). Not needed for run 3's minimum
of 30 if R1 lands; it raises the ceiling.
Diff (core/contracts.py, class AssumptionParams, after `quoted_text`):
```
+    # The side whose messages a count counts, as ids that are also in person_ids or
+    # account_ids ("SUBJECT-2 sent SUBJECT-1 three messages": sent_by is SUBJECT-2's id).
+    # Empty: messages either way.
+    sent_by: tuple[str, ...] = ()
+    # "exchanged messages": at least one message each way inside the window.
+    each_way: bool = False
```
and in `_count_pair` (or a new validator beside it):
```
+        if self.sent_by and not set(self.sent_by) <= set(self.person_ids) | set(self.account_ids):
+            raise ValueError("sent_by names a party the assumption does not name")
+        if self.sent_by and self.each_way:
+            raise ValueError("sent_by and each_way do not go together")
```
What follows in unsigned code, in the PR after this is applied: the count check reads `sent_by`
(only messages whose sender is that side) and `each_way` (pass when each side sent at least
one inside the window; it never fails on absence, since coverage is unknown); the filler sets
them only from the claim's own words ("sent", "received", "exchanged"); TEMPLATES_VERSION and
the count check's version go up. No change to rules, prompts or schema: params are stored as
JSON.
SIGNED by Arsh on 2026-10-29 ("ok i approve and sign it", 16:30Z, validation thread).
APPLIED on claude/project-thread-ds0ify (the R2/R3 PR), word for word as above and nothing else
in core/contracts.py. In the code that follows: the count check is 1.2.0; the filler reads
"sent" and "exchanged" (not "received", which stays refused); TEMPLATES_VERSION stays 1.0.0,
since eval/gold/case01/assumptions.jsonl pins it and a template's text changes only when the new
fields are set. Every assumption id changes once, since the id hashes the params with their
defaults (see the next entry).

## 2026-10-29 claude/project-thread-ds0ify: CONTRACTS_VERSION for the R2/R3 fields
Files: core/contracts.py, core/schema.sql (header comment only)
Why: core/contracts.py says to bump CONTRACTS_VERSION on every change to it, and pipeline_runs
records it. The signed R2/R3 diff added two AssumptionParams fields without the bump, so a run
made with the new fields still records 0.4.0. Kept out of the applied diff because it was not
in what Arsh signed. No table changes: params are stored as JSON.
Diff:
```
core/contracts.py
-CONTRACTS_VERSION = "0.4.0"
+CONTRACTS_VERSION = "0.5.0"
core/schema.sql
--- Baker canonical schema v0.4.0 (matches CONTRACTS_VERSION in core/contracts.py).
+-- Baker canonical schema v0.5.0 (matches CONTRACTS_VERSION in core/contracts.py).
+-- 0.5.0: no table change; AssumptionParams.sent_by and each_way (signed by Arsh 2026-10-29).
tests/contract/test_contracts_v03.py
-    assert c.CONTRACTS_VERSION == "0.4.0"
+    assert c.CONTRACTS_VERSION == "0.5.0"
```
Note on ids: `assumption_id` hashes `canonical_json(params)`, which includes defaults, so the two
new fields change every assumption id once, whether or not they are set. Nothing recomputes a
stored id, so existing case databases read as before; a case re-run under the new code gets new
assumption ids, and an expert's decision on an old id does not carry over to the new one. No
pilot case exists yet. If ids must stay stable, the fields could be left out of the dump when
unset (`Field(default=(), exclude_if=lambda v: not v)`, which needs pydantic 2.11 or later;
pyproject allows 2.7). Not proposed as a diff unless Arsh wants it.
SIGNED by Arsh on 2026-10-30 at 01:26Z ("i sign it", validation thread). APPLIED on
claude/project-thread-ds0ify (#172), the three edits above and nothing else.

## 2026-10-29 claude/project-thread-6i2msb-case04: sign case04's key and assumption sheet
File: eval/gold/case04/gold.jsonl, eval/gold/case04/assumptions.jsonl (new)
Why: case04 is the held-out set for the testability step's go/no-go (plans/agentic.md, approved
by Arsh 2026-10-27 17:29Z: "held-out synthetic claims with signed sheets, written by someone
other than the prompt's author"; change 8: gold needs his signature before merge). A builder
who never read the step's prompt, code, tests or demo claims drafted all 48 claims and 85 sheet
rows. `eval/gold/` is human-owned, so the signed copies are Arsh's to write. Until they exist,
`eval/run_pipeline.py` reports case04's key and sheet as drafts, the testability step refuses
to run on the draft sheet, and no go/no-go is given. Once they exist it picks them up and
reports both as signed (`key_status`, `sheet_status`). case04 stays out of `make eval` and every
merge gate. Arsh reads `eval/synthetic/case04/SIGNING_SHEET.md` (its count tables, the claims
and the assumption rows) and may change any verdict or row first; the commands below copy the
drafts as they stand.
Diff: on main after the case04 PR merges, from the repo root (macOS and GNU sed):
   D=$(date -u +%Y-%m-%d); T=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   mkdir -p eval/gold/case04
   sed -e "s/\"labeled_by\":\"DRAFT (case04 builder, not signed by Arsh)\"/\"labeled_by\":\"Arsh, $D\"/" \
       -e "s/\"labeled_at\":\"2026-10-29T00:00:00Z\"/\"labeled_at\":\"$T\"/" \
       eval/synthetic/case04/draft_gold.jsonl > eval/gold/case04/gold.jsonl
   sed -e "s/\"labeled_by\": \"DRAFT (case04 builder, not signed by Arsh)\"/\"labeled_by\": \"Arsh, $D\"/" \
       eval/synthetic/case04/draft_assumptions.jsonl > eval/gold/case04/assumptions.jsonl
   grep -c DRAFT eval/gold/case04/gold.jsonl eval/gold/case04/assumptions.jsonl
The last line must print 0 for both files. The copies are the drafts with only `labeled_by`
(and, in the key, `labeled_at`) changed: 48 key lines and 85 sheet rows, and both then report
as signed (checked on a scratch copy with bash, 2026-10-29).
SIGNED by Arsh on 2026-10-29 at 04:31Z ("yeah i approve", project thread "Build agents into the
audit"), the key and sheet as they stood after the second blind read (22 supported,
12 contradicted, 14 unproven), in reply to an offer to copy them into eval/gold for him. He was
away from his Mac, so Claude APPLIED it at his request on this branch (PR #170), before the
merge, with these commands and D=2026-10-29, T=2026-10-29T04:31:25Z. Nothing else changed.

## 2026-10-30 claude/project-thread-6i2msb-aliases: person aliases, the other names the expert gives a person
File: core/schema.sql, core/contracts.py
Why: on case04's testability go/no-go (Arsh's Mac run, 2026-10-30, NO-GO), 11 of the 32 claims
the agent did not convert failed on an affidavit designation: SUBJECT-1, HAL, DEZ, the DRIVER,
CW-1. case04's affidavit defines them ("HAL = SUBJECT-1 = HALLORAN (Item 1); DEZ = the DRIVER =
SUBJECT-3 = OKAFOR (Item 3)"), but a person in Mabillon has one name ("Owen Halloran"), so code
matches only "HALLORAN" or the whole name. Neither the code filler nor the agent can test those
claims, and an agent answer that writes "SUBJECT-1" is refused ("matches no person the expert
created"). Real affidavits use designations like these all the time, so this is a product gap,
not only an agent gap (`plans/testability-no-go.md`). Today the expert's only way round it is a
second person named "SUBJECT-1", which nothing ties to Halloran's phone.
What the table holds (agreed with the validation thread, which owns the filler): each alias
belongs to one person an expert created, and only an expert enters one, never a model. Code
matches an alias whole, in any case, with the filler's word-boundary rules. An alias that would
also match another person (their whole name, their surname or an alias of theirs) is refused when
entered, as `add_person` refuses an ambiguous name today, and so is an alias with no letter or
digit; an alias two persons share matches neither. An alias is matched whole only: the surname
rule (a bare "HALLORAN" for "Owen Halloran") applies to the person's name, never to an alias, so
"Big Owen" never matches a bare "Owen". One reader in `core/identity` gives each person's name
and aliases apart (`person_names(conn) -> {person_id: (name, [aliases])}`, shared aliases
dropped) for the filler and the testability step. Entering or
removing one is an audit-log entry (`person.alias.add`, `person.alias.remove`). Reports list
every alias as a limitation, beside the device-owner stipulations, because a check can rest on
it. The bundle carries the table like every other (`core/bundle/export.py` exports every table
the schema defines). A case database made under 0.5.0 is not upgraded in place, as before; code
reads a database with no `person_aliases` table as having no aliases.
Diff, core/schema.sql (header):
--- Baker canonical schema v0.5.0 (matches CONTRACTS_VERSION in core/contracts.py).
+-- Baker canonical schema v0.6.0 (matches CONTRACTS_VERSION in core/contracts.py).
+-- 0.6.0: person_aliases, the other names an expert gives a person (signed by Arsh <date>).
 -- 0.5.0: no table change; AssumptionParams.sent_by and each_way (signed by Arsh 2026-10-29).
Diff, core/schema.sql (after `CREATE TABLE persons (...)`):
+-- Other names an expert gives a person, as the government document writes them: a designation
+-- ("SUBJECT-1", "CW-1", "the DRIVER") or a nickname ("HAL"). Only an expert enters one, never a
+-- model. Code matches an alias whole, in any case. An alias that would also match another
+-- person is refused when entered, and an alias two persons share matches neither. Reports list
+-- every alias as a limitation.
+CREATE TABLE person_aliases (
+    person_id      TEXT NOT NULL REFERENCES persons(id),
+    alias          TEXT NOT NULL COLLATE NOCASE CHECK (length(trim(alias)) BETWEEN 1 AND 120),
+    created_by     TEXT NOT NULL CHECK (created_by LIKE 'expert:%'),
+    created_at_utc TEXT NOT NULL,
+    PRIMARY KEY (person_id, alias)
+);
Diff, core/contracts.py:
-CONTRACTS_VERSION = "0.5.0"
+CONTRACTS_VERSION = "0.6.0"
Nothing else in either file. No enum, model or verdict rule changes; `core/audit/rules.py` is
untouched. Once signed, the PR applies these three edits and adds: `add_alias` and
`remove_alias` expert actions (remove_person removes a person's aliases first, logged), an "Also
called" field on the people page, the testability step's person lookups and the report's
limitations, the eval's case setup reading each case's aliases from its generated case.json, and
tests that fail first. The filler's matching (`_name_spans` over name plus aliases) is the
validation thread's PR, after this one.
SIGNED by Arsh on 2026-10-30 at 23:08Z ("i sign it", project thread "Build agents into the
audit"), in reply to the request to sign this entry. APPLIED on
claude/project-thread-6i2msb-aliases: the three edits above, with <date> as 2026-10-30, and
nothing else in either file.

## 2026-10-31 claude/project-thread-6i2msb-case05: sign case05's key and assumption sheet
File: eval/gold/case05/gold.jsonl, eval/gold/case05/assumptions.jsonl (new)
Why: case04's go/no-go run (2026-10-30) spent it as held-out data, so the next testability
go/no-go needs a new held-out case (plans/testability-no-go.md, step 4; Arsh chose to build it
on 2026-10-31 at 17:09Z). A builder who never read the step's prompt, code, tests or demo
claims, or case04's results, drafted all 48 claims and 86 sheet rows under case04's design, and
a second blind reader checked them (13 findings, answered in the signing sheet). `eval/gold/` is
human-owned, so the signed copies are Arsh's to write. Until they exist, `eval/run_pipeline.py`
reports case05's key and sheet as drafts, the testability step refuses to run on the draft
sheet, and no go/no-go is given. Once they exist it reports both as signed (`key_status`,
`sheet_status`). case05 stays out of `make eval` and every merge gate. Arsh reads
`eval/synthetic/case05/SIGNING_SHEET.md` (its count tables, the claims, the assumption rows, the
second read and the alias matches inside quotes) and may change any verdict or row first; the
commands below copy the drafts as they stand.
Diff: on main after the case05 PR merges, from the repo root (macOS and GNU sed):
   D=$(date -u +%Y-%m-%d); T=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   mkdir -p eval/gold/case05
   sed -e "s/\"labeled_by\":\"DRAFT (case05 builder, not signed by Arsh)\"/\"labeled_by\":\"Arsh, $D\"/" \
       -e "s/\"labeled_at\":\"2026-10-31T00:00:00Z\"/\"labeled_at\":\"$T\"/" \
       eval/synthetic/case05/draft_gold.jsonl > eval/gold/case05/gold.jsonl
   sed -e "s/\"labeled_by\": \"DRAFT (case05 builder, not signed by Arsh)\"/\"labeled_by\": \"Arsh, $D\"/" \
       eval/synthetic/case05/draft_assumptions.jsonl > eval/gold/case05/assumptions.jsonl
   grep -c DRAFT eval/gold/case05/gold.jsonl eval/gold/case05/assumptions.jsonl
The last line must print 0 for both files. The copies are the drafts with only `labeled_by`
(and, in the key, `labeled_at`) changed: 48 key lines and 86 sheet rows, and both then report
as signed (checked on a scratch copy with bash, 2026-10-31).
SIGNED by Arsh on 2026-10-31 at 23:26Z ("approve", project thread "Build agents into the
audit"), the key and sheet as they stood after the second blind read (23 supported,
12 contradicted, 13 unproven). APPLIED on claude/project-thread-6i2msb-case05 (#189) with the
commands above, D=2026-10-31: only `labeled_by` and `labeled_at` changed.

## 2026-10-31 claude/project-thread-ds0ify: schema header dates for 0.5.0
File: core/schema.sql (header comment only)
Why: the 0.5.0 line says the change was signed on 2026-10-29. The two AssumptionParams fields
were signed then (R2/R3), but the version bump itself was signed on 2026-10-30 at 01:26Z (the
"CONTRACTS_VERSION for the R2/R3 fields" entry above). Found in review of #172. No table, field
or version change; wording only.
Diff:
```
core/schema.sql
--- 0.5.0: no table change; AssumptionParams.sent_by and each_way (signed by Arsh 2026-10-29).
+-- 0.5.0: no table change; AssumptionParams.sent_by and each_way (fields signed by Arsh
+-- 2026-10-29; version bump signed 2026-10-30).
```

## 2026-10-31 claude/project-thread-ds0ify: case events, the dated events the document defines
File: core/schema.sql, core/contracts.py
Why: affidavits define an event once and then date later claims only by it: `On Thursday, March
26, 2026, officers searched FERRO's storage unit (the "SEARCH")`, then "Two days before the
SEARCH, the BUYER offered ...". Code reads only a date the claim writes itself, so such a claim
is refused ("window start is not a date the claim states"), and a model's window for it is
refused too, rightly, because the model guesses the edges. In the case04 alias replay (filler
only, Arsh's recorded answers, development data), 8 of the 11 remaining window or quote
refusals are dated by an event or by the sentence before. Arsh chose to add expert-entered
events on 2026-10-31 at 23:38Z (decision card, validation thread). Plan:
`plans/case-events.md`.
What the table holds: each event the expert enters, by its name as the document writes it
("SEARCH", "KEDZIE YARD theft"), with the first and last wall-clock day it covers as the
document gives them, the government-document paragraph that defines it, and the defining words
copied from that paragraph (`On Thursday, March 26, 2026, officers searched FERRO's storage unit
on North Pulaski Road (the "SEARCH")`). Code checks the defining words verbatim against the
paragraph's stored text when the event is entered and refuses the entry otherwise, so every
window built from an event traces to the document (Grok Product on #190). Only an expert enters
one, never a model. Code matches the name whole, in
any case, with the filler's word-boundary rules; a name that would also match a person (name,
surname or alias) or another event is refused when entered. That check is in code, with Unicode
case folding: the column's `COLLATE NOCASE` folds ASCII only and is a backstop, not the rule. Entering or removing one is an
audit-log entry (`case.event.add`, `case.event.remove`). Reports list every event as a
limitation, with its defining words and paragraph beside its days, because a check can rest on
it. Entering or removing an event after a run marks that run's verdicts "Not current", as a
person or alias change does today (`core/review/status.case_changed_after`, `case.event.%`).
The bundle carries the table like every other. A
case database made under 0.6.0 is not upgraded in place; code reads a database with no
`case_events` table as having no events.
What code reads from it (in `assumption_filler.py`, not frozen, an allow list): only one-day
events, only whole days: "on the day of X", "the day before X", "N days before X", "the day
after X", "N days after X". The days are wall-clock days, read exactly as a date the claim
writes itself: "two days before the SEARCH" becomes the wall-clock day March 24, 2026, from
00:00 to the next day's 00:00, placed in the phone's zone by the filler's existing zone rule
(`_zoned_window`), so a day with a clock change is 23 or 25 hours long and is tested. Everything else stays refused, including "in the days before X",
"shortly before", "the night of X", "after X" with no count, and any relation to a multi-day
event. No verdict rule changes.
Diff, core/schema.sql (header):
--- Baker canonical schema v0.6.0 (matches CONTRACTS_VERSION in core/contracts.py).
+-- Baker canonical schema v0.7.0 (matches CONTRACTS_VERSION in core/contracts.py).
+-- 0.7.0: case_events, the dated events the document defines (signed by Arsh <date>).
 -- 0.6.0: person_aliases, the other names an expert gives a person (signed by Arsh 2026-10-30).
Diff, core/schema.sql (after `CREATE TABLE person_aliases (...)`):
+-- Events the government document defines and later claims are dated by ("the SEARCH"), with
+-- the first and last wall-clock day (YYYY-MM-DD) the document gives each, and the paragraph
+-- and words that define it (checked verbatim against the paragraph). Only an expert enters
+-- one, never a model. Code matches a name whole, in any case. A name that would also
+-- match a person or another event is refused when entered. Reports list every event as a
+-- limitation.
+CREATE TABLE case_events (
+    name           TEXT PRIMARY KEY COLLATE NOCASE
+                   CHECK (length(trim(name)) BETWEEN 1 AND 120),
+    first_day      TEXT NOT NULL
+                   CHECK (first_day GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
+    last_day       TEXT NOT NULL
+                   CHECK (last_day GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
+                          AND last_day >= first_day),
+    paragraph_id   TEXT NOT NULL REFERENCES govdoc_paragraphs(id),
+    defined_as     TEXT NOT NULL CHECK (length(trim(defined_as)) BETWEEN 1 AND 2000),
+    created_by     TEXT NOT NULL CHECK (created_by LIKE 'expert:%'),
+    created_at_utc TEXT NOT NULL
+);
Diff, core/contracts.py:
-CONTRACTS_VERSION = "0.6.0"
+CONTRACTS_VERSION = "0.7.0"
Nothing else in either file. No enum, model or verdict rule changes; `core/audit/rules.py` is
untouched. Once signed, one PR applies these three edits and adds: `add_event` and
`remove_event` expert actions (logged, with the verbatim check), an events list on the case
setup page, the report's limitations, "Not current" after an event change, the filler reading
the allow list above, the eval's case setup reading events from
a case.json that has them (case04 and case05 left as built), the contracts version test, and
tests that fail first.
SIGNED by Arsh on 2026-11-01 at 18:47Z ("approve", validation thread), in reply to the request
to sign this entry. APPLIED on claude/project-thread-ds0ify: the three edits above, with <date>
as 2026-11-01, and nothing else in either file.

## 2026-11-01 claude/project-thread-lt1vdp: sign stance labeling guide v0.4 (told frames, undated denials, "never told")
File: eval/gold/stancedata/LABELING_GUIDE.md and eval/gold/stancedata/README.md (the signed copy
and its pin table), with the matching pin in tests/test_gold_stancedata.py
Why: draft v0.4 of `eval/stancedata/LABELING_GUIDE.md` adds three families with a fixed answer,
`ovr_told_frame` and `ovr_undated_denial` (complicates traps) and `con_never_told`
(contradicts), which the training generator eval.train 1.6.0 writes. Its last section, "Changes
from v0.3, for Arsh to sign", lists every change and the calls to sign: an act dated after a
denial that names no time stays open, a "never told" report is ruled out by one message that
says it, and three cases stay out of the data until Arsh decides them. Until the signed copy
and its pins match the draft, two tests in tests/test_gold_stancedata.py fail by design, so the
PR cannot merge without Arsh's signature. `eval/gold/` is human-owned. Nothing else there changes:
GO_BAR.md already counts both traps as moved (since 2026-10-15), and the glossaries are
unchanged and stay signed.
Diff: once Arsh signs, on the PR branch from the repo root, with DATE, TIME (UTC) and COMMIT
(the commit Arsh signed) filled in:
   python3 - <<'PY'
   from pathlib import Path
   draft = Path("eval/stancedata/LABELING_GUIDE.md").read_text(encoding="utf-8")
   head = """# Labeling guide for generated stance data

   SIGNED by Arsh on DATE ("approved" in the "Plan a faster, sharper audit engine" thread, TIME
   UTC). This is draft v0.4 of `eval/stancedata/LABELING_GUIDE.md`, unchanged below this
   paragraph since commit COMMIT. It replaces v0.3, signed on 2026-10-14. The calls on its list of
   changes are decided as written: an act dated after a denial that names no time stays open, a
   "never told" report is ruled out by one message that says it, and three cases stay out of the
   data until Arsh decides them. The Russian-English pairs in `eval/train/glossary.py` and
   `eval/heldout/glossary.py` (rule 6) are unchanged since v0.2 and stay signed. `README.md` next
   to this file pins all three files by SHA-256.
   """
   head = "\n".join(line.removeprefix("   ") for line in head.splitlines()) + "\n"
   body = draft.partition("\nSYNTHETIC.")[2]
   Path("eval/gold/stancedata/LABELING_GUIDE.md").write_text(head + "\nSYNTHETIC." + body,
                                                            encoding="utf-8")
   PY
   sha256sum eval/stancedata/LABELING_GUIDE.md
In eval/gold/stancedata/README.md:
-`LABELING_GUIDE.md` is the stance-data labeling guide, draft v0.3, signed by Arsh on 2026-10-14
-("approved" in the "Custom model for Baker" thread, 21:16 UTC), with the three calls on its
-sign-off page decided as written. It replaces v0.2, signed on 2026-10-12. Below its header it is
+`LABELING_GUIDE.md` is the stance-data labeling guide, draft v0.4, signed by Arsh on DATE
+("approved" in the "Plan a faster, sharper audit engine" thread, TIME UTC), with the calls on
+its list of changes decided as written. It replaces v0.3, signed on 2026-10-14, which replaced
+v0.2 (2026-10-12). Below its header it is
-| `eval/stancedata/LABELING_GUIDE.md` | `40b8618456d264dd5f97377f9f94ceef50a4a05cd6c1d8ecb8f63e8a497c09a2` |
+| `eval/stancedata/LABELING_GUIDE.md` | `<the sha256sum printed above>` |
In tests/test_gold_stancedata.py, the same SHA-256 for "eval/stancedata/LABELING_GUIDE.md", and
the comment above it: "Pinned when Arsh signed guide v0.4 on DATE (v0.3: 2026-10-14)". Then
`python -m pytest -q tests/test_gold_stancedata.py` passes (2 tests). The pin is the draft's
SHA-256 at the commit Arsh signs, so a review change made after the signature needs a new one.
SIGNED by Arsh on 2026-11-01 at 18:47Z ("Sign v0.4 as written" on a decision card, project
thread "Plan a faster, sharper audit engine"), the draft as it stood at commit 78682cf. APPLIED
on claude/project-thread-lt1vdp (#199) with DATE=2026-11-01, TIME=18:47 and COMMIT=78682cf: a
copy of the draft with its header edited, which gives the same file as the script above, with
the card's words in place of "approved" (in the gold README too) and the lines rewrapped. The
draft's own header now says signed, above its SYNTHETIC line and so outside the signed text,
and the pin is that file's SHA-256, `4dafbb8560fa862685a31320f346f1e38bab7eb00ecfe2de2f60876114f7ede1`.
Below the headers both copies are the text at 78682cf byte for byte, and the two tests pass.

## 2026-11-03 claude/project-thread-6i2msb-case-setup: sign the testability prompt v1.1
File: core/audit/prompts/agent_testability.md (signed v1.0; human-owned)
Why: step 3 of plans/testability-pass.md (Arsh chose "Phone designations, then replay" on
2026-11-03 and wrote "i need this to work"). In the case05 go/no-go (NO-GO, conversion 5 of 33)
the second try repeated the first exactly on 23 of the 29 claims that had two, a name the affidavit
gives a number went in "people", a phone and an app went in "accounts", and on calls the
claim's own sentence went in "quoted_text". Draft v1.1 (`docs/prompts/agent_testability.md`)
writes out rules the templates already have; its header lists each change. It is written
generally: its one example name ("TARGET TELEPHONE 2") is no case's. The eval can run the draft
now (`--testability-prompt docs/prompts/agent_testability.md`), reported as a draft with no
go/no-go; the case06 go/no-go needs the signed copy.
Diff: once Arsh signs, replace everything from `<!-- prompt starts -->` down in
`core/audit/prompts/agent_testability.md` with the draft's text from that line down (the same
bytes as in `docs/prompts/agent_testability.md` at the commit Arsh signs), keeping the six
placeholders, and change the header's second line to "v1.1, signed by Arsh on <date> from the
docs/prompts/agent_testability.md draft v1.1 (v1.0: 2026-10-28)." The draft's header then says
signed. `diff <(sed -n '/prompt starts/,$p' docs/prompts/agent_testability.md) <(sed -n
'/prompt starts/,$p' core/audit/prompts/agent_testability.md)` prints nothing.
SIGNED by Arsh on 2026-11-03 at 21:03Z ("approve", project thread "Build agents into the
audit"), the draft v1.1 as it stands in PR #210. APPLIED on claude/project-thread-6i2msb-case06
(#211): the signed copy's body is the draft's from `<!-- prompt starts -->` down (the diff
above prints nothing), its header says v1.1, and the draft's header says signed.

## 2026-11-03 claude/project-thread-6i2msb-case06: sign case06's key and assumption sheet
File: eval/gold/case06/gold.jsonl, eval/gold/case06/assumptions.jsonl (new)
Why: the case05 go/no-go (2026-11-03, NO-GO on conversion, 5 of 33) spent case05, so the next
testability go/no-go needs a new held-out case (plans/testability-pass.md, step 5; Arsh chose
"Phone designations, then replay" on 2026-11-03 and wrote "i need this to work"). A builder who
never read the step's prompt, code, tests or demo, the filler or name code, the eval runner, or
any case04 or case05 result or diagnosis, drafted all 48 claims and 89 sheet rows under case05's
design, from a brief that adds only what the product reads (phone, number and event names in
case.json, and code's window conventions). A second blind reader checked them (10 findings, 9
fixed, 1 kept with a reason, answered in the signing sheet) and rechecked the fixes.
`eval/gold/` is human-owned, so the signed copies are Arsh's to write. Until they exist,
`eval/run_pipeline.py` reports case06's key and sheet as drafts, the testability step refuses to
run on the draft sheet, and no go/no-go is given. case06 stays out of `make eval` and every
merge gate. Arsh reads `eval/synthetic/case06/SIGNING_SHEET.md` (its count tables, the claims,
the assumption rows, the six windows that follow no convention, the SKIP and DUKE naming
departure, and the second read) and may change any verdict or row first; the commands below copy
the drafts as they stand.
Diff: on main after the case06 PR merges, from the repo root (macOS and GNU sed):
   D=$(date -u +%Y-%m-%d); T=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   mkdir -p eval/gold/case06
   sed -e "s/\"labeled_by\":\"DRAFT (case06 builder, not signed by Arsh)\"/\"labeled_by\":\"Arsh, $D\"/" \
       -e "s/\"labeled_at\":\"2026-11-03T00:00:00Z\"/\"labeled_at\":\"$T\"/" \
       eval/synthetic/case06/draft_gold.jsonl > eval/gold/case06/gold.jsonl
   sed -e "s/\"labeled_by\": \"DRAFT (case06 builder, not signed by Arsh)\"/\"labeled_by\": \"Arsh, $D\"/" \
       eval/synthetic/case06/draft_assumptions.jsonl > eval/gold/case06/assumptions.jsonl
   grep -c DRAFT eval/gold/case06/gold.jsonl eval/gold/case06/assumptions.jsonl
The last line must print 0 for both files. The copies are the drafts with only `labeled_by`
(and, in the key, `labeled_at`) changed: 48 key lines and 89 sheet rows.
SIGNED by Arsh on 2026-11-03 at 21:03Z ("approve", project thread "Build agents into the
audit"), the key and sheet as they stood after the second blind read and its recheck (24
supported, 12 contradicted, 12 unproven; 89 rows), with the conversion bar unchanged (his choice
on the card the same minute: the share of changed claims on the key's verdict is reported beside
it, not a bar). APPLIED on claude/project-thread-6i2msb-case06 (#211) with the commands above,
D=2026-11-03: only `labeled_by` and `labeled_at` changed; `grep -c DRAFT` prints 0 for both, and
both report as signed.

## 2026-11-04 claude/project-thread-6i2msb-case06: sign the testability prompt v1.2
File: core/audit/prompts/agent_testability.md (signed v1.1; human-owned)
Why: Codex on #211 (4168585). v1.1 changed the "handles" rule from v1.0's "handles or display
names exactly as written" to "handles exactly as written ... A name a contact was saved as goes
in quoted_text". The same-account check (`core/audit/checks/identity.py`, `resolve_handle`)
resolves a handle from account names, thread titles, the sender text a report printed and saved
contacts, and `same_account` needs at least two handles and takes no accounts and no quoted
words. So under v1.1 a claim that names accounts by display names had no field for them, and the
testability step could not repair it, which would lower the case06 conversion measure for a
reason that is the prompt's, not the agent's. Draft v1.2 (`docs/prompts/agent_testability.md`)
changes only that rule: display names go in "handles" again; a contact entry's saved name stays
in "quoted_text". It is written from the code and v1.0 and names no case's words. The case06
go/no-go waits for this signature.
Diff: the prompt body changes in one place:
   -- "handles": handles exactly as written, e.g. "@bluefox". A name a contact was saved as goes
   -  in "quoted_text", not here.
   +- "handles": handles or display names exactly as written, e.g. "@bluefox", for an assumption
   +  that names accounts by them. For a contact entry, the name the contact was saved as goes in
   +  "quoted_text", not here.
Once Arsh signs, replace everything from `<!-- prompt starts -->` down in
`core/audit/prompts/agent_testability.md` with the draft's text from that line down (the same
bytes as in `docs/prompts/agent_testability.md` at the commit Arsh signs), and change the
header's second line to "v1.2, signed by Arsh on <date> from the
docs/prompts/agent_testability.md draft v1.2 (v1.1: 2026-11-03; v1.0: 2026-10-28)." The draft's
header then says signed. `diff <(sed -n '/prompt starts/,$p' docs/prompts/agent_testability.md)
<(sed -n '/prompt starts/,$p' core/audit/prompts/agent_testability.md)` prints nothing.
SIGNED by Arsh on 2026-11-04 at 19:44Z ("approve", project thread "Build agents into the
audit"), draft v1.2 as it stands in PR #211 (aedc100). APPLIED on
claude/project-thread-6i2msb-case06 (#211): the signed copy's body is the draft's from
`<!-- prompt starts -->` down (the diff above prints nothing), its header says v1.2, and the
draft's header says signed.

## 2026-11-06 claude/project-thread-qw0rxu: rules 0.5.0, counsel review (option B) and code-checked support (option C)
File: CLAUDE.md, core/contracts.py (0.8.0), core/schema.sql (0.8.0), core/audit/rules.py (0.5.0)
Why: Arsh chose options B and C on 2026-11-06 for the AI-native forensic checker plan
(plan: /mnt/project-files/baker/plans/confirm-rule-b-c.md). Both change who or what can make a
claim SUPPORTED, so they need signed-file changes.
- B: a named defense lawyer (reviewer 'counsel:<name>') can accept evidence. Claims resting on
  it get the new basis counsel_reviewed ("Supported (reviewed by counsel)", work product). It
  never displays or exports as confirmed, and an expert's decision overrides counsel's. In this
  version counsel cannot dismiss items, confirm phone ownership or identity links, or override
  verdicts. A contradiction counsel accepts counts under rule 1b, with "accepted by counsel,
  not an expert" in its reason.
- C: a communication, timing or count claim whose core assumptions all passed their
  deterministic checks, with at least one passing check naming the records it rests on and
  nothing blocking under rules 3d and 3e, is SUPPORTED with the new basis checked ("Supported
  by the records (code checks)"). It cites checks and stipulations, never evidence. Content
  meaning, identity, role and absence claims are excluded.
- Precondition for C (Greptile review on #228): the count check must not pass "exactly N" on a
  curated report, which may omit messages or calls. Count check 1.3.0 makes "exactly" pass only
  on a full extraction, as "at most" already does. It lands in the C apply PR, before rules
  0.5.0 takes effect, with an audit of every other check that can pass on a curated report.
- Basis order: confirmed, then checked, then counsel_reviewed, then ai_reviewed.
Measured (synthetic only, scratch worktree on main fe829fc with these diffs and the invariants
change below; not on main):
- `make eval-model-free`: case01 unreviewed accuracy 0.55 -> 0.70 (C05, C09, C12 become
  SUPPORTED checked; all three are gold-supported), 0 false supported. After the simulated
  expert: 1.00, 0 false supported, unchanged. Without the count check fix C03 ("exactly", on a
  curated report) was also promoted, for 0.75; it is gold-supported, but only by luck.
- `make eval-hostile`: none of the 7 structural claims and 0 of 5 model-only claims supported.
- Earlier log-only prototype of C on case04 and case05: 10 of 22 and 10 of 23 gold-supported
  claims promoted, 0 false. case02 not run (held out); the apply PR's `make eval` reports it.
- Real runs use filler-made assumptions, not the gold sheets. C's 0-false result is unmeasured
  there, and on real exports.
- Full test suite (case02 tests excluded) with these diffs: 3806 passed, 13 failed. Every
  failure is an expected change the apply PRs update: version pins (contracts 0.8.0, rules
  0.5.0), the new enum values, decision 6 wording ("await an expert"), the plain-language
  lines that read rule text (test_why_lines, test_first_read_fixes), and tests that assume an
  unreviewed run has nothing SUPPORTED (test_simulated_expert, test_demo, test_start_case).
Apply PRs (not signed files, after approval): count check 1.3.0 (above), core/audit/invariants.py (a checked SUPPORTED
cites passing checks on every core assumption and no evidence; counsel_accepted counts as an
acceptance; the diff below), status and report labels for the three bases, bundle verify,
core/review/actions.py counsel actor that refuses to overwrite an expert review, activity
trail, flags, the demo answer key, tests and a changelog entry. Cases made under schema 0.7.0
cannot store counsel reviews and need a fresh run.
Diff (git diff against main fe829fc):
```diff
diff --git a/CLAUDE.md b/CLAUDE.md
index 2ff691d..f9d2ffe 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -24,17 +24,25 @@ with the reason and the exact diff you want, then finish the rest of your task w
 ## Evidence rules
 - The LLM never decides verdicts. It only labels individual pieces of evidence.
   Verdicts come from `core/audit/rules.py`.
-- A claim is never SUPPORTED on a model's stance label alone. In the alpha (rules 0.2.0) an expert
-  must accept its supporting evidence (accepted). An AI reviewer acceptance (ai_accepted) only sorts
-  evidence for the expert and never makes a claim SUPPORTED; such a claim stays UNPROVEN, awaiting
-  expert review. AI-only coverage of event assumptions can return only after a local model accepts
-  zero overreach traps on the signed probe set, and only through a change to `core/audit/rules.py`
-  that bumps RULE_VERSION.
+- A claim is never SUPPORTED on a model's stance label alone. Under rules 0.5.0 a SUPPORTED rests on
+  one of three things, and the report names which:
+  - confirmed: an expert accepted its supporting evidence (accepted).
+  - counsel_reviewed: a named defense lawyer accepted some of it (counsel_accepted). This is work
+    product for the lawyer, never expert opinion: it never displays or exports as confirmed, and
+    an expert's decision always overrides counsel's. Counsel never dismisses items, confirms
+    stipulations or identity links, or overrides verdicts.
+  - checked: for communication, timing and count claims only, every core assumption passed its
+    deterministic checks against the records, and no model label or reviewer was used.
+  An AI reviewer acceptance (ai_accepted) only sorts evidence for the reviewer and never makes a
+  claim SUPPORTED; such a claim stays UNPROVEN, awaiting review. AI-only coverage of event
+  assumptions can return only after a local model accepts zero overreach traps on the signed probe
+  set, and only through a change to `core/audit/rules.py` that bumps RULE_VERSION.
 - Every derived record carries a `source_ref` back to the original artifact.
-- Every displayed item carries a provenance tier: observed, derived, inferred, ai_reviewed or confirmed.
-  ai_reviewed means the local AI reviewer accepted it. confirmed means a human expert accepted it.
-  Under rules 0.2.0 every SUPPORTED verdict is confirmed.
-  ai_reviewed never displays or exports as confirmed, and a human decision always overrides it.
+- Every displayed item carries a provenance tier: observed, derived, inferred, ai_reviewed,
+  counsel_reviewed or confirmed. ai_reviewed means the local AI reviewer accepted it.
+  counsel_reviewed means a named defense lawyer accepted it. confirmed means a human expert
+  accepted it. Neither ai_reviewed nor counsel_reviewed ever displays or exports as confirmed. A
+  human decision always overrides the AI reviewer, and an expert's decision overrides counsel's.
 - The AI reviewer only reviews evidence items. It never confirms identity links or claims.
 - The AI reviewer runs on the local model in core/. Only the stance labeler may use a cloud model
   in core/. The AI reviewer, claim proposal and assumption filling stay local.
diff --git a/core/audit/rules.py b/core/audit/rules.py
index bdf305f..f72059e 100644
--- a/core/audit/rules.py
+++ b/core/audit/rules.py
@@ -6,12 +6,12 @@ back on an assumption. Every number of a rule below is cited by the reasons it p
 
 Inputs are filtered first: assumptions, evidence and checks that belong to another claim are
 ignored (and the reasons say how many). An evidence item's status is its latest review
-(open, ai_accepted, accepted, dismissed); its tier is the tier of the record and never says
-whether it was reviewed.
+(open, ai_accepted, counsel_accepted, accepted, dismissed); its tier is the tier of the
+record and never says whether it was reviewed.
 
 Rule 1. Contradiction. The claim is CONTRADICTED if any core assumption has
     (a) a deterministic check that failed, or
-    (b) a contradicting evidence item that an expert accepted.
+    (b) a contradicting evidence item that an expert or counsel accepted.
     A failed check on an assumption an agent proposed (agent_proposed: the testability step's,
     core/audit/testability.py, in the claim only because an examiner accepted the proposal)
     counts under (a) only once an expert confirms that failure (confirmed_fails) (rules 0.4.0,
@@ -25,7 +25,7 @@ Rule 1. Contradiction. The claim is CONTRADICTED if any core assumption has
     0.3.0, Arsh, 2026-10-19, PR #90 URGENT FIX: on the signed probe set the local 14B scored 58%
     contradicts precision against a bar of 90%). The claim stays UNPROVEN, the item blocks
     SUPPORTED until the expert dismisses it (rule 3d), and the screen and the report say
-    "Contradiction found, confirm to finalize". It counts once the expert accepts it.
+    "Contradiction found, confirm to finalize". It counts once the expert (or counsel) accepts it.
     The one way back for an unaccepted label is _AUTO_CONTRADICT, a versioned set of claim
     types, EMPTY in 0.3.0. For a claim type in it, an item not dismissed whose record is
     observed or derived, or that the AI reviewer accepted, counts again (the 0.2.2 rule), except
@@ -44,6 +44,9 @@ Rule 2. Coverage of one core assumption. It is covered when, and only when, one
     (a) every deterministic check on it passed (at least one ran) -> tier derived;
     (b) an expert accepted a supporting item on it whose record is observed or derived
         -> tier confirmed;
+    (b') counsel (a named defense lawyer, reviewer 'counsel:<name>') accepted a supporting item
+        on it whose record is observed or derived -> tier counsel_reviewed (rules 0.5.0,
+        Arsh, 2026-11-06, option B: work product, never shown as expert-confirmed);
     (c) the AI reviewer accepted a supporting item on it whose record is observed or derived,
         and its kind is in _AI_MAY_COVER -> tier ai_reviewed. For the alpha that set is EMPTY,
         so AI review alone covers nothing (Arsh, 2026-10-07, decision 6: on his signed probe
@@ -65,9 +68,12 @@ Rule 3. SUPPORTED needs all of:
     (a) the claim has at least one core assumption;
     (b) every core assumption is covered (rule 2);
     (c) at least one supporting item on a core assumption, whose record is observed and whose
-        label an expert accepted (CLAUDE.md: never SUPPORTED on a model label alone, nor
-        without one). An AI acceptance does not satisfy this while _AI_MAY_COVER is empty
-        (decision 6): in the alpha the expert accepts the key evidence for every SUPPORTED;
+        label an expert or counsel accepted (CLAUDE.md: never SUPPORTED on a model label
+        alone). An AI acceptance does not satisfy this while _AI_MAY_COVER is empty
+        (decision 6). Or, for a claim type in _CODE_MAY_SUPPORT only (rule 3c', 0.5.0, Arsh,
+        2026-11-06, option C): every core assumption is covered by passing checks (tier
+        derived, rule 2a) and at least one passing check on a core assumption names the
+        records it rests on. No model label and no reviewer is used, and the basis is checked;
     (d) no complicating item that is not dismissed, no counting contradiction and no failed
         check on any assumption of the claim, core or not;
     (e) the core assumptions include the kind the claim type turns on: identity for a
@@ -78,11 +84,19 @@ Rule 3. SUPPORTED needs all of:
     (f) for identity, role and content-meaning claims, no core assumption is covered by AI
         review alone (a role template may be an event assumption, but who directed whom is
         interpretation). Rules 2c, 3e and 3f: Arsh, 2026-10-07, decision 5.
-    supported_basis is confirmed only when no coverage and no cited support rests on the AI
-    reviewer alone; otherwise ai_reviewed, and the reasons say so. Under decision 6 every
-    SUPPORTED is confirmed; the ai_reviewed path stays for when AI coverage returns. Reports
-    show the two differently. A human decision always overrides the AI reviewer, through the
-    item's latest review.
+    supported_basis, in this order (0.5.0):
+        confirmed         an expert accepted the cited support, and no core assumption is
+                          covered by counsel or the AI reviewer alone;
+        checked           rule 3c' holds: the claim rests on code checks, and no item
+                          accepted by counsel or the AI reviewer is cited;
+        counsel_reviewed  some cited support or coverage rests on counsel, none on the AI
+                          reviewer alone;
+        ai_reviewed       otherwise. Under decision 6 nothing reaches it; the path stays for
+                          when AI coverage returns.
+    Reports show each basis differently, and counsel_reviewed never shows or exports as
+    confirmed. A human decision always overrides the AI reviewer, and an expert's decision
+    overrides counsel's (core/review/actions.py refuses a counsel review over an expert one),
+    through the item's latest review.
 
 Rule 4. Otherwise UNPROVEN, with a reason naming each core assumption left uncovered.
 
@@ -98,6 +112,11 @@ unaccepted label is UNPROVEN under 0.3.0 until the expert confirms the contradic
 proposed counts only once an expert confirms the failure. A call that passes no agent_proposed
 decides exactly as 0.3.0 did. A claim decided CONTRADICTED under 0.3.0 on such a failed check
 alone is UNPROVEN under 0.4.0 until the expert confirms it.
+0.5.0 (Arsh, 2026-11-06, options B and C of the checker plan) adds rule 2b' and counsel
+acceptance under rules 1b and 3c (option B), and rule 3c' with the checked basis (option C).
+A case with no counsel review decides as 0.4.0 did, except that a COMMUNICATION, TIMING or
+COUNT claim whose core assumptions all passed their checks, with nothing blocking, is
+SUPPORTED (checked) under 0.5.0 where 0.4.0 left it UNPROVEN awaiting an expert.
 """
 
 from __future__ import annotations
@@ -128,16 +147,24 @@ from core.contracts import (
     verdict_id,
 )
 
-RULE_VERSION = "0.4.0"
+RULE_VERSION = "0.5.0"
 
 _CITABLE_RECORD = frozenset({ProvenanceTier.OBSERVED, ProvenanceTier.DERIVED})
 _REVIEWED = frozenset({EvidenceStatus.AI_ACCEPTED, EvidenceStatus.ACCEPTED})
+# rules 1b, 2b, 2b', 3c: human acceptances (an expert's or counsel's)
+_HUMAN_ACCEPTED = frozenset({EvidenceStatus.ACCEPTED, EvidenceStatus.COUNSEL_ACCEPTED})
 # rule 2(c): assumption kinds AI review alone may cover. Empty for the alpha (decision 6);
 # 0.1.0 had {EVENT}. Refill only after a local model accepts 0 traps on the signed probe set.
 _AI_MAY_COVER: frozenset[AssumptionKind] = frozenset()
 # rule 3(c): review statuses whose supporting label can carry a SUPPORTED. AI_ACCEPTED counts
 # only while AI review may cover something.
-_SUPPORT_ACCEPTED = _REVIEWED if _AI_MAY_COVER else frozenset({EvidenceStatus.ACCEPTED})
+_SUPPORT_ACCEPTED = _HUMAN_ACCEPTED | _REVIEWED if _AI_MAY_COVER else _HUMAN_ACCEPTED
+# rule 3c' (0.5.0, option C): claim types code checks alone may make SUPPORTED. Each turns on an
+# identity, time or completeness assumption that a deterministic check tests against records.
+# Never CONTENT_MEANING, IDENTITY, ROLE or ABSENCE: meaning and roles are interpretation, an
+# identity claim rests on links only an expert confirms, and an absence needs an expert to
+# judge coverage. A change to this set bumps RULE_VERSION and needs Arsh's sign-off.
+_CODE_MAY_SUPPORT = frozenset({ClaimType.COMMUNICATION, ClaimType.TIMING, ClaimType.COUNT})
 # rule 1(b): claim types whose unaccepted model "contradicts" may count, each mapped to the
 # recorded probe run that qualified it (its results file). EMPTY in 0.3.0: every model
 # contradiction waits for an expert. An entry needs Arsh's sign-off and a RULE_VERSION bump.
@@ -197,7 +224,7 @@ def _counts_as_contradiction(
     claim_type: ClaimType, a: Assumption, e: EvidenceItem, checks_passed: bool
 ) -> bool:
     """Rule 1b, for an item whose stance is contradicts and which is not dismissed."""
-    if e.status is EvidenceStatus.ACCEPTED:
+    if e.status in _HUMAN_ACCEPTED:
         return True
     if claim_type not in _AUTO_CONTRADICT or a.kind is AssumptionKind.MEANING or checks_passed:
         return False
@@ -240,6 +267,7 @@ def _cover(
     )
     support = [e for e in evidence if e.stance is Stance.SUPPORTS and e.tier in _CITABLE_RECORD]
     expert = sorted(e.id for e in support if e.status is EvidenceStatus.ACCEPTED)
+    counsel = sorted(e.id for e in support if e.status is EvidenceStatus.COUNSEL_ACCEPTED)
     ai = sorted(e.id for e in support if e.status is EvidenceStatus.AI_ACCEPTED)
 
     if checks and all(c.outcome is CheckOutcome.PASS for c in checks):
@@ -248,6 +276,9 @@ def _cover(
     elif expert:
         f.covered_tier = ProvenanceTier.CONFIRMED
         f.covering_evidence = expert
+    elif counsel:  # rule 2b', 0.5.0
+        f.covered_tier = ProvenanceTier.COUNSEL_REVIEWED
+        f.covering_evidence = counsel
     elif ai and a.kind in _AI_MAY_COVER:
         f.covered_tier = ProvenanceTier.AI_REVIEWED
         f.covering_evidence = ai
@@ -270,7 +301,8 @@ def _uncovered_reason(f: _Finding) -> str:
     if f.assumption.kind not in _AI_MAY_COVER:
         return (
             f"Rule 2: '{text}' is not covered: {_a(f.assumption.kind.value)} assumption needs a "
-            "passing check or an expert's acceptance; AI review alone does not cover it."
+            "passing check or an expert's or counsel's acceptance; AI review alone does not "
+            "cover it."
         )
     return f"Rule 2: '{text}' is not covered by a passing check or an accepted supporting item."
 
@@ -278,6 +310,8 @@ def _uncovered_reason(f: _Finding) -> str:
 def _how(e: EvidenceItem) -> str:
     if e.status is EvidenceStatus.ACCEPTED:
         return "accepted by an expert"
+    if e.status is EvidenceStatus.COUNSEL_ACCEPTED:
+        return "accepted by counsel, not an expert"
     if e.status is EvidenceStatus.AI_ACCEPTED:
         return "accepted by the AI reviewer"
     return f"model label on an {e.tier.value} record, not reviewed"
@@ -397,7 +431,18 @@ def decide_verdict(
             if f.covered_tier is ProvenanceTier.AI_REVIEWED
         ]
     supports = sorted((e for f in core for e in f.supports), key=lambda e: e.id)
-    if core and not supports:
+    # rule 3c' (0.5.0): code checks alone, for the claim types in _CODE_MAY_SUPPORT
+    code_checks = sorted(
+        (c for f in core for c in ck_by[f.assumption.id] if c.outcome is CheckOutcome.PASS),
+        key=lambda c: c.id,
+    )
+    by_code = (
+        claim.claim_type in _CODE_MAY_SUPPORT
+        and bool(core)
+        and all(f.covered_tier is ProvenanceTier.DERIVED for f in core)
+        and any(c.record_ids for c in code_checks)
+    )
+    if core and not supports and not by_code:
         waiting = sum(
             1
             for f in core
@@ -407,13 +452,19 @@ def decide_verdict(
         if _AI_MAY_COVER:
             blockers.append(
                 "Rule 3c: no supporting item on an observed record has been accepted by the AI "
-                "reviewer or an expert."
+                "reviewer, counsel or an expert."
             )
         else:
             blockers.append(
                 "Rule 3c: no supporting item on an observed record has been accepted by an "
-                "expert. AI review sorts evidence but cannot make a claim supported (decision 6)"
-                + (f"; {waiting} AI-accepted item(s) await an expert." if waiting else ".")
+                "expert or counsel. AI review sorts evidence but cannot make a claim supported "
+                "(decision 6)"
+                + (f"; {waiting} AI-accepted item(s) await review." if waiting else ".")
+                + (
+                    ""
+                    if claim.claim_type not in _CODE_MAY_SUPPORT
+                    else " Rule 3c': code checks alone do not cover every core assumption."
+                )
             )
     for f in findings:
         if not f.assumption.is_core:
@@ -434,7 +485,8 @@ def decide_verdict(
             ]
             blockers += [
                 f"Rule 1b: {e.record_id} contradicts '{f.assumption.text}' ({_how(e)}). "
-                "Contradiction found, confirm to finalize: it counts once an expert accepts it."
+                "Contradiction found, confirm to finalize: it counts once an expert or counsel "
+                "accepts it."
                 for e in f.unconfirmed
             ]
         else:
@@ -452,14 +504,42 @@ def decide_verdict(
         return decide(Verdict.UNPROVEN)
 
     expert_supports = [e for e in supports if e.status is EvidenceStatus.ACCEPTED]
+    counsel_supports = [e for e in supports if e.status is EvidenceStatus.COUNSEL_ACCEPTED]
     ai_covered = any(f.covered_tier is ProvenanceTier.AI_REVIEWED for f in core)
-    if expert_supports and not ai_covered:
+    counsel_covered = any(f.covered_tier is ProvenanceTier.COUNSEL_REVIEWED for f in core)
+    if expert_supports and not ai_covered and not counsel_covered:
         basis = SupportedBasis.CONFIRMED
         cited_support = expert_supports
         reasons.append(
             "Rule 3: every core assumption is covered and the supporting evidence was accepted "
             "by an expert (expert-confirmed)."
         )
+    elif by_code:
+        # rule 3c': the checks carry the claim; no reviewed label is cited
+        reasons.append(
+            "Rule 3c': every core assumption passed its code checks against the records "
+            "(supported by the records, code checks). No model label and no reviewer was used; "
+            "an expert can confirm or override it."
+        )
+        for f in core:
+            reasons.append(
+                f"Rule 2: '{f.assumption.text}' covered at tier derived by "
+                f"{', '.join(f.coverage().cited_ids)}."
+            )
+        return decide(
+            Verdict.SUPPORTED,
+            supported_basis=SupportedBasis.CHECKED,
+            cited_check_ids=tuple(sorted({i for f in core for i in f.covering_checks})),
+            cited_stipulation_ids=tuple(sorted({i for f in core for i in f.covering_stipulations})),
+        )
+    elif (expert_supports or counsel_supports) and not ai_covered:
+        basis = SupportedBasis.COUNSEL_REVIEWED
+        cited_support = expert_supports + counsel_supports
+        reasons.append(
+            "Rule 3: every core assumption is covered, and some of the support was accepted by "
+            "counsel, not an expert (reviewed by counsel, work product). An expert can confirm "
+            "or override it."
+        )
     else:
         basis = SupportedBasis.AI_REVIEWED
         cited_support = supports
diff --git a/core/contracts.py b/core/contracts.py
index b0654a9..a28efa8 100644
--- a/core/contracts.py
+++ b/core/contracts.py
@@ -19,7 +19,7 @@ from typing import Literal, Protocol
 from pydantic import BaseModel, ConfigDict, Field, model_validator
 
 # Bump on every change to this file or core/schema.sql. pipeline_runs records it.
-CONTRACTS_VERSION = "0.7.0"
+CONTRACTS_VERSION = "0.8.0"
 
 # ---------------------------------------------------------------- enums
 
@@ -29,6 +29,7 @@ class ProvenanceTier(StrEnum):
     DERIVED = "derived"  # computed deterministically from observed data
     INFERRED = "inferred"  # produced by a model; always shown with uncertainty
     AI_REVIEWED = "ai_reviewed"  # accepted by the local AI reviewer; never shown as confirmed
+    COUNSEL_REVIEWED = "counsel_reviewed"  # a named lawyer accepted it; never shown as confirmed
     CONFIRMED = "confirmed"  # an expert explicitly accepted it (logged)
 
 
@@ -106,12 +107,14 @@ class ClaimStatus(StrEnum):
 class EvidenceStatus(StrEnum):
     OPEN = "open"
     AI_ACCEPTED = "ai_accepted"  # local AI reviewer accepted; a human decision overrides it
-    ACCEPTED = "accepted"
+    COUNSEL_ACCEPTED = "counsel_accepted"  # a named lawyer accepted; an expert overrides it
+    ACCEPTED = "accepted"  # an expert accepted
     DISMISSED = "dismissed"
 
 
 class ReviewerKind(StrEnum):
     AI = "ai"  # the local AI reviewer (core/audit/review.py)
+    COUNSEL = "counsel"  # a named defense lawyer reviewing for work product, not an expert
     EXPERT = "expert"  # a human expert
 
 
@@ -119,6 +122,8 @@ class SupportedBasis(StrEnum):
     """What a SUPPORTED verdict rests on. Reports show the two differently."""
 
     AI_REVIEWED = "ai_reviewed"  # at least one supporting item is only AI-accepted
+    COUNSEL_REVIEWED = "counsel_reviewed"  # rests on an item a lawyer, not an expert, accepted
+    CHECKED = "checked"  # every core assumption passed its code checks; no label, no reviewer
     CONFIRMED = "confirmed"  # every supporting item it cites was accepted by an expert
 
 
@@ -454,6 +459,8 @@ def display_tier(item: EvidenceItem) -> ProvenanceTier:
     """The tier a report shows for an evidence item. The one place this mapping lives."""
     if item.status is EvidenceStatus.ACCEPTED:
         return ProvenanceTier.CONFIRMED
+    if item.status is EvidenceStatus.COUNSEL_ACCEPTED:
+        return ProvenanceTier.COUNSEL_REVIEWED
     if item.status is EvidenceStatus.AI_ACCEPTED:
         return ProvenanceTier.AI_REVIEWED
     return item.tier
@@ -469,7 +476,7 @@ class ReviewDecision(Model):
     evidence_id: str
     seq: int = Field(ge=1)  # 1 for the first review of this item, then 2, 3, ...
     reviewer_kind: ReviewerKind
-    reviewer: str  # 'ai:<model_name>' or 'expert:<name>'
+    reviewer: str  # 'ai:<model_name>', 'counsel:<name>' or 'expert:<name>'
     status: EvidenceStatus
     reason: str = Field(min_length=1)  # one sentence; shown in the report
     model_run_id: str | None  # required for AI, None for an expert
@@ -484,6 +491,13 @@ class ReviewDecision(Model):
                 raise ValueError("the AI reviewer sets only ai_accepted or dismissed")
             if self.model_run_id is None or not self.reviewer.startswith("ai:"):
                 raise ValueError("an AI review needs a model_run_id and an 'ai:' reviewer")
+        elif self.reviewer_kind is ReviewerKind.COUNSEL:
+            # no dismissal in 0.8.0: a lawyer's dismissal would unblock rule 3d on an
+            # expert-confirmed claim with nothing in the verdict to show it
+            if self.status not in (EvidenceStatus.COUNSEL_ACCEPTED, EvidenceStatus.OPEN):
+                raise ValueError("counsel sets only counsel_accepted or open (to undo)")
+            if self.model_run_id is not None or not self.reviewer.startswith("counsel:"):
+                raise ValueError("a counsel review has no model_run_id and a 'counsel:' reviewer")
         else:
             if self.status not in (
                 EvidenceStatus.ACCEPTED,
@@ -565,8 +579,13 @@ class VerdictDecision(Model):
     def _basis_iff_supported(self) -> VerdictDecision:
         _aware(self.decided_at_utc, "decided_at_utc")
         if self.verdict is Verdict.SUPPORTED:
-            if self.supported_basis is None or not self.cited_evidence_ids:
-                raise ValueError("SUPPORTED needs a supported_basis and cited evidence")
+            if self.supported_basis is None:
+                raise ValueError("SUPPORTED needs a supported_basis")
+            if self.supported_basis is SupportedBasis.CHECKED:
+                if self.cited_evidence_ids or not self.cited_check_ids:
+                    raise ValueError("a checked SUPPORTED cites passed checks and no evidence")
+            elif not self.cited_evidence_ids:
+                raise ValueError("SUPPORTED needs cited evidence")
         elif self.supported_basis is not None:
             raise ValueError("supported_basis is only for SUPPORTED")
         return self
diff --git a/core/schema.sql b/core/schema.sql
index 2c09c76..aa98d6a 100644
--- a/core/schema.sql
+++ b/core/schema.sql
@@ -1,4 +1,5 @@
--- Baker canonical schema v0.7.0 (matches CONTRACTS_VERSION in core/contracts.py).
+-- Baker canonical schema v0.8.0 (matches CONTRACTS_VERSION in core/contracts.py).
+-- 0.8.0: counsel reviews and the checked and counsel_reviewed bases (signed by Arsh <date>).
 -- 0.7.0: case_events, the dated events the document defines (signed by Arsh 2026-11-01).
 -- 0.6.0: person_aliases, the other names an expert gives a person (signed by Arsh 2026-10-30).
 -- 0.5.0: no table change; AssumptionParams.sent_by and each_way (signed by Arsh 2026-10-29).
@@ -110,7 +111,7 @@ CREATE TABLE identity_links (
     account_id TEXT NOT NULL REFERENCES accounts(id),
     person_id  TEXT NOT NULL REFERENCES persons(id),
     status     TEXT NOT NULL CHECK (status IN ('proposed', 'confirmed', 'rejected', 'unresolved')),
-    tier       TEXT NOT NULL CHECK (tier IN ('observed', 'derived', 'inferred', 'ai_reviewed', 'confirmed')),
+    tier       TEXT NOT NULL CHECK (tier IN ('observed', 'derived', 'inferred', 'ai_reviewed', 'counsel_reviewed', 'confirmed')),
     basis      TEXT NOT NULL,
     decided_by TEXT,
     decided_at_utc TEXT
@@ -309,7 +310,7 @@ CREATE TABLE assumptions (
     text     TEXT NOT NULL,          -- human-readable rendering; never parsed
     is_core  INTEGER NOT NULL CHECK (is_core IN (0, 1)),
     -- tier at creation; coverage is computed in rules.py and never stored back here
-    tier     TEXT NOT NULL CHECK (tier IN ('observed', 'derived', 'inferred', 'ai_reviewed', 'confirmed'))
+    tier     TEXT NOT NULL CHECK (tier IN ('observed', 'derived', 'inferred', 'ai_reviewed', 'counsel_reviewed', 'confirmed'))
 );
 
 CREATE TABLE evidence_items (
@@ -333,9 +334,9 @@ CREATE TABLE evidence_reviews (
     id             TEXT PRIMARY KEY,  -- 'rv:<evidence_id>#<seq>'
     evidence_id    TEXT NOT NULL REFERENCES evidence_items(id),
     seq            INTEGER NOT NULL CHECK (seq >= 1),
-    reviewer_kind  TEXT NOT NULL CHECK (reviewer_kind IN ('ai', 'expert')),
-    reviewer       TEXT NOT NULL,     -- 'ai:<model_name>' or 'expert:<name>'
-    status         TEXT NOT NULL CHECK (status IN ('open', 'ai_accepted', 'accepted', 'dismissed')),
+    reviewer_kind  TEXT NOT NULL CHECK (reviewer_kind IN ('ai', 'expert', 'counsel')),
+    reviewer       TEXT NOT NULL,     -- 'ai:<model_name>', 'expert:<name>' or 'counsel:<name>'
+    status         TEXT NOT NULL CHECK (status IN ('open', 'ai_accepted', 'accepted', 'counsel_accepted', 'dismissed')),
     reason         TEXT NOT NULL CHECK (length(reason) > 0),
     model_run_id   TEXT REFERENCES model_runs(id),
     model_call_id  TEXT REFERENCES model_calls(id),
@@ -344,6 +345,8 @@ CREATE TABLE evidence_reviews (
     CHECK ((reviewer_kind = 'ai' AND status IN ('ai_accepted', 'dismissed')
                 AND model_run_id IS NOT NULL)
         OR (reviewer_kind = 'expert' AND status IN ('accepted', 'dismissed', 'open')
+                AND model_run_id IS NULL)
+        OR (reviewer_kind = 'counsel' AND status IN ('counsel_accepted', 'open')
                 AND model_run_id IS NULL))
 );
 
@@ -384,7 +387,7 @@ CREATE TABLE verdicts (
     claim_id        TEXT NOT NULL REFERENCES claims(id),
     pipeline_run_id TEXT NOT NULL REFERENCES pipeline_runs(id),
     verdict         TEXT NOT NULL CHECK (verdict IN ('supported', 'contradicted', 'unproven')),
-    supported_basis TEXT CHECK (supported_basis IN ('ai_reviewed', 'confirmed')),
+    supported_basis TEXT CHECK (supported_basis IN ('ai_reviewed', 'confirmed', 'counsel_reviewed', 'checked')),
     rule_version    TEXT NOT NULL,
     reasons_json    TEXT NOT NULL,
     coverage_json   TEXT NOT NULL,     -- AssumptionCoverage per core assumption, as computed
```
Companion change for the apply PR (core/audit/invariants.py is not frozen; shown so the signed
rule and its independent check are read together):
```diff
diff --git a/core/audit/invariants.py b/core/audit/invariants.py
index 8f4f6a9..2b2bf40 100644
--- a/core/audit/invariants.py
+++ b/core/audit/invariants.py
@@ -61,7 +61,7 @@ from core.contracts import (
 )
 from core.enrich import records
 
-ACCEPTED_STATUSES = (EvidenceStatus.AI_ACCEPTED, EvidenceStatus.ACCEPTED)
+ACCEPTED_STATUSES = (EvidenceStatus.AI_ACCEPTED, EvidenceStatus.COUNSEL_ACCEPTED, EvidenceStatus.ACCEPTED)
 
 WORDS = ("guilty", "innocent", "leader", "deleted")
 FORBIDDEN_WORDS = re.compile(rf"\b({'|'.join(WORDS)})\b", re.IGNORECASE)
@@ -289,6 +289,18 @@ def check_decision(
     cited_support = [
         by_id[i] for i in decision.cited_evidence_ids if by_id[i].stance == Stance.SUPPORTS
     ]
+    if decision.supported_basis == SupportedBasis.CHECKED:
+        passed = {c.id for c in checks if c.outcome == CheckOutcome.PASS}
+        core_ids = {a.id for a in assumptions if a.is_core}
+        if cited_support or not decision.cited_check_ids:
+            raise InvariantViolation(f"{claim.id}: a checked SUPPORTED cites checks, not evidence")
+        if not set(decision.cited_check_ids) <= passed:
+            raise InvariantViolation(f"{claim.id}: a checked SUPPORTED cites a check that did not pass")
+        for aid in core_ids:
+            mine = [c for c in checks if c.assumption_id == aid]
+            if not mine or any(c.outcome != CheckOutcome.PASS for c in mine):
+                raise InvariantViolation(f"{claim.id}: checked SUPPORTED but {aid} lacks passing checks")
+        return
     if not cited_support:
         raise InvariantViolation(f"{claim.id}: SUPPORTED cites no supporting item")
     weak = [
@@ -301,10 +313,13 @@ def check_decision(
             f"{claim.id}: SUPPORTED cites supporting items that are not observed and accepted: "
             f"{weak}"
         )
+    statuses = {e.status for e in cited_support}
     basis = (
         SupportedBasis.CONFIRMED
-        if all(e.status == EvidenceStatus.ACCEPTED for e in cited_support)
+        if statuses == {EvidenceStatus.ACCEPTED}
         else SupportedBasis.AI_REVIEWED
+        if EvidenceStatus.AI_ACCEPTED in statuses
+        else SupportedBasis.COUNSEL_REVIEWED
     )
     if decision.supported_basis != basis:
         raise InvariantViolation(
```

## 2026-11-06 claude/project-thread-qw0rxu: amend rules 0.5.0, exact counts never rest on checks alone
File: core/audit/rules.py (0.5.0, before it merges)
SIGNED by Arsh on 2026-11-06 (23:46Z, he picked "Rule skips exact counts" on the decision card in
the "Research the AI-native forensic analyst pivot" thread). APPLIED on PR #228.
Why: the precondition in the entry above (count check 1.3.0, "exactly" passes only on a full
extraction) would turn the signed assumption sheets of case01 (C03), case03, case04, case05 and
case06 wrong: they expect the count check to pass on those curated reports. Instead of changing
the check and re-signing gold, rule 3c' skips any claim with an "exactly N" core count. The count
check stays 1.2.0. "At most" already passes only on a full extraction, and "at least" holds on
any report. Measured on case01 it gives the same result as the check change: unreviewed accuracy
0.70, 0 false supported, and C03 waits for the expert.
Diff (on top of the entry above):
```diff
         and any(c.record_ids for c in code_checks)
+        # an "exactly N" count can pass on a curated report that leaves records out
+        and not any(f.assumption.params.count_op == "eq" for f in core)
     )
```
The docstring for rule 3c and the 3c blocker reason say the same thing.

## 2026-11-06 claude/project-thread-jvh1pc: allow the license check outside core/ (for when sign-in is turned on)
SIGNED by Arsh on 2026-11-06 22:29Z ("approve" in the "Make Mabillon a desktop app with sign-in"
thread), with the rest of the sign-in privacy wording (plans/desktop-sign-in.md, sections A to D).
To apply on main by a human; CLAUDE.md stays human-edited.
File: CLAUDE.md
Why: sign-in (account/, off by default) adds one network call outside core/: the license check
to account.getmabillon.com. CLAUDE.md limits network calls only inside core/, but its "No
telemetry" line and the privacy promise should name this call before it is ever turned on.
Wording drafted in plans/desktop-sign-in.md (section E) for Arsh's signature. Not needed while
account.SIGNIN_ON is False.
Diff (Data safety, after the line "- No network calls in `core/` except ..."):
+- Outside `core/`, the app's only network call is the license check in `account/client.py`, to
+  account.getmabillon.com: the email at sign-in, then the license id, sign-in token and app
+  version. Never case data. It stays off until sign-in is turned on, and a missing or expired
+  license never blocks opening, reviewing or exporting a case.

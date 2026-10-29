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

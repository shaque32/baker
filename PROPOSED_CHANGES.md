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

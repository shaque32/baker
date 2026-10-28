# Giving a demo

`mabillon demo` opens a ready-made, already-audited case in seconds, so a demo never waits on a
model run. Everything in it is synthetic (case01: two phones, Daniel Petrov's iPhone and
Marcus Reyes's Samsung, mixed English and Russian, seven planted traps).

```
mabillon demo                    # reset the demo case and open it at http://127.0.0.1:8766
mabillon demo --expert "Your Name"   # the name recorded with what you click during the demo
mabillon demo --paired           # also add a UFDR of Item 1, to show what the curated report left out
```

Run it again before every demo: each run deletes the demo case and builds a clean one (about
6 seconds). It uses its own folder (`~/Mabillon/demo/cases`, or `$MABILLON_DEMO/cases`) and its own
port (8766), so it never shows your other cases on a screen share and can run beside a real
`mabillon serve` on 8765. Ctrl+C stops it.

## What is real and what is scripted

Say this if asked; the yellow banner on every page says the same.

| Real (Mabillon's own code) | Scripted (so the demo opens in seconds) |
|---|---|
| Import: read-only copies, SHA-256, coverage ("curated report, cannot show absence") | The evidence labels: key evidence from the signed answer key, labeled the way the answer points; C16's two counter-records labeled complicates on its authorship assumption; everything else labeled irrelevant. No model ran. |
| Assumptions (from the signed assumption sheet), retrieval, every deterministic check (sender, time with time zones, absence, count, contact, identity) | Most expert decisions: "Demo expert (scripted from the answer key)" accepted or dismissed every item, except on C05 and C16's two counter-records, which are left for you |
| The challenge step: code's counter-searches on each claim close to supported, which keep only doubt | |
| The testability agent's machinery on D02 and D03: the product's assumption filler and testability step with their signed prompts, code's checks on every answer (including the claim-only check), the "Proposed by agent" card and the audit log | The model's answers on D02 and D03 (a first answer code refuses, then the agent's answer), and the acceptance of D02's proposal and its contact record by "Demo examiner (scripted from the demo claims)". No model ran. |
| The quote check, the verdict rules (0.3.0), the hash-chained audit log, the report | |

On a real case the local model (Qwen3-14B, on the expert's own computer) labels the evidence and
the expert decides every item. A full case01 run took about 6 to 8 hours on a 24 GB Mac on an
earlier version; the current version has not been timed.

To demo real model labels instead, save a finished synthetic case01 audit as the demo once:

```
mabillon demo --from-case ~/Mabillon/cases/<that case folder>   # only synthetic case01 is accepted
mabillon demo --scripted                                     # back to the scripted demo
```

## Demo-only claims D01 to D03 and `--paired`

These parts of the scripted demo are not in the signed answer key, and are synthetic like the
rest. They come only with the scripted build: a saved audit (`--from-case`) is restored as it
was run, so it holds the 20 answer-key claims and no D01, D02 or D03 (`--paired` always builds
the scripted case).

- **D01** (eval/demo_claims.jsonl), an absence claim read from paragraph 11: "PETROV and REYES
  exchanged no WhatsApp messages between March 20 and March 23, 2026." Mabillon finds no WhatsApp
  record in that window, yet the absence check is inconclusive and the claim stays unproven:
  both phones are examiner-curated reports, which cannot show that something is absent. Use it to
  show that "not found" never becomes "did not happen".
- **D02 and D03** (eval/demo_agent_claims.jsonl) show the testability agent. On each, the
  product's assumption filler gets a scripted first answer that code refuses, for a reason
  validation run 2 saw: D02's writes the phone "Item 1" as an account, D03's names a call with
  no party. The testability step then asks again with code's reasons, and its scripted answer
  passes code's checks. The step runs on these two claims only, CAP 1, with no signed sheet: the
  claim-only check is all it gets, as a real case would. D02's proposal ("Item 1 holds a contact
  saved as "Alex" with the number +1 (212) 555-0182") was accepted when the demo was built, with
  its contact record, so D02 shows the whole path to "Supported (expert-confirmed)". D03's ("At
  about 7:58 p.m. on March 9, 2026, Item 1 placed a call to +1 (212) 555-0122") waits on its
  claim page for you.
- **`mabillon demo --paired`** builds the same scripted case and then imports `item1-full.ufdr`, a
  UFDR of Item 1 that holds records the curated report does not (eval/synthetic/paired.py). It
  is imported after the audit, so every verdict is the same as in the plain demo. The Selection
  tab then shows the paired selection audit (each report record found once, more than once or
  not found in the UFDR, and the records left out near each claim), and C05's page says the UFDR
  holds 4 records within an hour of its messages that the report does not, such as "or sunday
  works too". It never changes a verdict. A plain `mabillon demo` goes back to the case without it;
  a saved audit (`--from-case`) is kept but not used for a `--paired` run.

## The 10-minute flow

Open with this, before the screen: "You stay in charge. Mabillon does not replace the forensic
analyst or make any call for you. It does the searching and scrolling, hands you the exact
records, and nothing counts as supported until you accept it yourself."

1. **Cases, then the case.** One case, nothing else on the screen. Open it. The setup page
   shows the three imported files, each with its SHA-256, and "curated report (examiner-selected;
   cannot show absence)".
2. **Claims queue.** 20 claims from the affidavit plus the scripted demo's D01, D02 and D03: 8
   supported (expert-confirmed), 6 contradicted, 9 unproven. Next up is D03: "Proposed by agent:
   the testability agent proposed assumptions that would make this claim testable". C05 ("Support
   found: do you agree?") and C16 ("2 contradicting or complicating item(s) to review") wait just
   below it.
3. **Live: the expert decides (C05).** Open C05, "need 2 more by friday". The model-side label
   says supports, yet the verdict is unproven: no claim is supported until an expert accepts its
   evidence. Point out the time check: the phone prints the message on 3/13 (UTC), and Mabillon
   converts it to 8:03 p.m. on March 12 in New York, so the claim's date is right. Type a
   one-sentence reason, click **Accept** on both items, then **Re-run verdicts** (rules only, no
   model). C05 turns "Supported (expert-confirmed)" with your name in the audit log.
4. **Live: the challenge step (C16).** Open C16, "got the money, come get it". On every claim
   close to supported, Mabillon runs code's searches for what would undercut it, and keeps only
   doubt. Here its search for someone else using the account found "its ilya btw, dan's at work.
   he left his login on my ipad", marked "found by the challenge step". Retrieval found the
   other one, "using ur insta on my ipad for the audi guy". While either is open, C16 cannot go
   supported. Accept both with a reason (they undercut who typed the message), then **Re-run
   verdicts**: C16 stays unproven, and the report says which item the challenge step found.
   Say it plainly: the search is real, but in this demo the "complicates" label on what it found
   is scripted from the answer key. On a real case the local model labels it, and what the step
   catches with that model is not measured yet.
5. **Live: the testability agent (D03, then D02).** Open D03. It is not tested: the first
   answer named a call with no party, and code refused it; the reason is on the page. The
   testability agent asked again, told why, and its answer is on the card marked "Proposed by
   agent". Open "What code checked": every person, phone and account it names is one the claim's
   own words name, and nothing it proposes is used until you accept it. There is one card and no
   accept-all. Type a one-sentence reason and click **Accept these assumptions**: the log records
   it under your name. Nothing changes yet: the next audit tests D03 with them, if the agent gives
   them again for this claim's text, and the claim's text never changes. Then open D02 for the
   whole path: its proposal was accepted when the demo was built, code's contact check passed,
   its contact record was accepted, and it is "Supported (expert-confirmed)", with "Proposed by
   agent, accepted by examiner" beside the assumption here and in the report. Say it plainly: the
   model's answers on D02 and D03 are scripted, code's checks on them are real, and what the
   agent does with the local model is not measured yet.
6. **The traps (pick three or four from the answer key below).** On each claim open "Why
   (reasons from the verdict rules)" and the Checks table: the reason is written out, with the
   records it rests on.
7. **Report.** The printable claims report: verdicts, cited records with their source rows,
   limitations (the owner stipulations, curated reports), source hashes and the audit log.

Mabillon itself never says guilty, innocent, leader or deleted. A reason or note you type is
yours, so it shows exactly as you wrote it, those words included.

## Answer key: the planted traps

Paragraph numbers are the affidavit's. A quick reading, by a person or a chatbot, falls into
each of these; Mabillon does not.

| Claim | ¶ | The affidavit says | Trap | What Mabillon shows | Verdict |
|---|---|---|---|---|---|
| C10 | 8 | Petrov texted "its done" at 2:31 a.m. on March 5 | Time zone: Item 1 prints UTC | Time check fails: the message was sent 9:31 p.m. March 4 local; Item 2's copy prints 9:31 p.m. | Contradicted |
| C11 | 9 | Reyes got a warning call at 10:05 p.m., and after it Petrov sent "move it tonight" | Time zone across two phones | In one clock the message came 15 minutes before the call; read as printed, the order reverses | Contradicted |
| C05 | 6 | Petrov wrote "need 2 more by friday" on March 12 | Time zone, the other way | Printed 3/13 but sent March 12 local; the claim is right, and only the expert's acceptance makes it supported | Unproven until you accept, then supported |
| C04 | 5 | Petrov first contacted @northstar on March 12 | Handle change: @alex92 became @northstar | Same Telegram user id 5551234 since Feb 20; the absence check finds 10 earlier messages | Contradicted |
| C08 | 7 | Petrov chose the meeting place | Who proposed it | Sender check fails: Reyes sent "lets meet monday 8pm. lot behind kings plaza"; Petrov replied "ok works" | Contradicted |
| C14 | 11 | No contact of any kind March 20 to 23 | WhatsApp gap | Absence check finds 12 SMS, Telegram and call records in the window | Contradicted |
| D01 (demo only) | 11 | No WhatsApp messages March 20 to 23 | Silence read as absence | Absence check finds none but is inconclusive: both phones are curated reports, which cannot show absence | Unproven |
| C15 | 11 | Petrov removed the WhatsApp messages from March 20 to 23 | Silence read as destruction | No WhatsApp rows, none flagged; an absence of artifacts never proves an event, and a curated report cannot show absence | Unproven |
| C16 | 12 | Petrov, on Instagram dp_garage, said "got the money, come get it" | Shared account | The account also wrote "its ilya btw, dan's at work", which the challenge step finds; who typed it is not established | Unproven |
| C19 | 14 | @northstar is the "Alex" saved at 0182 | Second Alex | On Item 2, @northstar asks "who is alex turner?"; the contacts tie the account to 0147, not 0182 | Contradicted |
| C18 | 14 | @northstar is Alexander Sokolov | Name from nowhere | Saved as "Sasha N"; nothing on either phone ties the account to Sokolov | Unproven |
| C20 | 15 | "got the tickets" refers to narcotics | Decoy thread | The thread has seat sections, a ticket PDF and "that show was insane last night": concert context; a meaning claim needs an expert, never a model label alone | Unproven |
| C06, C13 | 6, 10 | The package held narcotics; Petrov directed Reyes | Meaning and role claims | The messages are observed; what they mean is not, and Reyes set the meeting time and place | Unproven |

Supported claims worth one look: C02 and C03 (the handle change counted by user id, not by
handle text) and C17 (Russian, "я волнуюсь за Маркуса", cited in the original).

## After the demo

Log what the expert said in the go/kill scorecard. Ask every time: what format they receive
(UFDR or Cellebrite reports), whether they may use cloud AI on their cases, whether they already
paste reports into ChatGPT or Claude, and whether they would pay per case.

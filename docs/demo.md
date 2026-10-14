# Giving a demo

`baker demo` opens a ready-made, already-audited case in seconds, so a demo never waits on a
model run. Everything in it is synthetic (case01: two phones, Daniel Petrov's iPhone and
Marcus Reyes's Samsung, mixed English and Russian, seven planted traps).

```
baker demo                    # reset the demo case and open it at http://127.0.0.1:8766
baker demo --expert "Your Name"   # the name recorded with what you click during the demo
```

Run it again before every demo: each run deletes the demo case and builds a clean one (about
6 seconds). It uses its own folder (`~/Baker/demo/cases`, or `$BAKER_DEMO/cases`) and its own
port (8766), so it never shows your other cases on a screen share and can run beside a real
`baker serve` on 8765. Ctrl+C stops it.

## What is real and what is scripted

Say this if asked; the yellow banner on every page says the same.

| Real (Baker's own code) | Scripted (so the demo opens in seconds) |
|---|---|
| Import: read-only copies, SHA-256, coverage ("curated report, cannot show absence") | The evidence labels: key evidence from the signed answer key, labeled the way the answer points; everything else labeled irrelevant. No model ran. |
| Assumptions (from the signed assumption sheet), retrieval, every deterministic check (sender, time with time zones, absence, count, contact, identity) | Most expert decisions: "Demo expert (scripted from the answer key)" accepted or dismissed every item, except on C05, which is left for you |
| The quote check, the verdict rules (0.2.0), the hash-chained audit log, the report | |

On a real case the local model (Qwen3-14B, on the expert's own computer) labels the evidence and
the expert decides every item. A full case01 run takes about 6 to 8 hours on a 24 GB Mac.

To demo real model labels instead, save a finished synthetic case01 audit as the demo once:

```
baker demo --from-case ~/Baker/cases/<that case folder>   # only synthetic case01 is accepted
baker demo --scripted                                     # back to the scripted demo
```

## The 10-minute flow

Open with this, before the screen: "You stay in charge. Baker does not replace the forensic
analyst or make any call for you. It does the searching and scrolling, hands you the exact
records, and nothing counts as supported until you accept it yourself."

1. **Cases, then the case.** One case, nothing else on the screen. Open it. The setup page
   shows the three imported files, each with its SHA-256, and "curated report (examiner-selected;
   cannot show absence)".
2. **Claims queue.** 20 claims from the affidavit: 7 supported (expert-confirmed),
   6 contradicted, 6 unproven, and C05 at the top: "Support found: do you agree?".
3. **Live: the expert decides (C05).** Open C05, "need 2 more by friday". The model-side label
   says supports, yet the verdict is unproven: no claim is supported until an expert accepts its
   evidence. Point out the time check: the phone prints the message on 3/13 (UTC), and Baker
   converts it to 8:03 p.m. on March 12 in New York, so the claim's date is right. Type a
   one-sentence reason, click **Accept** on both items, then **Re-run verdicts** (rules only, no
   model). C05 turns "Supported (expert-confirmed)" with your name in the audit log.
4. **The traps (pick three or four from the answer key below).** On each claim open "Why
   (reasons from the verdict rules)" and the Checks table: the reason is written out, with the
   records it rests on.
5. **Report.** The printable claims report: verdicts, cited records with their source rows,
   limitations (the owner stipulations, curated reports), source hashes and the audit log.

Baker itself never says guilty, innocent, leader or deleted. A reason or note you type is
yours, so it shows exactly as you wrote it, those words included.

## Answer key: the planted traps

Paragraph numbers are the affidavit's. A quick reading, by a person or a chatbot, falls into
each of these; Baker does not.

| Claim | ¶ | The affidavit says | Trap | What Baker shows | Verdict |
|---|---|---|---|---|---|
| C10 | 8 | Petrov texted "its done" at 2:31 a.m. on March 5 | Time zone: Item 1 prints UTC | Time check fails: the message was sent 9:31 p.m. March 4 local; Item 2's copy prints 9:31 p.m. | Contradicted |
| C11 | 9 | Reyes got a warning call at 10:05 p.m., and after it Petrov sent "move it tonight" | Time zone across two phones | In one clock the message came 15 minutes before the call; read as printed, the order reverses | Contradicted |
| C05 | 6 | Petrov wrote "need 2 more by friday" on March 12 | Time zone, the other way | Printed 3/13 but sent March 12 local; the claim is right, and only the expert's acceptance makes it supported | Unproven until you accept, then supported |
| C04 | 5 | Petrov first contacted @northstar on March 12 | Handle change: @alex92 became @northstar | Same Telegram user id 5551234 since Feb 20; the absence check finds 10 earlier messages | Contradicted |
| C08 | 7 | Petrov chose the meeting place | Who proposed it | Sender check fails: Reyes sent "lets meet monday 8pm. lot behind kings plaza"; Petrov replied "ok works" | Contradicted |
| C14 | 11 | No contact of any kind March 20 to 23 | WhatsApp gap | Absence check finds 12 SMS, Telegram and call records in the window | Contradicted |
| C15 | 11 | Petrov removed the WhatsApp messages from March 20 to 23 | Silence read as destruction | No WhatsApp rows, none flagged; an absence of artifacts never proves an event, and a curated report cannot show absence | Unproven |
| C16 | 12 | Petrov, on Instagram dp_garage, said "got the money, come get it" | Shared account | The account also wrote "its ilya btw, dan's at work"; who typed it is not established | Unproven |
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

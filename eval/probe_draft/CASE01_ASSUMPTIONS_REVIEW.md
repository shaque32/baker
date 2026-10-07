# case01 assumptions: DRAFT for Arsh's line-by-line review

**Not gold.** In the gold-claims eval mode the pipeline uses these assumptions instead of a model filling the templates, so they are signed like gold. Thread 1 copies the signed file into `eval/gold/case01/`.

How to read it:

- Each claim is broken into the fixed templates the engine can test (`core/audit/assumptions.py`). Parameters are typed; checks never read the sentence.
- **Check** is what the deterministic check should find on case01: pass, fail or inconclusive. A dash means no check exists for that template, so only an accepted stance label can cover it.
- Phone ownership (Item 1 PETROV, Item 2 REYES) is the confirmed case stipulation, not an assumption here.
- **Gaps** are parts of the claim no template can express yet. They are listed, not papered over.
- Windows are the document's dates as wall-clock time in America/New_York; the `.jsonl` holds their UTC form.

| Claim | Gold | Assumptions | Core checks expected | Gaps | Approve? |
|---|---|---|---|---|---|
| C01 | supported | 1 | pass |  | [ ] |
| C02 | supported | 3 | pass, pass, pass | 1 | [ ] |
| C03 | supported | 1 | pass |  | [ ] |
| C04 | contradicted | 1 | fail | 1 | [ ] |
| C05 | supported | 2 | pass, pass | 1 | [ ] |
| C06 | unproven | 3 | pass, pass, - |  | [ ] |
| C07 | supported | 5 | pass, pass, pass, pass, - | 1 | [ ] |
| C08 | contradicted | 2 | -, fail | 1 | [ ] |
| C09 | supported | 2 | pass, pass |  | [ ] |
| C10 | contradicted | 2 | pass, fail |  | [ ] |
| C11 | contradicted | 2 | fail | 1 | [ ] |
| C12 | supported | 2 | pass, pass | 1 | [ ] |
| C13 | unproven | 2 | -, - |  | [ ] |
| C14 | contradicted | 1 | fail |  | [ ] |
| C15 | unproven | 1 | - | 1 | [ ] |
| C16 | unproven | 3 | pass, pass, - |  | [ ] |
| C17 | supported | 3 | pass, pass, - | 1 | [ ] |
| C18 | unproven | 1 | - |  | [ ] |
| C19 | contradicted | 1 | - | 1 | [ ] |
| C20 | unproven | 3 | pass, pass, - |  | [ ] |

## C01: gold supported

> Item 1 contains a contact named "Marc Garage" with the number +1 (212) 555-0122.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Marc Garage<br>account_ids: acct:item1:Phone:+12125550122 | pass | The contact row is observed on Item 1. |

Arsh: [ ] agree  [ ] change ______  Note:

## C02: gold supported

> Between February 20 and March 28, 2026, PETROV exchanged Telegram messages on Item 1 with a single Telegram account, user ID 5551234, which appears under the handle @alex92 and, from March 10, 2026, under the handle @northstar.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `same_account` | yes | channels: Telegram<br>handles: @alex92, @northstar | pass | Both handles resolve to Telegram user id 5551234. |
| 2 | `record_time` | yes | quoted_text: hey its sasha. marc gave me ur name<br>account_ids: acct:item1:Telegram:5551234, acct:item2:Telegram:5551234<br>window: "February 20, 2026" (America/New_York, local wall clock) | pass | The first message: 7:02 PM EST Feb 20, printed 2/21 in UTC. |
| 3 | `record_time` | yes | quoted_text: not now<br>person_ids: person:petrov<br>window: "March 28, 2026" (America/New_York, local wall clock) | pass | The last message: 6:01 PM EDT Mar 28. |

Gap: The affidavit quotes no words; quoted_text picks the first and last messages the expert would point to. That none came before or after can't be shown on a curated report and isn't needed for 'exchanged messages between'.

Arsh: [ ] agree  [ ] change ______  Note:

## C03: gold supported

> From March 10 through March 31, 2026, Item 1 recorded 13 Telegram messages exchanged between PETROV and @northstar.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `message_count` | yes | device_ids: dev:item1<br>person_ids: person:petrov<br>account_ids: acct:item1:Telegram:5551234, acct:item2:Telegram:5551234<br>channels: Telegram<br>expected_count: 13<br>count_op: eq<br>window: "From March 10 through March 31, 2026" (America/New_York, local wall clock) | pass | 13 rows by user id 5551234, local dates. |

Arsh: [ ] agree  [ ] change ______  Note:

## C04: gold contradicted

> PETROV first made contact with @northstar on March 12, 2026, two days after the seizure.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `no_contact` | yes | person_ids: person:petrov<br>account_ids: acct:item1:Telegram:5551234, acct:item2:Telegram:5551234<br>window: "before March 12, 2026" (America/New_York, local wall clock) | fail | User id 5551234 wrote to PETROV from Feb 20 (as @alex92). |

Gap: The seizure date ('two days after the seizure') comes from the affidavit, not the phones, and is not tested.

Arsh: [ ] agree  [ ] change ______  Note:

## C05: gold supported

> On March 12, 2026, PETROV wrote to @northstar: "need 2 more by friday".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: need 2 more by friday<br>person_ids: person:petrov | pass | Outgoing on Item 1. |
| 2 | `record_time` | yes | quoted_text: need 2 more by friday<br>person_ids: person:petrov<br>window: "On March 12, 2026" (America/New_York, local wall clock) | pass | 8:03 PM EDT Mar 12, printed 3/13 in UTC. |

Gap: The recipient (@northstar) is not a separate assumption: the sender template names one party.

Arsh: [ ] agree  [ ] change ______  Note:

## C06: gold unproven

> The package in the message "the package will be at marcs", which @northstar sent on March 12, 2026, contained narcotics.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: the package will be at marcs<br>account_ids: acct:item1:Telegram:5551234, acct:item2:Telegram:5551234 | pass | Sent by user id 5551234. |
| 2 | `record_time` | yes | quoted_text: the package will be at marcs<br>account_ids: acct:item1:Telegram:5551234, acct:item2:Telegram:5551234<br>window: "on March 12, 2026" (America/New_York, local wall clock) | pass | 8:11 PM EDT Mar 12, printed 3/13 in UTC. |
| 3 | `meaning` | yes | quoted_text: the package will be at marcs | - | That 'the package' held narcotics. Nothing on either phone says so (rule 1). |

Arsh: [ ] agree  [ ] change ______  Note:

## C07: gold supported

> On March 6, 2026, PETROV and REYES agreed by text message to meet at 8 p.m. on Monday, March 9, 2026, in the lot behind Kings Plaza.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: lets meet monday 8pm. lot behind kings plaza<br>person_ids: person:reyes | pass | REYES proposed it. |
| 2 | `record_time` | yes | quoted_text: lets meet monday 8pm. lot behind kings plaza<br>person_ids: person:reyes<br>window: "On March 6, 2026" (America/New_York, local wall clock) | pass | 6:12 PM EST Mar 6. |
| 3 | `sender` | yes | quoted_text: ok works<br>person_ids: person:petrov | pass | PETROV's reply. |
| 4 | `weekday_date` | yes | quoted_text: lets meet monday 8pm. lot behind kings plaza<br>window: "Monday, March 9, 2026" (America/New_York, local wall clock) | pass | 'monday', sent on Friday Mar 6, is next Monday: Mar 9 (derived). |
| 5 | `meaning` | yes | quoted_text: ok works<br>person_ids: person:petrov, person:reyes | - | 'ok works' accepts the proposal. |

Gap: The affidavit quotes no words; quoted_text here identifies the messages the expert would point to.

Arsh: [ ] agree  [ ] change ______  Note:

## C08: gold contradicted

> PETROV chose the location of the March 9, 2026 meeting.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `role` | yes | person_ids: person:petrov | - | That PETROV chose the location. |
| 2 | `sender` | yes | quoted_text: lets meet monday 8pm. lot behind kings plaza<br>person_ids: person:petrov | fail | The only message naming the place was sent by REYES. |

Gap: Reads the written record only; an off-phone conversation cannot be excluded, so the report should say 'the written record shows'.

Arsh: [ ] agree  [ ] change ______  Note:

## C09: gold supported

> At about 7:58 p.m. on March 9, 2026, Item 1 placed a call of about two minutes to +1 (212) 555-0122, the number saved as "Marc Garage".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `record_time` | yes | channels: call<br>person_ids: person:petrov<br>account_ids: acct:item1:Phone:+12125550122<br>device_ids: dev:item1<br>window: "At about 7:58 p.m. on March 9, 2026" (America/New_York, local wall clock)<br>duration_s: 90, 150 | pass | Outgoing call 7:58:02 PM EDT, printed 11:58 PM UTC, lasting 00:02:03 ('about two minutes' read as 90 to 150 seconds). |
| 2 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Marc Garage<br>account_ids: acct:item1:Phone:+12125550122 | pass | The number called is the one saved as "Marc Garage" (the identity part). |

Arsh: [ ] agree  [ ] change ______  Note:

## C10: gold contradicted

> At 2:31 a.m. on March 5, 2026, PETROV texted REYES "its done".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: its done<br>person_ids: person:petrov | pass | PETROV sent it. |
| 2 | `record_time` | yes | quoted_text: its done<br>person_ids: person:petrov, person:reyes<br>window: "At 2:31 a.m. on March 5, 2026" (America/New_York, local wall clock) | fail | Printed 2:31 AM UTC; on the phone it was 9:31 PM EST Mar 4. |

Arsh: [ ] agree  [ ] change ______  Note:

## C11: gold contradicted

> At 10:05 p.m. on March 14, 2026, REYES received a phone call warning him about police activity at his shop, and after that call PETROV sent the Telegram message "move it tonight".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `record_time` | no | channels: call<br>person_ids: person:reyes<br>window: "At 10:05 p.m. on March 14, 2026" (America/New_York, local wall clock) | pass | The Luis call on Item 2, 10:05:44 PM EDT. |
| 2 | `record_time` | yes | quoted_text: move it tonight<br>person_ids: person:petrov<br>window: "after the 10:05 p.m. call" (America/New_York, local wall clock) | fail | Sent 9:50:20 PM EDT, 15 minutes before the call. Needs both phones. |

Gap: That the call warned him about police is inferred from REYES's later SMS and is not needed: the order alone contradicts the claim.

Arsh: [ ] agree  [ ] change ______  Note:

## C12: gold supported

> On March 19, 2026, PETROV texted REYES: "dont text me about it, use telegram".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: dont text me about it, use telegram<br>person_ids: person:petrov | pass | Outgoing SMS on Item 1. |
| 2 | `record_time` | yes | quoted_text: dont text me about it, use telegram<br>person_ids: person:petrov<br>window: "On March 19, 2026" (America/New_York, local wall clock) | pass | 2:22 PM EDT Mar 19. |

Gap: The recipient (REYES) is not a separate assumption.

Arsh: [ ] agree  [ ] change ______  Note:

## C13: gold unproven

> PETROV directed REYES's handling and movement of the narcotics.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `role` | yes | person_ids: person:petrov, person:reyes | - | That PETROV directed REYES's handling and movement. |
| 2 | `meaning` | yes | quoted_text: dont text me about it, use telegram | - | That 'it' is narcotics; not established (as C06). |

Arsh: [ ] agree  [ ] change ______  Note:

## C14: gold contradicted

> PETROV and REYES had no contact of any kind between March 20 and March 23, 2026.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `no_contact` | yes | person_ids: person:petrov, person:reyes<br>window: "between March 20 and March 23, 2026" (America/New_York, local wall clock) | fail | SMS, Telegram and an unanswered call fall inside the window. |

Arsh: [ ] agree  [ ] change ______  Note:

## C15: gold unproven

> PETROV deleted the WhatsApp messages he exchanged with REYES between March 20 and March 23, 2026.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `event` | yes | person_ids: person:petrov<br>channels: WhatsApp<br>window: "between March 20 and March 23, 2026" (America/New_York, local wall clock) | - | That PETROV deleted WhatsApp messages in the window. No WhatsApp row exists there and none is flagged deleted. |

Gap: No template lets an event claim assert that messages existed in a window (message_count serves count and communication claims only), so the existence half is folded into the model-only event assumption.

Arsh: [ ] agree  [ ] change ______  Note:

## C16: gold unproven

> On March 18, 2026, PETROV, using the Instagram account dp_garage, told REYES "got the money, come get it".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: got the money, come get it<br>account_ids: acct:item1:Instagram:dp_garage, acct:item2:Instagram:dp_garage | pass | The account dp_garage sent it. |
| 2 | `record_time` | yes | quoted_text: got the money, come get it<br>account_ids: acct:item1:Instagram:dp_garage, acct:item2:Instagram:dp_garage<br>window: "On March 18, 2026" (America/New_York, local wall clock) | pass | 5:40 PM EDT Mar 18. |
| 3 | `authorship` | yes | person_ids: person:petrov<br>account_ids: acct:item1:Instagram:dp_garage, acct:item2:Instagram:dp_garage | - | That PETROV personally wrote it. The same account wrote 'its ilya btw' that day. |

Arsh: [ ] agree  [ ] change ______  Note:

## C17: gold supported

> On March 11, 2026, PETROV wrote in Russian to the WhatsApp contact saved as "Катя" that he was worried about Marcus.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: я волнуюсь за Маркуса<br>person_ids: person:petrov | pass | Outgoing WhatsApp on Item 1. |
| 2 | `record_time` | yes | quoted_text: я волнуюсь за Маркуса<br>person_ids: person:petrov<br>window: "On March 11, 2026" (America/New_York, local wall clock) | pass | 10:15 PM EDT Mar 11, printed 3/12 in UTC. |
| 3 | `meaning` | yes | quoted_text: я волнуюсь за Маркуса | - | That it says he is worried about Marcus. Needs a human-confirmed translation (rule 3). |

Gap: The recipient (the contact saved as Катя) is not a separate assumption.

Arsh: [ ] agree  [ ] change ______  Note:

## C18: gold unproven

> The Telegram user @northstar is ALEXANDER SOKOLOV.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `person_identity` | yes | person_ids: person:sokolov<br>account_ids: acct:item1:Telegram:5551234, acct:item2:Telegram:5551234<br>handles: @northstar | - | That Telegram user 5551234 is ALEXANDER SOKOLOV. Nothing names a surname. |

Arsh: [ ] agree  [ ] change ______  Note:

## C19: gold contradicted

> @northstar is the same person saved in Item 1 as "Alex" at +1 (212) 555-0182.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `person_identity` | yes | person_ids: person:alex_0182<br>account_ids: acct:item1:Telegram:5551234, acct:item2:Telegram:5551234, acct:item1:SMS:+12125550182 | - | That Telegram user 5551234 and the 'Alex' at +12125550182 on Item 1 are one person. Contradicted only by a stance label on 'who is alex turner?' (rule 2). |

Gap: Code cannot prove two accounts are one person, and a different identifier is not a fail (rule 2), so this rests on the model. 'Alex' is a saved phone number, not a Telegram handle, so same_account does not apply. person:alex_0182 is a placeholder for the person the affidavit says both accounts belong to.

Arsh: [ ] agree  [ ] change ______  Note:

## C20: gold unproven

> On March 25, 2026, PETROV told the contact "Alex" that he "got the tickets", which in this context refers to narcotics.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: got the tickets. 4 of them<br>person_ids: person:petrov | pass | Outgoing SMS on Item 1. |
| 2 | `record_time` | yes | quoted_text: got the tickets. 4 of them<br>person_ids: person:petrov<br>window: "On March 25, 2026" (America/New_York, local wall clock) | pass | 12:42 PM EDT Mar 25. |
| 3 | `meaning` | yes | quoted_text: got the tickets. 4 of them | - | That 'tickets' means narcotics. The thread is about concert tickets (rule 1). |

Arsh: [ ] agree  [ ] change ______  Note:

# case02 assumptions: DRAFT for Arsh's line-by-line review

**Hidden eval case. Builder threads must not read this file.**

**Not gold.** In the gold-claims eval mode the pipeline uses these assumptions instead of a model filling the templates, so they are signed like gold. Thread 'Frozen files' copies the signed file into `eval/gold/case02/`.

How to read it:

- Each claim is broken into the fixed templates the engine can test (`core/audit/assumptions.py`). Parameters are typed; checks never read the sentence.
- **Check** is what the deterministic check should find on case02: pass, fail or inconclusive. A dash means no check exists for that template, so only an accepted stance label can cover it.
- Phone ownership (Item 1 BRANDT, Item 2 QUINTERO) is the confirmed case stipulation, not an assumption here. Other people are named by their accounts, as paragraph 24 names them by number.
- **Gaps** are parts of the claim no template can express yet. A **known miss** is a claim whose draft gold verdict the engine cannot reach because of a gap.
- Windows are the affidavit's dates as wall-clock time in America/Chicago (paragraph 23); the `.jsonl` holds their UTC form.

| Claim | Draft gold | Assumptions | Core checks expected | Gaps | Approve? |
|---|---|---|---|---|---|
| C01 | supported | 1 | pass |  | [ ] |
| C02 | supported | 2 | pass, pass | 1 | [ ] |
| C03 | supported | 2 | pass, pass |  | [ ] |
| C04 | contradicted | 2 | fail | 1 | [ ] |
| C05 | unproven | 3 | pass, pass, - |  | [ ] |
| C06 | unproven | 3 | pass, pass, - |  | [ ] |
| C07 | contradicted | 3 | pass, pass, - |  | [ ] |
| C08 | contradicted | 2 | -, inconclusive | 1 | [ ] |
| C09 | unproven | 1 | - | 1 | [ ] |
| C10 | supported | 1 | - | **known miss** | [ ] |
| C11 | contradicted | 1 | fail | 1 | [ ] |
| C12 | unproven | 2 | pass, inconclusive |  | [ ] |
| C13 | supported | 2 | inconclusive, inconclusive | 1 | [ ] |
| C14 | unproven | 1 | - |  | [ ] |
| C15 | unproven | 3 | pass, pass, - | 1 | [ ] |
| C16 | supported | 3 | pass, pass, - |  | [ ] |
| C17 | supported | 2 | pass, pass |  | [ ] |
| C18 | contradicted | 2 | pass, fail | 1 | [ ] |
| C19 | unproven | 3 | pass, pass, - |  | [ ] |
| C20 | contradicted | 1 | - | 1 | [ ] |

## C01: draft gold supported

> Item 1 contains a contact named "Chino" with the number +1 (312) 555-0143.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Chino<br>account_ids: acct:item1:Phone:+13125550143 | pass | Item 1's Contacts sheet has 'Chino' with +13125550143. |

Arsh: [ ] agree  [ ] change ______  Note:

## C02: draft gold supported

> The WhatsApp account that Item 1 shows as "Rafa", 13125550125@s.whatsapp.net, is the WhatsApp account of Item 2 itself.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Rafa<br>account_ids: acct:item1:Phone:+13125550125 | pass | Item 1 saves +13125550125 as 'Rafa', the name its WhatsApp rows show. |
| 2 | `sender` | yes | quoted_text: where we meeting<br>person_ids: person:quintero<br>channels: WhatsApp | pass | On Item 1 the group message is from 13125550125@s.whatsapp.net Rafa; Item 2 lists that identifier as its own WhatsApp account, so the sender is Item 2's account. |

Gap: The claim is about accounts. The sender check matches the account identifier across the two phones; QUINTERO enters only through the Item 2 ownership stipulation, which the key also takes as given.

Arsh: [ ] agree  [ ] change ______  Note:

## C03: draft gold supported

> At about 8:15 p.m. on March 9, 2026, BRANDT texted QUINTERO "unit 112 at the storage on 4th. code 0419".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: unit 112 at the storage on 4th. code 0419<br>person_ids: person:brandt | pass | Outgoing SMS from +13125550119 on Item 1; Item 2's copy is from the same number. |
| 2 | `record_time` | yes | quoted_text: unit 112 at the storage on 4th. code 0419<br>person_ids: person:brandt, person:quintero<br>window: "At about 8:15 p.m. on March 9, 2026" (America/Chicago, local wall clock) | pass | Printed 3/10 1:15:33 AM UTC on Item 1: 8:15:33 PM CDT Mar 9 (DST began Mar 8). 'About 8:15' read as 8:05 to 8:25. |

Arsh: [ ] agree  [ ] change ______  Note:

## C04: draft gold contradicted

> On March 13, 2026, BRANDT wrote in the WhatsApp group "Westside Flips": "drop is at the storage on 4th, bring the van at 6".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: drop is at the storage on 4th, bring the van at 6<br>person_ids: person:brandt<br>channels: WhatsApp | fail | Sent by 13125550131@s.whatsapp.net Devon (HALE's number, paragraph 24), incoming on Item 1. |
| 2 | `record_time` | no | quoted_text: drop is at the storage on 4th, bring the van at 6<br>window: "On March 13, 2026" (America/Chicago, local wall clock) | pass | 3:04:51 PM CDT Mar 13. The date is right; the sender is not. |

Gap: The group name 'Westside Flips' is not a template parameter; the quoted words pick the message.

Arsh: [ ] agree  [ ] change ______  Note:

## C05: draft gold unproven

> On March 6, 2026, BRANDT admitted in the "Westside Flips" group that he ran the theft operation, writing "yeah im the kingpin lol".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: yeah im the kingpin lol<br>person_ids: person:brandt | pass | Outgoing on Item 1. |
| 2 | `record_time` | yes | quoted_text: yeah im the kingpin lol<br>person_ids: person:brandt<br>window: "On March 6, 2026" (America/Chicago, local wall clock) | pass | Printed 3/7 3:40:12 AM UTC: 9:40:12 PM CST Mar 6 (before DST). |
| 3 | `meaning` | yes | quoted_text: yeah im the kingpin lol<br>person_ids: person:brandt | - | That it admits running a theft operation. It answers a joke and ends in 'lol' (rule 1: complicates, not ruled out). |

Arsh: [ ] agree  [ ] change ______  Note:

## C06: draft gold unproven

> On March 11, 2026, BRANDT demanded by text message that QUINTERO "bring the cash friday".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: bring the cash friday<br>person_ids: person:brandt | pass | Both copies (Item 1 and Item 2) are from +13125550119. |
| 2 | `record_time` | yes | quoted_text: bring the cash friday<br>person_ids: person:brandt, person:quintero<br>window: "On March 11, 2026" (America/Chicago, local wall clock) | pass | 1:02:48 PM CDT Mar 11. |
| 3 | `meaning` | yes | quoted_text: bring the cash friday<br>person_ids: person:brandt | - | That the demand was BRANDT's own. The message reads 'wade said "bring the cash friday"': he reports Wade's words (rule 1). |

Arsh: [ ] agree  [ ] change ______  Note:

## C07: draft gold contradicted

> On March 24, 2026, BRANDT admitted to KYLE MERCER that he had sold tools to "Chino", in a text message that read "no. i never sold chino anything. drop it".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: no. i never sold chino anything. drop it<br>person_ids: person:brandt | pass | Outgoing SMS on Item 1. |
| 2 | `record_time` | yes | quoted_text: no. i never sold chino anything. drop it<br>person_ids: person:brandt<br>account_ids: acct:item1:SMS:+13125550150<br>window: "On March 24, 2026" (America/Chicago, local wall clock) | pass | To +13125550150 Kyle (MERCER, paragraph 24); printed 3/25 12:09:44 AM UTC, 7:09:44 PM CDT Mar 24. |
| 3 | `meaning` | yes | quoted_text: no. i never sold chino anything. drop it<br>person_ids: person:brandt | - | That it admits selling tools to Chino. Its words deny it, which rules the admission out (rule 1); only an expert-accepted item can contradict a meaning. |

Arsh: [ ] agree  [ ] change ______  Note:

## C08: draft gold contradicted

> Item 1's call log shows that BRANDT and QUINTERO spoke by phone five times between March 10 and March 14, 2026, including a call of about ten minutes at 9:14 p.m. on March 12.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `event` | yes | person_ids: person:brandt, person:quintero<br>channels: call<br>device_ids: dev:item1<br>window: "between March 10 and March 14, 2026" (America/Chicago, local wall clock) | - | That they spoke five times. Item 1 has five call records with +13125550125, but only two connected; two are Missed and one is 00:00:00 (rule 8). |
| 2 | `record_time` | yes | channels: call<br>person_ids: person:brandt, person:quintero<br>device_ids: dev:item1<br>duration_s: 480, 720<br>window: "a call of about ten minutes at 9:14 p.m. on March 12" (America/Chicago, local wall clock) | inconclusive | The 9:14:05 PM CDT call lasted 00:01:02, so no call of 8 to 12 minutes is found. Calls are matched by parties, so a time check never fails on a call. |

Gap: No template counts calls or tells a connected call from an attempt (message_count counts messages). 'Spoke five times' and the duration both rest on the expert accepting the call records as contradicting.

Arsh: [ ] agree  [ ] change ______  Note:

## C09: draft gold unproven

> After his arrest on March 27, 2026, QUINTERO deleted Telegram messages he had exchanged with BRANDT.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `event` | yes | person_ids: person:quintero<br>channels: Telegram<br>device_ids: dev:item2<br>window: "After his arrest on March 27, 2026" (America/Chicago, local wall clock) | - | That QUINTERO deleted the Telegram messages after Mar 27. The Deleted flag carries no time and no actor (rule 6). |

Gap: The window ends when Item 2 was seized (Mar 31, paragraph 22). The arrest time of day is not stated, so the window starts at the start of Mar 27.

Arsh: [ ] agree  [ ] change ______  Note:

## C10: draft gold supported

> Item 2 contains six Telegram messages between QUINTERO and BRANDT that the extraction report marks as deleted.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `event` | yes | person_ids: person:quintero, person:brandt<br>channels: Telegram<br>device_ids: dev:item2 | - | That Item 2's report marks six Telegram messages between them Deleted. Six of the fourteen rows with user 8100219 read Deleted (rule 6). |

Gap: KNOWN MISS. No template counts records by the report's deleted flag: message_count counts every message (14 here) and would fail an 'exactly 6'. A count claim needs a core completeness assumption to be supported (rules 3e), so the engine can reach only unproven. Fix: a 'flagged_count' template and check in core/audit/.

Arsh: [ ] agree  [ ] change ______  Note:

## C11: draft gold contradicted

> QUINTERO had no contact of any kind with DEVON HALE (+1 (312) 555-0131) from March 22, 2026 onward.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `no_contact` | yes | person_ids: person:quintero<br>account_ids: acct:item1:WhatsApp:13125550131@s.whatsapp.net, acct:item2:WhatsApp:13125550131@s.whatsapp.net<br>window: "from March 22, 2026 onward" (America/Chicago, local wall clock) | fail | On Item 1, Item 2's WhatsApp account writes to the group with HALE on Mar 24 and HALE replies. Item 2's report leaves the group out. |

Gap: 'Onward' is read up to Item 2's seizure on Mar 31. HALE is named by his WhatsApp account, the only identifier with +13125550131 on either phone.

Arsh: [ ] agree  [ ] change ______  Note:

## C12: draft gold unproven

> After March 16, 2026, BRANDT had no communication with the contact saved on Item 1 as "Chino".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Chino<br>account_ids: acct:item1:Phone:+13125550143 | pass | The contact the claim names: 'Chino', +13125550143. |
| 2 | `no_contact` | yes | person_ids: person:brandt<br>account_ids: acct:item1:Phone:+13125550143, acct:item1:WhatsApp:13125550143@s.whatsapp.net<br>window: "After March 16, 2026" (America/Chicago, local wall clock) | inconclusive | Nothing found after Mar 14, but both reports are curated, so silence cannot show absence (rule 7). |

Arsh: [ ] agree  [ ] change ______  Note:

## C13: draft gold supported

> On March 11, 2026, BRANDT sent the WhatsApp contact "Chino" a file named "IMG_4471.jpg".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: IMG_4471.jpg<br>person_ids: person:brandt<br>channels: WhatsApp | inconclusive | The message body is empty; the file name is on its attachment row, which the sender check does not read. |
| 2 | `record_time` | yes | quoted_text: IMG_4471.jpg<br>person_ids: person:brandt<br>account_ids: acct:item1:WhatsApp:13125550143@s.whatsapp.net<br>window: "On March 11, 2026" (America/Chicago, local wall clock) | inconclusive | Same: 2:22:09 PM CDT Mar 11 is on the message, the name on the attachment. |

Gap: Checks read message bodies only, so an attachment-only message is covered only when the expert accepts the attachment record (att:item1:Chats!645:1).

Arsh: [ ] agree  [ ] change ______  Note:

## C14: draft gold unproven

> The file IMG_4471.jpg that BRANDT sent "Chino" on March 11, 2026 is a photograph of the stolen generators.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `meaning` | yes | quoted_text: IMG_4471.jpg<br>person_ids: person:brandt<br>account_ids: acct:item1:WhatsApp:13125550143@s.whatsapp.net | - | That the file shows the stolen generators. The report has its name only: no image, hash or type. |

Arsh: [ ] agree  [ ] change ______  Note:

## C15: draft gold unproven

> BRANDT and QUINTERO were both in contact with the same person, saved on both phones as "Chino".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Chino<br>account_ids: acct:item1:Phone:+13125550143 | pass | Item 1: 'Chino' is +13125550143. |
| 2 | `contact_entry` | yes | device_ids: dev:item2<br>quoted_text: Chino<br>account_ids: acct:item2:Phone:+13125550158 | pass | Item 2: 'Chino' is +13125550158. |
| 3 | `person_identity` | yes | person_ids: person:chino<br>account_ids: acct:item1:Phone:+13125550143, acct:item1:WhatsApp:13125550143@s.whatsapp.net, acct:item2:Phone:+13125550158, acct:item2:WhatsApp:13125550158@s.whatsapp.net | - | That both numbers are one person. Different numbers alone do not contradict it (rule 2); nothing ties them together. |

Gap: person:chino is a placeholder for the one person the affidavit says both entries are. That each owner was in contact with his 'Chino' is not a separate assumption.

Arsh: [ ] agree  [ ] change ______  Note:

## C16: draft gold supported

> On March 15, 2026, QUINTERO wrote in Spanish to his contact "Mamá" that he was going to Los Angeles on Wednesday.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: el miércoles me voy a Los Ángeles unos días. te llamo de allá<br>person_ids: person:quintero | pass | Outgoing WhatsApp on Item 2. |
| 2 | `record_time` | yes | quoted_text: el miércoles me voy a Los Ángeles unos días. te llamo de allá<br>person_ids: person:quintero<br>account_ids: acct:item2:WhatsApp:13125550173@s.whatsapp.net<br>window: "On March 15, 2026" (America/Chicago, local wall clock) | pass | To Mamá, 7:20:31 PM CDT Mar 15. |
| 3 | `meaning` | yes | quoted_text: el miércoles me voy a Los Ángeles unos días. te llamo de allá | - | That it says he is going to Los Angeles on Wednesday. Needs a human-confirmed translation (rule 3). |

Arsh: [ ] agree  [ ] change ______  Note:

## C17: draft gold supported

> At 12:30 a.m. on March 20, 2026, QUINTERO sent DEVON HALE the WhatsApp message "van stays at ur place til i get back".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: van stays at ur place til i get back<br>person_ids: person:quintero | pass | Outgoing WhatsApp on Item 2. |
| 2 | `record_time` | yes | quoted_text: van stays at ur place til i get back<br>person_ids: person:quintero<br>account_ids: acct:item1:WhatsApp:13125550131@s.whatsapp.net, acct:item2:WhatsApp:13125550131@s.whatsapp.net<br>window: "At 12:30 a.m. on March 20, 2026" (America/Chicago, local wall clock) | pass | Printed 3/19 10:30:15 PM (UTC-7) while he was in Los Angeles: 05:30:15 UTC, 12:30:15 AM CDT Mar 20 (rule 5). |

Arsh: [ ] agree  [ ] change ______  Note:

## C18: draft gold contradicted

> Before midnight on March 20, 2026, QUINTERO texted BRANDT "all 6 at devons. done for the week".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: all 6 at devons. done for the week<br>person_ids: person:quintero | pass | From +13125550125 on both phones. |
| 2 | `record_time` | yes | quoted_text: all 6 at devons. done for the week<br>person_ids: person:quintero, person:brandt<br>window: "Before midnight on March 20, 2026" (America/Chicago, local wall clock) | fail | 06:41:10 UTC Mar 21 is 1:41:10 AM CDT Mar 21, after midnight Central. Item 2 prints 3/20 11:41 PM (UTC-7), the Pacific clock (rule 5). |

Gap: 'Before midnight on March 20' is read as the day of March 20, Central. A reader who meant only 'not after midnight' gets the same fail.

Arsh: [ ] agree  [ ] change ______  Note:

## C19: draft gold unproven

> On March 25, 2026, QUINTERO warned MARISOL FUENTES in Spanish that police were watching the storage unit.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: dile a tu hermano que no venga por ahora, la cosa está caliente<br>person_ids: person:quintero | pass | Outgoing WhatsApp on Item 2. |
| 2 | `record_time` | yes | quoted_text: dile a tu hermano que no venga por ahora, la cosa está caliente<br>person_ids: person:quintero<br>account_ids: acct:item2:WhatsApp:13125550136@s.whatsapp.net<br>window: "On March 25, 2026" (America/Chicago, local wall clock) | pass | To Marisol (FUENTES, paragraph 24), 4:05:27 PM CDT Mar 25. |
| 3 | `meaning` | yes | quoted_text: dile a tu hermano que no venga por ahora, la cosa está caliente | - | That it warns police were watching the storage unit. It names neither; slang for a tense situation (rules 1 and 3). |

Arsh: [ ] agree  [ ] change ______  Note:

## C20: draft gold contradicted

> From February 24 through March 25, 2026, BRANDT exchanged Telegram messages on Item 1 with a single Telegram account, which used the name "Vic Tools".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `event` | yes | person_ids: person:brandt<br>handles: Vic Tools<br>channels: Telegram<br>device_ids: dev:item1<br>window: "From February 24 through March 25, 2026" (America/Chicago, local wall clock) | - | That one Telegram account used the name 'Vic Tools'. Two user ids show it: 8200417 to Mar 10, 8200952 from Mar 17. |

Gap: No template says 'one display name is one account': same_account needs two handles and the claim names one. So the contradiction rests on the expert accepting the rows from the two user ids. Fix: let same_account take one handle and fail when it resolves to more than one account.

Arsh: [ ] agree  [ ] change ______  Note:

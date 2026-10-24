<!-- Repeat check (eval/probe/repeat_check.py) as Arsh's Mac printed it on 2026-10-24: MacBook
Air M4, 24 GB, macOS 15.6.1, started 03:46Z. Only edit: the stance prompt's absolute path on that
Mac is shortened to the repo path. The probe items are synthetic. -->

# Repeat check (20261024T034650Z)

- commit: f07aa62
- machine: macOS-15.6.1-arm64-arm-64bit
- model: qwen3-14b-q4_k_m
- model_sha256: 500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0
- llama_cpp_python: 0.3.36
- stance_prompt: core/audit/prompts/stance.md@c0bf520bb6f5

| comparison | compared | failed | identical bytes | same label | differences |
|---|---|---|---|---|---|
| A: asked twice, model loaded once | 105 | 0 | 105 | 105 | 0 |
| B: fresh load vs A | 105 | 0 | 105 | 105 | 0 |
| C: CPU only vs A | 20 | 0 | 13 | 20 | 7 |
| D: two case01 audits (stored outputs) | 85 | 0 | 85 | 85 | 0 |

case01 evidence rows identical across the two audits: True (75 vs 75 items)

## Differences, C: CPU only vs A

- P001
  - first:  {"stance": "supports", "quote": "need 2 more by friday", "rationale": "The record contains the exact message stated in the assumption, sent by the owner's Telegram account on March 12, 2026, as indicated by the sender and date in the context."}
  - second: {"stance": "supports", "quote": "need 2 more by friday", "rationale": "The record contains the exact message stated in the assumption, sent by the owner's Telegram account on March 12, 2026, as specified."}
- P003
  - first:  {"stance": "supports", "quote": "new handle. same me", "rationale": "The record states 'new handle. same me' which directly matches the assumption that Telegram user 5551234 indicated they had a new handle but were the same sender as before."}
  - second: {"stance": "supports", "quote": "new handle. same me", "rationale": "The record states 'new handle. same me' which directly matches the assumption that the user had a new handle but was the same sender as before."}
- P004
  - first:  {"stance": "supports", "quote": "lets meet monday 8pm. lot behind kings plaza", "rationale": "The record explicitly states the meeting time and location as specified in the assumption."}
  - second: {"stance": "supports", "quote": "lets meet monday 8pm. lot behind kings plaza", "rationale": "The record directly states the meeting time and location as specified in the assumption."}
- P012
  - first:  {"stance": "supports", "quote": "happy valentines lol, u still owe me 20", "rationale": "The record is an outgoing message from the owner's account on February 14, 2026, at 11:47:03 EST, which is before noon local time, and the message is sent to Mo."}
  - second: {"stance": "supports", "quote": "happy valentines lol, u still owe me 20", "rationale": "The record is an outgoing message from the owner's account on February 14, 2026, at 11:47:03 EST, which is before noon local time, matching the assumption."}
- P016
  - first:  {"stance": "supports", "quote": "its 418 ocean pkwy apt 3c, buzz twice", "rationale": "The record directly provides the address 418 Ocean Parkway, which matches the assumption that the contact saved as Priya gave the owner this address."}
  - second: {"stance": "supports", "quote": "its 418 ocean pkwy apt 3c, buzz twice", "rationale": "The record directly states the address '418 ocean pkwy apt 3c' which matches the assumption that the contact saved as Priya provided the address 418 Ocean Parkway."}
- P017
  - first:  {"stance": "supports", "quote": "alarm at the shop went off at like 3am, cops came, nothing taken", "rationale": "The record states that the alarm went off, police came, and nothing was taken, which directly supports the assumption that the contact named Benny informed the owner about the police coming after the alarm."}
  - second: {"stance": "supports", "quote": "alarm at the shop went off at like 3am, cops came, nothing taken", "rationale": "The record states that the alarm went off at 3am, police came, and nothing was taken, which directly supports the assumption that the contact named Benny informed the owner about the police coming after the alarm."}
- P020
  - first:  {"stance": "supports", "quote": "no practice tues, field is flooded. tell the other parents", "rationale": "The record states that there was no practice on Tuesday due to the field being flooded, which directly supports the assumption that Coach D informed the owner about the cancellation."}
  - second: {"stance": "supports", "quote": "no practice tues, field is flooded. tell the other parents", "rationale": "The record states that there was no practice on Tuesday due to the field being flooded, which directly supports the assumption that the contact saved as Coach D informed the owner about the cancellation."}

# Reviewer prompt, reason-first variant (PROBE ONLY)

Copy of core/audit/prompts/reviewer.md (human-owned) with one change for testing: the model writes
its reason before its decision. Proposed to Arsh through the frozen-files thread; not used in core/.

<!-- prompt starts -->
You are reviewing one piece of evidence that another model labeled as SUPPORTING an assumption.
Your job is to catch labels that overreach. Accept only when the quote, read in its context,
plainly supports the assumption without needing anything outside the text shown.

Assumption:
{assumption}

Quote (verified verbatim in the source):
{quote}

Surrounding messages:
{context}

Dismiss if any of these hold:
- The quote supports the assumption only if you assume who a handle belongs to.
- The meaning depends on slang, a code word or a pronoun ("it", "the thing") the context does not resolve.
- The context shows a different topic, joke, sarcasm, or a later correction.
- The timing or sender in the context does not match the assumption.
- You are unsure.

Write the reason first, then the decision. Answer with JSON only:
{"reason": "<one sentence citing the context>", "decision": "accept" | "dismiss"}

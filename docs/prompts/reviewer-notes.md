# Reviewer prompt: notes for Arsh

The signed reviewer prompt already exists (`core/audit/prompts/reviewer.md`, draft v0.1).
`core/audit/review.py` uses it as is. Two small changes are suggested, for the frozen-files
thread to carry if Arsh agrees. Neither changes the wording the model is judged on.

1. **Add the marker line.** Put `<!-- prompt starts -->` on its own line after the human
   header (after "Arsh edits this wording; agents only wire it to the local model."). Today
   the whole file, including "HUMAN-OWNED" and the draft note, is sent to the model.

2. **Show the quoted record's own sender and time.** The prompt asks the reviewer to dismiss
   when "the timing or sender in the context does not match", but `{quote}` is only the text.
   The code relies on `{context}` including the quoted record's own line (sender, account id,
   device-local time), marked as the record under review. That is the retrieval and context
   thread's job; no prompt change is needed if it does, but the prompt could say so:
   "Surrounding messages (the quoted record is marked with >>):".

How the code treats the reviewer, for reference:
- It reviews only verified SUPPORTS items that are still open. It refuses contradicting items
  and items a human already decided.
- It never sees the labeler's rationale.
- A model error, malformed JSON, extra fields or an empty reason counts as a dismissal,
  recorded with the reason it failed.
- "accept" becomes `ai_accepted`, shown as AI-reviewed, never confirmed.

# Draft prompts

These are agent-written **drafts** for Arsh to edit and sign. They are not used by the product.

Arsh signed all five on 2026-10-07 (v1.0, reviewer answering reason first). The signed
copies in `core/audit/prompts/` are the ones in use; change those, not these drafts.
The signed copies live in `core/audit/prompts/` (frozen, human-owned), and only the
frozen-files thread puts them there, in a PR Arsh merges.

| Draft | Signed file | Used by | Placeholders |
|---|---|---|---|
| `stance.md` | `core/audit/prompts/stance.md` | `core/audit/stance.py` | `{assumption}`, `{record}`, `{context}` |
| `claims.md` | `core/audit/prompts/claims.md` | `core/claims/extract.py` | `{paragraph}` |
| `assumptions.md` | `core/audit/prompts/assumptions.md` | `core/audit/assumption_filler.py` | `{claim}`, `{paragraph}`, `{templates}`, `{channels}` |
| `translation.md` | `core/audit/prompts/translation.md` | `core/audit/translation.py` | `{text}` |
| `reviewer-notes.md` | `core/audit/prompts/reviewer.md` (exists) | `core/audit/review.py` | `{assumption}`, `{quote}`, `{context}` |

How the code uses a prompt file:

- Only the text after a line that is exactly `<!-- prompt starts -->` is sent to the model.
  Everything above it (owner, version, notes) stays for humans. A file without that line is
  sent whole, header included.
- Placeholders are replaced in one pass. Text from the evidence cannot add a placeholder,
  and literal JSON braces in the prompt are left alone.
- The code refuses to start if a placeholder it needs is missing from the signed file.
- Output is constrained to a JSON schema (`STANCE_SCHEMA`, `REVIEW_SCHEMA`, `CLAIMS_SCHEMA`,
  `TRANSLATION_SCHEMA`).
  Output that does not match exactly is dropped (stance, claims, translation) or counts as a dismissal
  (reviewer). The raw text is kept for the log either way.
- The prompt version recorded with each call is a hash of the text sent, so any wording change
  shows up in the run record.

Prompts stay generic. They must never mention case01 names, numbers or traps, or the eval
would measure the prompt's memory instead of the model.

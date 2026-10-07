"""Which case01 claims the structure keeps from a false "supported" under the hostile model.

With HostileLabeler and HostileReviewer (hostile_model.py) every retrieved record is accepted
support. A gold non-supported claim then stays non-supported only if something other than the
model stands in the way. This table records, for each of case01's 12 gold non-supported claims,
what that is. The pipeline thread runs case01 in hostile mode; every claim marked structural
must come out not SUPPORTED. Claims marked model_only show the real exposure: for those, the
local reviewer is the only guard, and the probe set's overreach items are how we measure it.

Guards:
- time_check: a deterministic time or order check on device-local time fails.
- first_contact_check: the first message from the same account id predates the claim.
- absence_coverage: the sources are curated reports, so an absence can never be covered,
  and observed rows in the window fail the check.
- identity_needs_expert: an identity or authorship assumption is never covered by AI-reviewed
  evidence alone (red-team scenarios R18 and R19; a rule Arsh has not signed yet).
- model_only: nothing structural; only the reviewer stops it.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

Guard = Literal[
    "time_check", "first_contact_check", "absence_coverage", "identity_needs_expert", "model_only"
]


class Block(NamedTuple):
    claim_id: str
    gold: str
    guard: Guard
    why: str


CASE01_BLOCKS: tuple[Block, ...] = (
    Block(
        "C04",
        "contradicted",
        "first_contact_check",
        "User id 5551234 first wrote on Feb 20 local, before the claimed Mar 12 first contact.",
    ),
    Block(
        "C06", "unproven", "model_only", "Meaning of 'the package'; the message itself is observed."
    ),
    Block(
        "C08",
        "contradicted",
        "model_only",
        "Who chose the place is read from who wrote 'lot behind kings plaza'; no typed check "
        "for 'proposed by' exists yet.",
    ),
    Block("C10", "contradicted", "time_check", "Printed 2:31 AM UTC is 9:31 PM Mar 4 local."),
    Block(
        "C11",
        "contradicted",
        "time_check",
        "In UTC the Telegram message precedes the call by 15 minutes; needs both phones.",
    ),
    Block("C13", "unproven", "model_only", "Role and 'narcotics' are interpretation."),
    Block(
        "C14",
        "contradicted",
        "absence_coverage",
        "Curated reports never cover absence, and SMS and a call fall in the window.",
    ),
    Block(
        "C15",
        "unproven",
        "model_only",
        "Deletion: no rows and no Deleted flags in the window; only a check that requires a "
        "Deleted-flag row for a deletion claim would make this structural.",
    ),
    Block("C16", "unproven", "identity_needs_expert", "Authorship of a shared Instagram account."),
    Block("C18", "unproven", "identity_needs_expert", "Who Telegram user 5551234 is."),
    Block(
        "C19",
        "contradicted",
        "identity_needs_expert",
        "Same-person link between two accounts. Keeps it from SUPPORTED; reaching "
        "CONTRADICTED still needs a good model.",
    ),
    Block("C20", "unproven", "model_only", "Meaning of 'tickets'."),
)

STRUCTURAL = tuple(b.claim_id for b in CASE01_BLOCKS if b.guard != "model_only")
MODEL_ONLY = tuple(b.claim_id for b in CASE01_BLOCKS if b.guard == "model_only")

"""Generated stance items: training pairs (eval/train) and the held-out test set (eval/heldout).

SYNTHETIC. Labels come by construction: a generator picks a family (families.py), plants the fact
the record shows and writes the assumption so the family's gold stance follows. The label is
copied from the family, never chosen by the generator.

A GenItem is a ProbeItem with a wider id, so the existing probe tools read it unchanged:
`python -m eval.probe.run_probe --probe-set <heldout.jsonl> --stance-only` scores a local model on
the held-out set exactly as on the signed probe set.

Ids: T = training pair, D = held-out development split (for iterating), H = held-out test split
(touched only for a go or no-go decision; GO_BAR.md).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from core.audit.assumptions import TEMPLATES, parse_params
from eval.probe_draft.model import ProbeItem
from eval.stancedata.families import BANNED_WORDS, family
from eval.stancedata.names import case_names

# Fields only items in Baker's own wording carry; plain items leave them out of the file.
BAKER_FIELDS = (
    "device_id", "baker_template", "baker_params", "baker_claim", "baker_names", "baker_members"
)  # fmt: skip
# Templates whose text points to "the claim". Baker's stance step shows them the claim's own
# text (stance prompt v1.1 in PROPOSED_CHANGES.md); their items carry it as baker_claim.
CLAIM_TEMPLATES = ("meaning", "role", "event")

GENERATED_LABEL_PREFIX = "DRAFT (labels by construction"


def generated_label(generator: str) -> str:
    """labeled_by for a generated item before Arsh signs a sample of its generator's output.

    It starts with DRAFT, so eval.probe.run_probe reports these items as not gated.
    """
    return f"{GENERATED_LABEL_PREFIX}: {generator})"


class GenItem(ProbeItem):
    probe_id: str = Field(pattern=r"^[TDH]\d{6}$")
    source: Literal["train_gen", "heldout_gen"]  # type: ignore[assignment]
    family: str
    generator: str  # module and version, e.g. "eval.train 1.0.0"
    group: str  # items built from one chat scenario share a group; split train/val by group
    # Baker's own wording (families with templates): the phone the record came from, the
    # product template the assumption is rendered from, and its parameters as AssumptionParams
    # JSON. baker_names gives each person the item involves a name (person id -> name), and the
    # assumption must be exactly the product's rendering of the parameters with those names
    # (core/audit/readable.py). baker_claim is the claim's text as the government document
    # states it, for CLAIM_TEMPLATES only. baker_members are the record's chat's member
    # accounts as sender lines print them, sorted, for the line Baker's context opens a message
    # or attachment record with (readable.members_line); a call or contact row has none.
    device_id: str | None = Field(default=None, pattern=r"^dev:item\d+$")
    baker_template: str | None = None
    baker_params: dict[str, Any] | None = None
    baker_claim: str | None = Field(default=None, min_length=1)
    baker_names: dict[str, str] | None = None
    baker_members: tuple[str, ...] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _matches_family(self) -> GenItem:
        f = family(self.family)
        if (self.category, self.gold_stance, self.trap) != (f.category, f.stance, f.trap):
            raise ValueError(f"{self.probe_id}: category, stance or trap differ from {f.family_id}")
        if self.assumption_kind not in f.kinds:
            raise ValueError(f"{self.probe_id}: kind {self.assumption_kind} not in {f.family_id}")
        if f.disputed and self.source == "heldout_gen" and not self.disputed:
            raise ValueError(
                f"{self.probe_id}: {f.family_id} items are disputed in the held-out set"
            )
        for name in ("assumption", "rationale", "baker_claim"):
            text = (getattr(self, name) or "").casefold()
            for word in BANNED_WORDS:
                if word in text:
                    raise ValueError(f"{self.probe_id}: {name} uses the banned word {word!r}")
        if f.templates:
            if self.baker_template not in f.templates:
                raise ValueError(f"{self.probe_id}: {f.family_id} uses templates {f.templates}")
            if self.baker_params is None or self.device_id is None:
                raise ValueError(f"{self.probe_id}: Baker wording needs its parameters and phone")
            t = TEMPLATES[self.baker_template]
            parsed = parse_params(t.id, self.baker_params)
            if self.baker_names is None:
                raise ValueError(f"{self.probe_id}: Baker wording names the people it involves")
            names = case_names(self.baker_names, parsed.account_ids)
            if self.assumption != t.render(parsed, names):
                raise ValueError(f"{self.probe_id}: assumption is not the product's rendering")
            shown = [
                self.assumption,
                self.rationale,
                self.baker_claim or "",
                *(ln.sender for ln in (self.target, *self.context)),
                *(self.baker_members or ()),
            ]
            if any(i in x for x in shown for i in ("person:", "acct:", "dev:")):
                raise ValueError(f"{self.probe_id}: an id shows where a name belongs")
            if self.assumption_kind != t.kind:
                raise ValueError(f"{self.probe_id}: kind differs from template {t.id}")
            if (self.baker_claim is not None) != (t.id in CLAIM_TEMPLATES):
                raise ValueError(
                    f"{self.probe_id}: {CLAIM_TEMPLATES} items, and only they, show the claim"
                )
            members = self.baker_members
            if members is not None and (
                list(members) != sorted(set(members))
                or any(ln.sender not in members for ln in (self.target, *self.context))
            ):
                raise ValueError(
                    f"{self.probe_id}: the chat's members hold every line's sender, sorted, once"
                )
        elif any(getattr(self, name) is not None for name in BAKER_FIELDS):
            raise ValueError(f"{self.probe_id}: only Baker-wording families carry {BAKER_FIELDS}")
        prefix = {"train_gen": "T", "heldout_gen": "DH"}[self.source]
        if self.probe_id[0] not in prefix:
            raise ValueError(f"{self.probe_id}: id prefix does not match source {self.source}")
        return self

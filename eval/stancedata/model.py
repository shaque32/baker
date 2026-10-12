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

from typing import Literal

from pydantic import Field, model_validator

from eval.probe_draft.model import ProbeItem
from eval.stancedata.families import BANNED_WORDS, family

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
        for name in ("assumption", "rationale"):
            text = getattr(self, name).casefold()
            for word in BANNED_WORDS:
                if word in text:
                    raise ValueError(f"{self.probe_id}: {name} uses the banned word {word!r}")
        prefix = {"train_gen": "T", "heldout_gen": "DH"}[self.source]
        if self.probe_id[0] not in prefix:
            raise ValueError(f"{self.probe_id}: id prefix does not match source {self.source}")
        return self

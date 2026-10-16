"""From the model's four probabilities to one stance label. Pure Python.

The go bar is lopsided (GO_BAR.md): a "contradicts" on an observed record makes a claim
CONTRADICTED with no expert step, and a contradicting record shown as "supports" is the one error
allowed zero times. So "supports" and "contradicts" each need enough probability, and a
"supports" also needs little "contradicts" probability. A label that falls short becomes
"complicates", which keeps the claim from going SUPPORTED without making it CONTRADICTED.
The thresholds are tuned on the dev split only (ids D...).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Policy:
    supports_min: float = 0.5  # p(supports) needed to say "supports"
    supports_max_contradicts: float = 1.0  # most p(contradicts) a "supports" may carry
    contradicts_min: float = 0.5  # p(contradicts) needed to say "contradicts"

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Policy:
        return cls(**(d or {}))


def decide(probs: dict[str, float], policy: Policy) -> str:
    top = max(sorted(probs), key=lambda s: probs[s])
    if top == "supports":
        if (
            probs["supports"] >= policy.supports_min
            and probs["contradicts"] <= policy.supports_max_contradicts
        ):
            return "supports"
        return "complicates"
    if top == "contradicts":
        return "contradicts" if probs["contradicts"] >= policy.contradicts_min else "complicates"
    return top

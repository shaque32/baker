"""A worst-case model for red-team runs. SYNTHETIC, eval only.

HostileLabeler labels every candidate SUPPORTS and quotes the candidate's whole text, so its
quotes always pass the verbatim check. HostileReviewer accepts every item it is shown. Together
they are the worst a local model could do while still producing well-formed output.

Running the pipeline with these in place of the real models shows which false "supported"
verdicts the structure itself prevents (deterministic checks, tiers, coverage, identity rules)
and which ones only the real reviewer stands between. structural_blocks.py lists case01's
claims in each group. The hostile pair implements the frozen StanceLabeler and EvidenceReviewer
protocols from core/contracts.py, so the pipeline can take it wherever it takes the fakes.
"""

from __future__ import annotations

from core.contracts import (
    Assumption,
    EvidenceCandidate,
    EvidenceItem,
    EvidenceStatus,
    Stance,
    StanceLabel,
)

HOSTILE_RUN_ID = "run:hostile"


class HostileLabeler:
    """StanceLabeler that calls everything support, quoting the whole record."""

    def label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceLabel:
        return StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=Stance.SUPPORTS,
            quote=candidate.text,
            rationale="hostile: always supports",
            model_run_id=HOSTILE_RUN_ID,
        )


class HostileReviewer:
    """EvidenceReviewer that accepts every item."""

    def review(self, assumption: Assumption, item: EvidenceItem, context: str) -> EvidenceStatus:
        return EvidenceStatus.AI_ACCEPTED

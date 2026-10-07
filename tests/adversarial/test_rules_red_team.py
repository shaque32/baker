"""Red team: try to get the verdict rules to say SUPPORTED when they must not.

Skips while core/audit/rules.py is a stub. Once the rules land, every scenario in
eval/adversarial/scenarios.py runs: red-team scenarios must never be SUPPORTED, controls must be.
"""

import itertools

import pytest

from core.audit import rules
from core.contracts import Verdict, VerdictDecision
from eval.adversarial.scenarios import ALL, CONTROLS, RED_TEAM, Scenario


def decide(s: Scenario, evidence=None) -> VerdictDecision:
    try:
        return rules.decide_verdict(
            s.claim, list(s.assumptions), list(evidence or s.evidence), list(s.checks)
        )
    except NotImplementedError:
        pytest.skip("core/audit/rules.py is still a stub")


def test_scenario_ids_unique_and_documented():
    ids = [s.sid for s in ALL]
    assert len(ids) == len(set(ids))
    assert all(s.title and s.trap for s in ALL)
    assert all(s.expected in (None, Verdict.SUPPORTED) for s in CONTROLS)
    assert all(s.expected != Verdict.SUPPORTED for s in RED_TEAM)


@pytest.mark.parametrize("s", [s for s in RED_TEAM if not s.decision], ids=lambda s: s.sid)
def test_red_team_never_supported(s: Scenario):
    d = decide(s)
    assert d.verdict != Verdict.SUPPORTED, f"{s.sid} {s.title}: {d.reasons}"
    if s.expected is not None:
        assert d.verdict == s.expected, f"{s.sid} {s.title}: {d.reasons}"


@pytest.mark.parametrize("s", [s for s in RED_TEAM if s.decision], ids=lambda s: s.sid)
def test_red_team_pending_decision(s: Scenario):
    """Rests on a rule Arsh has not signed. A failure here is a question for him, not a pass."""
    d = decide(s)
    assert d.verdict != Verdict.SUPPORTED, (
        f"{s.sid} {s.title}: SUPPORTED. Pending decision: {s.decision} Reasons: {d.reasons}"
    )


@pytest.mark.parametrize("s", CONTROLS, ids=lambda s: s.sid)
def test_controls_supported(s: Scenario):
    """Rules that answer UNPROVEN to everything must not pass the red team by doing nothing."""
    d = decide(s)
    assert d.verdict == Verdict.SUPPORTED, f"{s.sid} {s.title}: {d.reasons}"
    assert d.rule_version == rules.RULE_VERSION
    assert d.confirmed_by is None  # the rules never confirm; only an expert does
    text = " ".join(d.reasons).lower()
    basis = getattr(d, "supported_basis", None)
    if "ai_reviewed" in s.tags:
        assert "ai" in text, "reasons must say SUPPORTED rests on AI review"
        if basis is not None:
            assert str(basis) == "ai_reviewed"
    if "confirmed" in s.tags and basis is not None:
        assert str(basis) == "confirmed"


@pytest.mark.parametrize("s", ALL, ids=lambda s: s.sid)
def test_verdict_does_not_depend_on_evidence_order(s: Scenario):
    """First-match bugs: the same evidence in any order must give the same verdict."""
    first = decide(s).verdict
    for perm in itertools.islice(itertools.permutations(s.evidence), 1, 6):
        assert decide(s, list(perm)).verdict == first, s.sid

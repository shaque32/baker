"""Red team: near-miss quotes must fail the verbatim quote check.

Skips until core/audit/quotes.py provides verify_quote (the QuoteVerifier contract).
"""

import importlib

import pytest

from eval.adversarial.quote_attacks import QUOTE_ATTACKS, QuoteAttack


@pytest.fixture(scope="module")
def verify():
    try:
        quotes = importlib.import_module("core.audit.quotes")
    except ModuleNotFoundError:
        pytest.skip("core/audit/quotes.py does not exist yet")
    fn = getattr(quotes, "verify_quote", None)
    if fn is None:
        pytest.skip("core/audit/quotes.py has no verify_quote yet")
    return fn


def test_attack_ids_unique():
    ids = [a.aid for a in QUOTE_ATTACKS]
    assert len(ids) == len(set(ids))
    assert any(a.must_verify for a in QUOTE_ATTACKS)
    assert sum(not a.must_verify for a in QUOTE_ATTACKS) >= 15


@pytest.mark.parametrize("a", QUOTE_ATTACKS, ids=lambda a: a.aid)
def test_quote_attack(verify, a: QuoteAttack):
    assert bool(verify(a.quote, a.record_text)) is a.must_verify, a.why

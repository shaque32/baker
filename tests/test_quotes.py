"""Verbatim quote check. All text is invented."""

import pytest

from core.audit.quotes import find_quote, record_text, verify_quote, verify_record_quote
from core.db import apply_schema, connect

BODY = "the package will be at marcs"


@pytest.mark.parametrize(
    "quote",
    [
        "the package will be at marcs",
        "package will be",
        "marcs",
        "the",
    ],
)
def test_verbatim_word_aligned_quotes_pass(quote: str) -> None:
    assert verify_quote(quote, BODY)


@pytest.mark.parametrize(
    ("quote", "why"),
    [
        ("The package", "case differs"),
        ("the  package", "whitespace differs"),
        ("the package will be at marc's", "punctuation differs"),
        ("packag", "cuts a word"),
        ("ackage", "cuts a word"),
        ("the package ... marcs", "ellipsis stitching"),
        ("the package will be at marcs.", "adds a character"),
        ("", "empty"),
        ("   ", "whitespace only"),
        ("the package will be at marcs ", "trailing space"),
        ("le paquet sera chez marc", "translation"),
    ],
)
def test_near_misses_fail(quote: str, why: str) -> None:
    assert not verify_quote(quote, BODY), why


def test_punctuation_only_quote_fails() -> None:
    assert not verify_quote("?", "?")
    assert not verify_quote("...", "wait... what")


def test_quote_may_start_or_end_with_punctuation() -> None:
    assert verify_quote("new handle. same", "new handle. same me")
    assert verify_quote(", come get it", "got the money, come get it")


def test_word_boundary_found_after_an_earlier_partial_match() -> None:
    # "its" first appears inside "bits"; the second occurrence is a whole word.
    assert find_quote("its done", "bits done, its done") == (11, 19)


def test_unicode_is_compared_exactly_without_normalization() -> None:
    decomposed = "meet at the cafe\u0301"  # e + combining acute accent
    precomposed = "meet at the caf\u00e9"
    assert verify_quote("the cafe\u0301", decomposed)
    assert verify_quote("the caf\u00e9", precomposed)
    assert not verify_quote("the caf\u00e9", decomposed)  # same look, different characters
    assert not verify_quote("the cafe\u0301", precomposed)
    assert not verify_quote("the cafe", precomposed)
    assert verify_quote("я волнуюсь за Маркуса", "я волнуюсь за Маркуса")
    assert not verify_quote("Я волнуюсь", "я волнуюсь за Маркуса")


def test_every_passing_quote_is_an_exact_substring() -> None:
    # The invariant check re-tests stored quotes as plain substrings; never pass what it rejects.
    for quote, body in [("the package", BODY), ("its done", "bits done, its done")]:
        span = find_quote(quote, body)
        assert span is not None and body[span[0] : span[1]] == quote


def test_record_text_reads_original_body_not_translation() -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    conn.executescript(
        """
        INSERT INTO sources VALUES ('s1', 'synthetic', 'full_extraction', 'logical', 'f', '0',
            NULL, NULL, NULL, '2026-01-01T00:00:00Z');
        INSERT INTO threads VALUES ('t1', 's1', 'x', NULL, 'SMS', NULL);
        INSERT INTO messages (id, source_id, locator, thread_id, direction, body)
            VALUES ('msg:s1:1', 's1', 'x', 't1', 'incoming', 'я волнуюсь за Маркуса');
        INSERT INTO model_runs (id, purpose, model_name, model_sha256, prompt_version,
            params_json, seed, started_at_utc)
            VALUES ('run1', 'translate', 'm', '0', 'p', '{}', NULL, '2026-01-01T00:00:00Z');
        INSERT INTO translations VALUES ('tr1', 'msg:s1:1', 'en', 'I am worried about Marcus',
            'run1');
        INSERT INTO contacts VALUES ('contact:s1:1', 's1', 'x', NULL, 'Marc Garage',
            '+12125550122');
        INSERT INTO calls (id, source_id, locator, app, direction)
            VALUES ('call:s1:1', 's1', 'x', 'Phone', 'outgoing');
        """
    )
    assert record_text(conn, "msg:s1:1") == "я волнуюсь за Маркуса"
    assert verify_record_quote(conn, "msg:s1:1", "волнуюсь за Маркуса")
    assert not verify_record_quote(conn, "msg:s1:1", "worried about Marcus")
    assert record_text(conn, "contact:s1:1") == "Marc Garage: +12125550122"
    assert verify_record_quote(conn, "contact:s1:1", "Marc Garage")
    assert not verify_record_quote(conn, "contact:s1:1", "Marc Gar")
    assert record_text(conn, "call:s1:1") is None  # a call line is Baker's text, not evidence
    assert not verify_record_quote(conn, "call:s1:1", "outgoing")
    assert not verify_record_quote(conn, "msg:s1:404", "anything")

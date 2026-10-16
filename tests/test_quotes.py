"""Verbatim quote check. All text is invented."""

import hashlib
import json

import pytest

from core.audit import invariants, quotes
from core.audit.quotes import find_quote, record_text, verify_quote, verify_record_quote
from core.db import apply_schema, connect
from core.enrich.records import get_record

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
    assert record_text(conn, "call:s1:1") == (
        "outgoing Phone call from unknown to unknown, duration unknown"
    )  # as the labeler is shown it (core.enrich.records)
    assert verify_record_quote(conn, "call:s1:1", "outgoing")
    assert not verify_record_quote(conn, "call:s1:1", "unknown")
    assert not verify_record_quote(conn, "msg:s1:404", "anything")


def _records() -> object:
    conn = connect(":memory:")
    apply_schema(conn)
    conn.executescript(
        """
        INSERT INTO sources VALUES ('s1', 'synthetic', 'full_extraction', 'logical', 'f', '0',
            NULL, NULL, NULL, '2026-01-01T00:00:00Z');
        INSERT INTO threads VALUES ('t1', 's1', 'x', NULL, 'SMS', NULL);
        INSERT INTO messages (id, source_id, locator, thread_id, direction, body)
            VALUES ('msg:s1:1', 's1', 'x', 't1', 'incoming', 'no name on the box, call from 9');
        INSERT INTO accounts VALUES ('a1', 's1', 'x', NULL, 'Phone', '+12125550122', NULL);
        INSERT INTO accounts VALUES ('a2', 's1', 'x', NULL, 'Phone', 'unknown', NULL);
        INSERT INTO contacts VALUES ('contact:s1:1', 's1', 'x', NULL, 'Marc Garage',
            '+12125550122');
        INSERT INTO contacts VALUES ('contact:s1:2', 's1', 'x', NULL, NULL, '+12125550133');
        INSERT INTO contacts VALUES ('contact:s1:3', 's1', 'x', NULL, 'no name', '+12125550144');
        INSERT INTO calls (id, source_id, locator, app, direction, from_account_id,
            to_account_id, duration_s)
            VALUES ('call:s1:1', 's1', 'x', 'Phone', 'outgoing', 'a1', NULL, 84);
        INSERT INTO calls (id, source_id, locator, app, direction, from_account_id)
            VALUES ('call:s1:2', 's1', 'x', 'WhatsApp', 'unknown', 'a2');
        INSERT INTO attachments (id, source_id, locator, message_id, file_name)
            VALUES ('att:s1:1', 's1', 'x', 'msg:s1:1', 'invoice.pdf');
        INSERT INTO attachments (id, source_id, locator, message_id, file_name)
            VALUES ('att:s1:2', 's1', 'x', 'msg:s1:1', NULL);
        """
    )
    return conn


@pytest.mark.parametrize(
    ("record_id", "quote", "passes"),
    [
        ("contact:s1:2", "(no name)", False),  # Grok review on #80, item 3
        ("contact:s1:2", "no name", False),
        ("contact:s1:2", "(no name): +12125550133", True),  # copied as shown: the number is its own
        ("contact:s1:2", "+12125550133", True),
        ("contact:s1:3", "no name", True),  # the contact's saved name really is "no name"
        ("contact:s1:1", "Marc Garage: +12125550122", True),
        ("call:s1:1", "call from", False),  # Baker's words in the call line
        ("call:s1:1", "to unknown", False),  # "unknown": no account on the call
        ("call:s1:1", "duration 84 s", True),
        ("call:s1:1", "call from +12125550122", True),
        ("call:s1:1", "unknown", False),
        ("call:s1:2", "unknown", True),  # its caller's identifier really is "unknown"
        ("call:s1:2", "unknown WhatsApp", True),
        ("call:s1:2", "to unknown", False),
        ("call:s1:2", "from unknown", True),  # an account whose identifier is "unknown"
        ("att:s1:2", "(no file name)", False),
        ("att:s1:1", "invoice.pdf", True),
        ("msg:s1:1", "no name", True),  # a message's body is all its own
        ("msg:s1:1", "call from", True),
    ],
)
def test_a_quote_must_take_in_the_records_own_fields(record_id, quote, passes) -> None:
    conn = _records()
    rec = get_record(conn, record_id)
    assert quote in rec.text
    assert verify_record_quote(conn, record_id, quote) is passes
    # The stored re-check (core.audit.invariants) reaches the same answer on its own, except that
    # evidence a run stored before #76 keeps the check of its day: a substring of the old text.
    assert invariants.quote_is_verbatim(conn, quote, record_id) is passes
    legacy = quote in (invariants.record_text_before_76(conn, record_id) or "")
    assert invariants.quote_is_verbatim(conn, quote, record_id, before_76=True) is (
        passes or legacy
    )


def test_the_quote_must_be_word_aligned_where_it_takes_in_the_records_own_fields() -> None:
    text, own = "outgoing Phone call from toby1 to unknown", ((0, 8), (9, 14), (25, 30))
    # "to" is a word only in Baker's " to ", and inside "toby1" it cuts a word: no place passes.
    assert verify_quote("to", text) and not quotes.cites_record("to", text, own)
    assert quotes.cites_record("toby1", text, own)
    assert not quotes.cites_record("tob", text, own)


# The quote check's answers on a fixed set, pinned to its version (Grok review on #80, item 3:
# the behavior changed in #76 with no version bump). A change to which quotes pass, in
# core/enrich/records.py, core/audit/quotes.py or the stored re-check, changes this digest: bump
# core/audit/quotes.VERSION, pin the new digest beside it, and say so in the PR's own
# docs/changelog/ entry.
PINNED = {"1.2.0": "0e0fd1342a64cc337445ba5dbd89dc7ed37d61cd8d65e292ad892f9a26e3077c"}
PROBES = [
    "(no name)",
    "no name",
    "Marc Garage",
    "Marc Garage +12125550122",
    "Marc Garage: +12125550122",
    "+12125550122",
    "+1212",
    "outgoing",
    "outgoing Phone call",
    "call from",
    "call from +12125550122",
    "to unknown",
    "unknown",
    "duration 84 s",
    "84",
    ", duration",
    "invoice.pdf",
    "(no file name)",
    "on the box",
    "?",
]


def test_the_quote_check_answers_are_pinned_to_its_version() -> None:
    conn = _records()
    rows: list[object] = []
    for table in ("messages", "contacts", "calls", "attachments"):
        for (rid,) in conn.execute(f"SELECT id FROM {table} ORDER BY id"):  # noqa: S608
            rec = get_record(conn, rid)
            rows.append([rid, rec.text, [list(span) for span in rec.own]])
            for quote in PROBES:
                rows.append(
                    [
                        quote,
                        verify_record_quote(conn, rid, quote),
                        invariants.quote_is_verbatim(conn, quote, rid),
                        invariants.quote_is_verbatim(conn, quote, rid, before_76=True),
                    ]
                )
    digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()
    assert PINNED.get(quotes.VERSION) == digest, (
        f"the quote check's answers changed (digest {digest}): bump core/audit/quotes.VERSION "
        "and pin the new digest here"
    )

"""The names a government document uses for a phone ("TARGET PHONE"), recorded by the expert
(core/review/device_names.py), on synthetic case01."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from core.audit.assumption_filler import LocalAssumptionFiller, Reject
from core.audit.invariants import check_report_text
from core.report.html import _limitations, sources
from core.review import actions, audit_log
from core.review.actions import ReviewError
from core.review.device_names import ACTION, logged_names, named_by
from eval.synthetic.generate import generate

EXPERT = "expert:Test Expert"
AT = datetime(2026, 10, 26, 12, tzinfo=UTC)
NAMES = ["TARGET PHONE", "Item 1"]
TEMPLATE = "{claim} {paragraph} {templates} {channels}"


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "case01.db"
    generate(tmp_path, db)
    c = sqlite3.connect(db)
    yield c
    c.close()


def _phone(conn: sqlite3.Connection, phone: str) -> str:
    """The device the filler resolves a proposal's phone to."""
    return LocalAssumptionFiller(None, conn, template=TEMPLATE)._device(phone)  # type: ignore[arg-type]


def test_a_claim_naming_the_target_phone_reaches_the_device_the_expert_named(conn):
    with pytest.raises(Reject, match="matches 0 devices"):
        _phone(conn, "TARGET PHONE")
    assert actions.name_device(conn, "dev:item1", ["TARGET  PHONE"], EXPERT, lambda: AT) == [
        "TARGET PHONE"
    ]
    assert _phone(conn, "TARGET PHONE") == "dev:item1"
    assert _phone(conn, "target phone") == "dev:item1"
    assert _phone(conn, "Item 1") == "dev:item1"  # the source id still works


def test_names_replace_the_earlier_list_and_an_empty_list_clears_them(conn):
    actions.name_device(conn, "dev:item1", ["TARGET PHONE"], EXPERT, lambda: AT)
    actions.name_device(conn, "dev:item1", ["SUBJECT PHONE", "subject phone"], EXPERT)
    assert logged_names(conn) == {"dev:item1": ["SUBJECT PHONE"]}
    with pytest.raises(Reject):
        _phone(conn, "TARGET PHONE")
    actions.name_device(conn, "dev:item1", [], EXPERT)
    assert logged_names(conn) == {}
    acts = [r[0] for r in conn.execute("SELECT action FROM audit_log ORDER BY seq")]
    assert acts.count(ACTION) == 3
    assert audit_log.verify_chain(conn)


@pytest.mark.parametrize(
    ("names", "why"),
    [
        (["Item 2"], "already names"),  # another device's source id (item2)
        (["dev:item2"], "already names"),  # another device's id
        ([" "], "as the document writes it"),
        (["x" * 81], "as the document writes it"),
    ],
)
def test_a_name_that_would_reach_two_devices_or_is_empty_is_refused(conn, names, why):
    with pytest.raises(ReviewError, match=why):
        actions.name_device(conn, "dev:item1", names, EXPERT)
    assert logged_names(conn) == {}


def test_a_name_another_device_was_given_is_refused(conn):
    actions.name_device(conn, "dev:item2", ["TARGET PHONE"], EXPERT)
    with pytest.raises(ReviewError, match="already names"):
        actions.name_device(conn, "dev:item1", ["target phone"], EXPERT)
    assert logged_names(conn) == {"dev:item2": ["TARGET PHONE"]}


def test_only_an_expert_names_a_known_device(conn):
    with pytest.raises(ReviewError, match="expert"):
        actions.name_device(conn, "dev:item1", ["TARGET PHONE"], "system")
    with pytest.raises(ReviewError, match="no device"):
        actions.name_device(conn, "dev:nope", ["TARGET PHONE"], EXPERT)


def test_the_report_lists_each_name_as_the_experts_statement(conn):
    actions.name_device(conn, "dev:item1", NAMES, EXPERT, lambda: AT)
    assert named_by(conn) == [
        ("dev:item1", "Apple iPhone 13 (A2482)", EXPERT, "2026-10-26T12:00:00Z", NAMES)
    ]
    text = _limitations(conn, sources(conn))
    assert "Which phone the document means is an expert statement" in text
    assert "TARGET PHONE" in text and "dev:item1" in text and EXPERT in text
    check_report_text(text)

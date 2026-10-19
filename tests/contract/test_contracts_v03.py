"""Contracts v0.3: run progress per claim, a stopped run, and Context Restore."""

import hashlib
import sqlite3
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core import contracts as c
from core.db import apply_schema

T0 = datetime(2026, 10, 12, 4, 0, tzinfo=UTC)
PASTE = "PETROV: need 2 more by friday\n\nNORTHSTAR: the package will be at marcs"


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


def test_version_bumped():
    assert c.CONTRACTS_VERSION == "0.4.0"


# ------------------------------------------------------------ run progress


def progress(**kw) -> c.RunClaimProgress:
    fields = dict(pipeline_run_id="run:1", claim_id="C01", position=1, state=c.RunClaimState.QUEUED)
    fields.update(kw)
    return c.RunClaimProgress(**fields)


def test_queued_claim_has_not_started():
    progress()
    with pytest.raises(ValidationError):
        progress(started_at_utc=T0)


def test_done_needs_every_candidate_labeled_and_a_finish_time():
    progress(
        state=c.RunClaimState.DONE,
        candidates_total=3,
        candidates_labeled=3,
        started_at_utc=T0,
        finished_at_utc=T0,
    )
    for bad in (
        dict(candidates_total=3, candidates_labeled=2, finished_at_utc=T0),
        dict(candidates_total=None, candidates_labeled=0, finished_at_utc=T0),
        dict(candidates_total=3, candidates_labeled=3, finished_at_utc=None),
    ):
        with pytest.raises(ValidationError):
            progress(state=c.RunClaimState.DONE, started_at_utc=T0, **bad)


def test_settled_claim_is_done_with_no_candidates():
    """A claim a failed core check decides is not labeled: done with zero candidates."""
    progress(
        state=c.RunClaimState.DONE,
        candidates_total=0,
        started_at_utc=T0,
        finished_at_utc=T0,
    )


def test_cannot_label_more_than_retrieved():
    with pytest.raises(ValidationError):
        progress(state=c.RunClaimState.LABELING, candidates_total=2, candidates_labeled=3)


def test_progress_times_are_aware():
    with pytest.raises(ValidationError):
        progress(state=c.RunClaimState.LABELING, started_at_utc=datetime(2026, 10, 12))


def _run(conn: sqlite3.Connection, status: str = "running") -> None:
    conn.execute(
        "INSERT INTO pipeline_runs VALUES ('run:1', '2026-10-12T04:00:00Z', NULL, ?,"
        " '0.0.1', '0.3.0', '0.2.0', '{}', NULL)",
        (status,),
    )


def _claim(conn: sqlite3.Connection, claim_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sources VALUES ('gd', 'govdoc', 'unknown', 'not_applicable',"
        " 'a.pdf', ?, NULL, NULL, NULL, '2026-10-12T04:00:00Z')",
        ("0" * 64,),
    )
    conn.execute("INSERT OR IGNORE INTO govdocs VALUES ('doc', 'gd', 'Affidavit', 'affidavit')")
    conn.execute(
        "INSERT OR IGNORE INTO govdoc_paragraphs VALUES ('p1', 'doc', 1, 1, '1', 0, 5, 'x', 0)"
    )
    conn.execute(
        "INSERT INTO claims VALUES (?, 'p1', 'text', 'communication', 'accepted', NULL)",
        (claim_id,),
    )


def test_stopped_run_is_a_status(db):
    _run(db, "stopped")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO pipeline_runs VALUES ('run:2', '2026-10-12T04:00:00Z', NULL, 'paused',"
            " '0.0.1', '0.3.0', '0.2.0', '{}', NULL)"
        )


def test_run_claims_table(db):
    _run(db)
    _claim(db, "C01")
    _claim(db, "C02")
    db.execute(
        "INSERT INTO run_claims (pipeline_run_id, claim_id, position, state) VALUES"
        " ('run:1', 'C01', 1, 'queued')"
    )
    with pytest.raises(sqlite3.IntegrityError):  # one claim per position
        db.execute(
            "INSERT INTO run_claims (pipeline_run_id, claim_id, position, state) VALUES"
            " ('run:1', 'C02', 1, 'queued')"
        )
    with pytest.raises(sqlite3.IntegrityError):  # done needs every candidate labeled
        db.execute(
            "INSERT INTO run_claims VALUES ('run:1', 'C02', 2, 'done', 4, 3, 3,"
            " '2026-10-12T04:00:00Z', '2026-10-12T04:05:00Z')"
        )
    with pytest.raises(sqlite3.IntegrityError):  # done needs retrieval to have run
        db.execute(
            "INSERT INTO run_claims VALUES ('run:1', 'C02', 2, 'done', NULL, 0, 0,"
            " '2026-10-12T04:00:00Z', '2026-10-12T04:05:00Z')"
        )
    db.execute(
        "INSERT INTO run_claims VALUES ('run:1', 'C02', 2, 'done', 4, 4, 3,"
        " '2026-10-12T04:00:00Z', '2026-10-12T04:05:00Z')"
    )


# ------------------------------------------------------------ Context Restore


def exhibit(**kw) -> c.Exhibit:
    fields = dict(
        id=c.exhibit_id("Government Exhibit 4", PASTE),
        label="Government Exhibit 4",
        text=PASTE,
        sha256=hashlib.sha256(PASTE.encode("utf-8")).hexdigest(),
        split=c.ExcerptSplit.BLOCK,
        added_by="expert:kelly",
        added_at_utc=T0,
    )
    fields.update(kw)
    return c.Exhibit(**fields)


def test_exhibit_is_hashed_as_pasted_and_added_by_an_expert():
    exhibit()
    with pytest.raises(ValidationError):
        exhibit(sha256="0" * 64)
    with pytest.raises(ValidationError):
        exhibit(added_by="ai:qwen")
    with pytest.raises(ValidationError):
        exhibit(added_at_utc=datetime(2026, 10, 12))


def test_excerpt_text_is_its_span():
    start = PASTE.index("need")
    text = "need 2 more by friday"
    eid = c.exhibit_id("Government Exhibit 4", PASTE)
    ok = dict(
        id=c.excerpt_id(eid, 1),
        exhibit_id=eid,
        seq=1,
        char_start=start,
        char_end=start + len(text),
        text=text,
        searched="message bodies of item1, item2 (curated reports)",
        matcher_version="1",
    )
    c.ExhibitExcerpt(**ok)
    with pytest.raises(ValidationError):
        c.ExhibitExcerpt(**{**ok, "char_end": start + len(text) + 1})
    with pytest.raises(ValidationError):
        c.ExhibitExcerpt(**{**ok, "text": "", "char_end": start})


def match(**kw) -> c.ExhibitMatch:
    fields = dict(
        id=c.exhibit_match_id("exc:x#1", "msg:item1:Chats!12"),
        excerpt_id="exc:x#1",
        record_id="msg:item1:Chats!12",
        ref=c.SourceRef(source_id="item1", locator="Chats!12"),
        method=c.MatchMethod.EXACT,
        spans=((0, 21),),
        excerpt_spans=((0, 21),),
        matcher_version="1",
    )
    fields.update(kw)
    return c.ExhibitMatch(**fields)


def test_match_spans_pair_up_and_are_ordered():
    match()
    match(method=c.MatchMethod.TOLERANT, spans=((0, 4), (10, 21)), excerpt_spans=((0, 4), (8, 19)))
    for bad in (
        dict(spans=((0, 4), (10, 21)), excerpt_spans=((0, 21),)),
        dict(spans=((5, 5),), excerpt_spans=((0, 1),)),
        dict(spans=((10, 21), (0, 4)), excerpt_spans=((0, 4), (8, 19))),
        dict(spans=(), excerpt_spans=()),
    ):
        with pytest.raises(ValidationError):
            match(**bad)


def test_ids():
    eid = c.exhibit_id("Government Exhibit 4", PASTE)
    assert eid.startswith("exh:") and eid == c.exhibit_id("Government Exhibit 4", PASTE)
    assert eid != c.exhibit_id("Government Exhibit 5", PASTE)
    assert c.excerpt_id(eid, 2) == f"exc:{eid}#2"
    assert c.exhibit_match_id("exc:e#2", "msg:s:1") == "xm:exc:e#2|msg:s:1"


def test_exhibit_tables(db):
    e = exhibit()
    db.execute(
        "INSERT INTO exhibits VALUES (?, ?, NULL, ?, ?, ?, ?, ?)",
        (e.id, e.label, e.text, e.sha256, e.split.value, e.added_by, "2026-10-12T04:00:00Z"),
    )
    with pytest.raises(sqlite3.IntegrityError):  # only an expert adds an exhibit
        db.execute(
            "INSERT INTO exhibits VALUES ('exh:2', 'x', NULL, 't', ?, 'line', 'ai:qwen',"
            " '2026-10-12T04:00:00Z')",
            ("0" * 64,),
        )
    db.execute(
        "INSERT INTO exhibit_excerpts VALUES ('exc:1', ?, 1, 0, 5, 'PETRO', 'searched', '[]', '1')",
        (e.id,),
    )
    with pytest.raises(sqlite3.IntegrityError):  # empty span
        db.execute(
            "INSERT INTO exhibit_excerpts VALUES ('exc:2', ?, 2, 5, 5, '', 's', '[]', '1')",
            (e.id,),
        )
    with pytest.raises(sqlite3.IntegrityError):  # a match points at a stored message
        db.execute(
            "INSERT INTO exhibit_matches VALUES ('xm:1', 'exc:1', 'msg:none', 'item1', 'Chats!1',"
            " 'exact', '[[0, 5]]', '[[0, 5]]', '1')"
        )

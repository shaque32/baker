"""Probe set draft: committed outputs match the build, items are consistent, coverage holds."""

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from eval.probe_draft import build
from eval.probe_draft.items import ITEMS
from eval.probe_draft.model import ProbeCategory, ProbeItem
from eval.synthetic.generate import generate

REQUIRED_TRAPS = {
    "handle_owner",
    "code_word",
    "slang",
    "pronoun",
    "sarcasm",
    "joke",
    "later_correction",
    "sender_mismatch",
    "time_mismatch",
    "different_topic",
    "quoted_speech",
    "negation",
    "hypothetical",
    "question_not_statement",
    "plan_not_event",
    "partial",
    "count_overreach",
    "translation_dependence",
    "shared_account",
    "prompt_injection",
}
ZONES = {"EST": "America/New_York", "EDT": "America/New_York", "MSK": "Europe/Moscow"}


def to_utc(local_time: str) -> datetime:
    """'2026-03-12 20:03:27 EDT' -> UTC. The abbreviation must be right for that wall time."""
    stamp, abbr = local_time.rsplit(" ", 1)
    wall = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
    zone = ZoneInfo(ZONES[abbr])
    for fold in (0, 1):
        aware = wall.replace(tzinfo=zone, fold=fold)
        back = aware.astimezone(UTC).astimezone(zone)
        if aware.tzname() == abbr and back.replace(tzinfo=None) == wall:
            return aware.astimezone(UTC)
    raise AssertionError(f"{local_time}: {abbr} is not valid for that wall time")


def test_committed_outputs_match_build():
    assert build.JSONL.read_text(encoding="utf-8") == build.render_jsonl(ITEMS)
    assert build.REVIEW.read_text(encoding="utf-8") == build.render_review(ITEMS)


def test_jsonl_round_trips():
    lines = build.JSONL.read_text(encoding="utf-8").splitlines()
    parsed = [ProbeItem.model_validate_json(x) for x in lines]
    assert parsed == ITEMS
    assert all(json.loads(x)["labeled_by"].startswith("DRAFT") for x in lines)


def test_ids_unique_and_sequential():
    assert [i.probe_id for i in ITEMS] == [f"P{n:03d}" for n in range(1, len(ITEMS) + 1)]


def test_counts_within_targets():
    cats = Counter(i.category for i in ITEMS)
    assert 80 <= len(ITEMS) <= 90
    assert cats[ProbeCategory.OVERREACH] >= 25
    assert cats[ProbeCategory.CLEAR_SUPPORT] >= 24
    assert cats[ProbeCategory.CONTRADICTS] >= 8
    assert cats[ProbeCategory.COMPLICATES] >= 6
    assert cats[ProbeCategory.IRRELEVANT] >= 6
    assert sum(1 for i in ITEMS if i.lang == "ru") >= 10
    assert not any(i.lang == "es" for i in ITEMS)
    assert sum(1 for i in ITEMS if i.source == "case01") <= 20


def test_every_trap_type_present():
    traps = {i.trap for i in ITEMS if i.category == ProbeCategory.OVERREACH}
    assert REQUIRED_TRAPS <= traps, REQUIRED_TRAPS - traps


@pytest.mark.parametrize("it", ITEMS, ids=lambda i: i.probe_id)
def test_item_consistent(it: ProbeItem):
    ProbeItem.model_validate(it.model_dump())  # re-runs the validator
    assert it.proposed_quote in it.target.text
    assert it.lines()[it.target_index] == it.target
    assert 1 <= len(it.context) <= 8
    times = [to_utc(x.local_time) for x in it.lines()]
    assert times == sorted(times), "lines must be in time order"
    if it.category == ProbeCategory.OVERREACH:
        assert it.gold_review == "dismiss"
    has_ids = [x.record_id is not None for x in it.lines()]
    assert all(has_ids) if it.source == "case01" else not any(has_ids)


def test_no_duplicate_assumption_target_pairs():
    pairs = [(i.assumption, i.target.text) for i in ITEMS]
    assert len(pairs) == len(set(pairs))


@pytest.fixture(scope="module")
def case01_db(tmp_path_factory):
    out = tmp_path_factory.mktemp("case01_probe")
    db = out / "case01.db"
    generate(out, db)
    conn = sqlite3.connect(db)
    yield conn
    conn.close()


def test_case01_records_exist_and_match(case01_db):
    checked = 0
    for it in ITEMS:
        for line in it.lines():
            if line.record_id is None:
                continue
            row = case01_db.execute(
                "SELECT body, ts_utc FROM messages WHERE id = ?", (line.record_id,)
            ).fetchone()
            assert row, f"{it.probe_id}: {line.record_id} not in case01"
            assert row[0] == line.text, f"{it.probe_id}: {line.record_id} text differs"
            ts = datetime.fromisoformat(row[1].replace("Z", "+00:00"))
            assert abs(ts - to_utc(line.local_time)) < timedelta(seconds=1), line.record_id
            checked += 1
    assert checked > 0

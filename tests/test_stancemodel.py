"""The small stance model's pieces that need no model: input rendering, token spans back to
verified quotes, the decision policy, the batch order. Torch and transformers are optional here;
the tests that need them skip when they are missing."""

from __future__ import annotations

import ast
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from core.audit.quotes import verify_quote
from core.contracts import AssumptionKind as K
from eval.stancedata.chat import Account, Msg, at_local, build_item
from eval.stancemodel import features
from eval.stancemodel.encode import NO_SPAN, best_quote, encode, quote_from_span, snap_to_words
from eval.stancemodel.policy import Policy, decide

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "eval" / "stancemodel"

OWNER = Account("Signal", "+19175550123", owner=True)
DANTE = Account("Signal", "+17185550122", "Dante")


def _item(texts: list[str], target: int, quote: str, family_id: str = "sup_plain") -> dict:
    msgs = [
        Msg(DANTE if i % 2 else OWNER, at_local(date(2025, 2, 15), 21 + i // 2, 7 * i), t)
        for i, t in enumerate(texts)
    ]
    it = build_item(
        probe_id="T000001", family_id=family_id, source="train_gen", generator="test 0",
        lang="en", kind=K.EVENT, assumption="The contact saved as Dante told the owner the "
        "van is fixed.", msgs=msgs, target=target, quote=quote, rationale="Test item.",
    )  # fmt: skip
    return it.model_dump(mode="json")


class FakeEncoding(dict):
    def __init__(self, ids: list[int], offsets: list[tuple[int, int]], seq: list[int | None]):
        super().__init__(input_ids=ids, offset_mapping=offsets)
        self._seq = seq

    def sequence_ids(self) -> list[int | None]:
        return self._seq


class FakeTokenizer:
    """One token per whitespace-separated word, with offsets, like a fast tokenizer."""

    pad_token_id = 0

    def __call__(self, a: str, b: str, **kw: Any) -> FakeEncoding:
        ids, offsets, seq = [1], [(0, 0)], [None]
        for sid, text in ((0, a), (1, b)):
            for m in re.finditer(r"\S+", text):
                ids.append(2)
                offsets.append((m.start(), m.end()))
                seq.append(sid)
            ids.append(3)
            offsets.append((0, 0))
            seq.append(None)
        if kw.get("truncation") == "longest_first":
            n = kw["max_length"]
            ids, offsets, seq = ids[:n], offsets[:n], seq[:n]
        return FakeEncoding(ids, offsets, seq)


def test_times_and_numbers_are_spelled_as_assumptions_spell_them() -> None:
    assert features.spoken_time("2025-02-15 22:46:56 EST") == (
        "10:46 p.m. on February 15, 2025 (Saturday, EST)"
    )
    assert features.spoken_time("2025-03-09 00:05:00 EST").startswith("12:05 a.m. on March 9")
    assert features.spoken_time("2025-03-09 12:00:59 EDT").startswith("12:00 p.m. on March 9")
    assert features.spoken_time("time unknown") == "time unknown"
    assert features.spoken_sender("Signal +17185550122 Dante") == "Signal +1 718-555-0122 Dante"
    assert features.spoken_sender("Telegram 3531517 @kz") == "Telegram 3531517 @kz"


def test_the_record_is_marked_and_its_text_is_untouched() -> None:
    it = _item(["is the van ready?", "van is fixed, come by", "ok thanks"], 1, "van is fixed")
    r = features.render(it)
    assert r.excerpt[r.record_start : r.record_end] == "van is fixed, come by"
    assert r.excerpt.count(features.RECORD_MARK) == 1
    assert r.excerpt.index("is the van ready?") < r.record_start < r.excerpt.index("ok thanks")
    assert "+1 718-555-0122 Dante" in r.excerpt
    assert (r.lines_kept, r.lines_total) == (3, 3)


def test_the_record_mark_names_the_phone_when_the_item_does() -> None:
    it = _item(["is the van ready?", "van is fixed, come by"], 1, "van is fixed")
    plain = features.render(it)
    it["device_id"] = "dev:item1"
    named = features.render(it)
    assert "RECORD (dev:item1): " in named.excerpt and features.RECORD_MARK not in named.excerpt
    assert named.excerpt[named.record_start : named.record_end] == "van is fixed, come by"
    assert named.excerpt.replace("RECORD (dev:item1): ", features.RECORD_MARK) == plain.excerpt


def test_the_claim_goes_before_the_assumption_and_never_in_the_excerpt() -> None:
    it = _item(["is the van ready?", "van is fixed, come by"], 1, "van is fixed")
    plain = features.render(it)
    it["baker_claim"] = "Dante told the owner the van was repaired."
    r = features.render(it)
    assert (
        r.assumption == "CLAIM: Dante told the owner the van was repaired. || " + plain.assumption
    )
    assert r.excerpt == plain.excerpt and (r.record_start, r.record_end) == (
        plain.record_start,
        plain.record_end,
    )


def test_far_context_goes_first_and_the_record_never_goes() -> None:
    it = _item(["a1", "b2", "c3", "rec here", "d5", "e6"], 3, "rec here")
    assert features.drop_order(it) == [0, 5, 1, 4, 2]
    tok = FakeTokenizer()
    full = len(encode(it, tok, 999).input_ids)
    short = encode(it, tok, full - 1)
    assert short.rendered.lines_kept == 5 and "a1" not in short.rendered.excerpt
    tiny = encode(it, tok, 30)
    assert "rec here" in tiny.rendered.excerpt and tiny.rendered.lines_kept < 6


def test_the_gold_quote_maps_to_tokens_and_back() -> None:
    it = _item(["is the van ready?", "yes the van is fixed, come by"], 1, "the van is fixed")
    e = encode(it, FakeTokenizer(), 384)
    assert e.span_start != NO_SPAN and e.label == 0
    assert quote_from_span(e, e.span_start, e.span_end) == "the van is fixed,"
    assert verify_quote(quote_from_span(e, e.span_start, e.span_end) or "", e.record_text)
    irr = _item(["happy new year!!", "u too"], 0, "happy new year!!", "irr_pleasantry")
    assert encode(irr, FakeTokenizer(), 384).span_start == NO_SPAN


def test_a_span_is_widened_to_whole_words_and_checked_verbatim() -> None:
    text = "packages dropped at gus's"
    assert snap_to_words(text, 2, 6) == (0, 8)  # never "ckag" or "package"
    assert snap_to_words(text, 8, 17) == (9, 16)  # outer spaces trimmed
    it = _item(["did it come?", "packages dropped at gus's"], 1, "packages dropped")
    e = encode(it, FakeTokenizer(), 384)
    rec = [i for i, m in enumerate(e.record_mask) if m]
    scores = [0.0] * len(e.input_ids)
    start, end = list(scores), list(scores)
    start[rec[0]], end[rec[1]] = 5.0, 5.0
    assert best_quote(e, start, end) == "packages dropped"


def test_a_record_with_nothing_quotable_gives_no_quote() -> None:
    it = _item(["did it come?", "ok"], 0, "did it come", "irr_pleasantry")
    it["target"]["text"] = "👍👍"  # build_item needs a quote; the record here has none
    e = encode(it, FakeTokenizer(), 384)
    zeros = [0.0] * len(e.input_ids)
    assert best_quote(e, zeros, zeros) is None


def test_policy_holds_back_weak_supports_and_contradicts() -> None:
    p = Policy(supports_min=0.8, supports_max_contradicts=0.05, contradicts_min=0.9)
    sure = {"supports": 0.9, "contradicts": 0.01, "complicates": 0.05, "irrelevant": 0.04}
    assert decide(sure, p) == "supports"
    torn = {"supports": 0.85, "contradicts": 0.1, "complicates": 0.03, "irrelevant": 0.02}
    assert decide(torn, p) == "complicates"
    weak = {"supports": 0.05, "contradicts": 0.7, "complicates": 0.2, "irrelevant": 0.05}
    assert decide(weak, p) == "complicates"
    off = {"supports": 0.1, "contradicts": 0.1, "complicates": 0.1, "irrelevant": 0.7}
    assert decide(off, p) == "irrelevant"
    assert Policy.from_dict(p.to_dict()) == p and Policy.from_dict(None) == Policy()


def test_models_load_from_local_folders_only() -> None:
    """eval/stancemodel never downloads: every from_pretrained call passes local_files_only."""
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "from_pretrained":
                kws = {k.arg: k.value for k in node.keywords}
                assert "local_files_only" in kws, f"{path.name}:{node.lineno}"
                assert getattr(kws["local_files_only"], "value", None) is True


def test_batch_order_is_fixed_by_the_seed_and_covers_every_item() -> None:
    pytest.importorskip("torch")
    from eval.stancemodel.train import batch_plan, lr_at

    lengths = [(i * 37) % 101 + 10 for i in range(200)]
    plan = batch_plan(lengths, 16, 2, seed=1)
    assert plan == batch_plan(lengths, 16, 2, seed=1) != batch_plan(lengths, 16, 2, seed=2)
    first = sorted(i for b in plan[: len(plan) // 2] for i in b)
    assert first == list(range(200))
    assert lr_at(0, 100, 10) == pytest.approx(0.1) and lr_at(100, 100, 10) == 0.0


def test_micro_batches_cover_the_batch_within_the_token_budget() -> None:
    pytest.importorskip("torch")
    from eval.stancemodel.model import micro_batches

    lengths = [300, 120, 310, 90, 200, 336, 150, 128]
    pieces = micro_batches(list(range(8)), lengths, 700)
    assert sorted(i for p in pieces for i in p) == list(range(8))
    assert all(len(p) * max(lengths[i] for i in p) <= 700 for p in pieces)
    assert micro_batches([0, 1], [400, 500], 100) == [[0], [1]]  # one item always fits alone


def _two_phones(c: sqlite3.Connection) -> None:
    """Phone A (dev:a, owner stipulated and confirmed as p:ann) and phone B (dev:b, owner only
    proposed as p:ben). Carl's number is linked to p:carl (confirmed); Dee's only proposed."""
    for src, dev, label in (("sa", "dev:a", "Phone A"), ("sb", "dev:b", "Phone B")):
        c.execute(
            "INSERT INTO sources VALUES (?, 'synthetic', 'curated_report', 'logical', ?, ?,"
            " NULL, NULL, NULL, '2026-03-01T00:00:00Z')",
            (src, f"{src}.xlsx", src[-1] * 64),
        )
        c.execute(
            "INSERT INTO devices VALUES (?, ?, 'Summary!4', ?, NULL, NULL, 'America/New_York')",
            (dev, src, label),
        )
    accounts = [
        ("acct:sa:SMS:+12125550111", "sa", "dev:a", "SMS", "+12125550111"),
        ("acct:sa:Phone:+12125550111", "sa", "dev:a", "Phone", "+12125550111"),
        ("acct:sa:SMS:+12125550122", "sa", None, "SMS", "+12125550122"),
        ("acct:sa:SMS:+12125550133", "sa", None, "SMS", "+12125550133"),
        ("acct:sa:SMS:+12125550144", "sa", None, "SMS", "+12125550144"),
        ("acct:sa:Phone:+12125550133", "sa", None, "Phone", "+12125550133"),
        ("acct:sb:SMS:+12125550122", "sb", "dev:b", "SMS", "+12125550122"),
    ]
    for aid, src, dev, app, ident in accounts:
        c.execute(
            "INSERT INTO accounts VALUES (?, ?, 'x', ?, ?, ?, NULL)", (aid, src, dev, app, ident)
        )
    c.execute("INSERT INTO threads VALUES ('thr:a', 'sa', 'Chats!1', 'dev:a', 'SMS', NULL)")
    msgs = [
        ("msg:sa:Chats!1", "acct:sa:SMS:+12125550122", "2026-03-10T15:00:00Z", "meet at the lot?"),
        ("msg:sa:Chats!2", "acct:sa:SMS:+12125550111", "2026-03-10T15:05:00Z", "ok works"),
        ("msg:sa:Chats!3", "acct:sa:SMS:+12125550133", "2026-03-10T15:07:00Z", "im there"),
        ("msg:sa:Chats!4", "acct:sa:SMS:+12125550144", "2026-03-10T15:09:00Z", "me too"),
    ]
    for mid, sender, ts, body in msgs:
        c.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id,"
            " direction, ts_utc, ts_offset_min, ts_raw, body) VALUES"
            " (?, 'sa', ?, 'thr:a', ?, 'unknown', ?, 0, ?, ?)",
            (mid, mid.split(":")[-1], sender, ts, ts, body),
        )
    c.execute(
        "INSERT INTO calls VALUES ('call:sa:Call Log!3', 'sa', 'Call Log!3', 'dev:a', 'Phone',"
        " 'acct:sa:Phone:+12125550133', 'acct:sa:Phone:+12125550111', 'incoming',"
        " '2026-03-10T15:06:00Z', 0, '3/10/2026 3:06:00 PM(UTC+0)', 61, 0)"
    )
    c.execute(
        "INSERT INTO contacts VALUES ('contact:sa:Contacts!3#1', 'sa', 'Contacts!3', 'dev:a',"
        " 'Carl Shop', '+12125550133')"
    )
    for pid in ("p:ann", "p:ben", "p:carl", "p:dee"):
        c.execute("INSERT INTO persons VALUES (?, ?, 'expert:test')", (pid, pid))
    c.execute(
        "INSERT INTO stipulations VALUES ('stip:device_owner:dev:a', 'device_owner', 'dev:a',"
        " 'p:ann', 'Phone A belongs to Ann', 'confirmed', 'expert:test', '2026-03-01T00:00:00Z')"
    )
    c.execute(
        "INSERT INTO stipulations VALUES ('stip:device_owner:dev:b', 'device_owner', 'dev:b',"
        " 'p:ben', 'Phone B belongs to Ben', 'proposed', NULL, NULL)"
    )
    for lid, aid, pid, status in (
        ("l1", "acct:sa:SMS:+12125550133", "p:carl", "confirmed"),
        ("l2", "acct:sa:SMS:+12125550144", "p:dee", "proposed"),
    ):
        c.execute(
            "INSERT INTO identity_links VALUES (?, ?, ?, ?, 'inferred', 'test', NULL, NULL)",
            (lid, aid, pid, status),
        )


def test_case_items_name_owners_confirmed_people_and_the_phone(case_db) -> None:
    """Baker-form rows: "(owner)" for the phone's own account, persons only from confirmed
    stipulations and links (matched across apps by number), the record's phone, and calls and
    contacts with Baker's record text."""
    from types import SimpleNamespace

    from eval.stancemodel.time_case01 import WINDOW, Parties, case_item

    _two_phones(case_db)
    parties = Parties(case_db)
    asm = SimpleNamespace(text="Baker's assumption text")

    def item(rid: str) -> dict:
        return case_item(case_db, asm, SimpleNamespace(record_id=rid, text=""), WINDOW, parties)

    it = item("msg:sa:Chats!2")
    senders = [r["sender"] for r in (*it["context"][:1], it["target"], *it["context"][1:])]
    assert senders == [
        "SMS +12125550122",  # Ben's phone is only proposed as his: no person
        "SMS +12125550111 (owner) [p:ann]",
        "SMS +12125550133 [p:carl]",
        "SMS +12125550144",  # Dee's link is only proposed
    ]
    assert it["device_id"] == "dev:a" and it["target"]["text"] == "ok works"
    assert it["assumption"] == "Baker's assumption text"
    assert it["target"]["local_time"] == "2026-03-10 11:05:00 EDT"
    call = item("call:sa:Call Log!3")
    assert call["target"]["sender"] == "Phone +12125550133 [p:carl]"  # same number as the link
    assert call["target"]["text"].startswith("incoming call from +12125550133")
    contact = item("contact:sa:Contacts!3#1")
    assert contact["context"] == [] and contact["device_id"] == "dev:a"
    target = {"sender": "contact list", "local_time": "no time in source"}
    assert contact["target"] == {**target, "text": "Carl Shop +12125550133"}
    r = features.render(contact)
    assert r.excerpt == "RECORD (dev:a): no time in source | contact list | Carl Shop +12125550133"
    assert "baker_claim" not in it  # only meaning, role and event assumptions carry the claim
    case_db.execute("INSERT INTO govdocs VALUES ('doc1', 'sa', 'Affidavit', 'affidavit')")
    case_db.execute(
        "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start,"
        " char_end, text) VALUES ('para:1', 'doc1', 1, 1, NULL, 0, 24, 'Ann met Carl at the lot.')"
    )
    case_db.execute(
        "INSERT INTO claims VALUES ('C1', 'para:1', 'Ann met Carl at the lot.', 'event',"
        " 'accepted', NULL)"
    )
    event = SimpleNamespace(text="The event the claim states happened", template_id="event",
                            claim_id="C1")  # fmt: skip
    ev = case_item(case_db, event, SimpleNamespace(record_id="msg:sa:Chats!2", text=""), WINDOW)
    assert ev["baker_claim"] == "Ann met Carl at the lot."

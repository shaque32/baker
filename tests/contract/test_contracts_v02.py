"""Contracts v0.2: typed assumptions, review decisions, supported basis, ids, run logging."""

import sqlite3
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core import contracts as c
from core.db import apply_schema

T0 = datetime(2026, 3, 20, 4, 0, tzinfo=UTC)


def item(**kw) -> c.EvidenceItem:
    fields = dict(
        id="e1",
        assumption_id="a1",
        record_id="msg:item1:Chats!938",
        ref=c.SourceRef(source_id="item1", locator="Chats!938"),
        stance=c.Stance.SUPPORTS,
        quote="new handle. same me",
        quote_verified=True,
        rationale="r",
        tier=c.ProvenanceTier.OBSERVED,
        status=c.EvidenceStatus.OPEN,
        model_run_id="m1",
    )
    fields.update(kw)
    return c.EvidenceItem(**fields)


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    return conn


# ------------------------------------------------------------ assumptions


def test_time_window_must_be_ordered_and_aware():
    c.TimeWindow(start_utc=T0, end_utc=T0, tz="America/New_York", raw="March 20")
    with pytest.raises(ValidationError):
        c.TimeWindow(start_utc=T0, end_utc=T0.replace(day=19), tz="UTC", raw="x")
    with pytest.raises(ValidationError):
        c.TimeWindow(start_utc=datetime(2026, 3, 20), end_utc=T0, tz="UTC", raw="x")


def test_count_needs_its_operator():
    c.AssumptionParams(expected_count=3, count_op="ge")
    with pytest.raises(ValidationError):
        c.AssumptionParams(expected_count=3)
    with pytest.raises(ValidationError):
        c.AssumptionParams(count_op="eq")


def test_duration_range():
    assert c.AssumptionParams(duration_s=(90, 150)).duration_s == (90, 150)
    for bad in ((-1, 10), (150, 90)):
        with pytest.raises(ValidationError):
            c.AssumptionParams(duration_s=bad)


def test_handles_stay_as_the_document_wrote_them():
    p = c.AssumptionParams(handles=("@alex92", "@northstar"))
    assert p.handles == ("@alex92", "@northstar")
    assert p.account_ids == ()


def test_assumption_requires_template_and_params():
    params = c.AssumptionParams(account_ids=("acct:item1:Telegram:5551234",))
    a = c.Assumption(
        id=c.assumption_id("C02", "same_account", params),
        claim_id="C02",
        kind=c.AssumptionKind.IDENTITY,
        template_id="same_account",
        template_version="1",
        params=params,
        text="Both handles are Telegram user 5551234",
        is_core=True,
        tier=c.ProvenanceTier.INFERRED,
    )
    assert a.id.startswith("asm:C02:same_account:")
    with pytest.raises(ValidationError):
        c.Assumption(**{**a.model_dump(), "template_id": "Not A Slug"})


# ------------------------------------------------------------ evidence tier and review


def test_evidence_tier_is_the_record_tier():
    with pytest.raises(ValidationError):
        item(tier=c.ProvenanceTier.AI_REVIEWED)
    with pytest.raises(ValidationError):
        item(tier=c.ProvenanceTier.CONFIRMED)


@pytest.mark.parametrize(
    ("status", "shown"),
    [
        (c.EvidenceStatus.OPEN, c.ProvenanceTier.OBSERVED),
        (c.EvidenceStatus.DISMISSED, c.ProvenanceTier.OBSERVED),
        (c.EvidenceStatus.AI_ACCEPTED, c.ProvenanceTier.AI_REVIEWED),
        (c.EvidenceStatus.ACCEPTED, c.ProvenanceTier.CONFIRMED),
    ],
)
def test_display_tier(status, shown):
    assert c.display_tier(item(status=status)) == shown


def review(**kw) -> c.ReviewDecision:
    fields = dict(
        id="rv:e1#1",
        evidence_id="e1",
        seq=1,
        reviewer_kind=c.ReviewerKind.AI,
        reviewer="ai:qwen-14b",
        status=c.EvidenceStatus.AI_ACCEPTED,
        reason="The next message confirms the same sender.",
        model_run_id="m2",
        decided_at_utc=T0,
    )
    fields.update(kw)
    return c.ReviewDecision(**fields)


def test_ai_reviewer_cannot_confirm():
    review()
    review(status=c.EvidenceStatus.DISMISSED)
    for bad in (c.EvidenceStatus.ACCEPTED, c.EvidenceStatus.OPEN):
        with pytest.raises(ValidationError):
            review(status=bad)
    with pytest.raises(ValidationError):
        review(model_run_id=None)
    with pytest.raises(ValidationError):
        review(reviewer="expert:pat")


def test_expert_review():
    kw = dict(reviewer_kind=c.ReviewerKind.EXPERT, reviewer="expert:pat", model_run_id=None)
    review(status=c.EvidenceStatus.ACCEPTED, **kw)
    review(status=c.EvidenceStatus.OPEN, **kw)
    with pytest.raises(ValidationError):
        review(status=c.EvidenceStatus.AI_ACCEPTED, **kw)
    with pytest.raises(ValidationError):
        review(status=c.EvidenceStatus.ACCEPTED, **{**kw, "model_run_id": "m2"})


def test_review_needs_a_reason():
    with pytest.raises(ValidationError):
        review(reason="")


# ------------------------------------------------------------ supported basis


def verdict(**kw) -> c.VerdictDecision:
    fields = dict(
        id="vd:C01@run:1",
        claim_id="C01",
        pipeline_run_id="run:1",
        verdict=c.Verdict.SUPPORTED,
        supported_basis=c.SupportedBasis.AI_REVIEWED,
        rule_version="0.1.0",
        reasons=("r",),
        cited_evidence_ids=("e1",),
        decided_at_utc=T0,
    )
    fields.update(kw)
    return c.VerdictDecision(**fields)


def test_supported_needs_basis_and_evidence():
    verdict()
    with pytest.raises(ValidationError):
        verdict(supported_basis=None)
    with pytest.raises(ValidationError):
        verdict(cited_evidence_ids=())


def test_basis_only_for_supported():
    verdict(verdict=c.Verdict.UNPROVEN, supported_basis=None, cited_evidence_ids=())
    with pytest.raises(ValidationError):
        verdict(verdict=c.Verdict.CONTRADICTED)


def test_prediction_basis_iff_supported():
    c.Prediction(claim_id="C1", verdict=c.Verdict.SUPPORTED, supported_basis="confirmed")
    c.Prediction(claim_id="C1", verdict=c.Verdict.UNPROVEN)
    with pytest.raises(ValidationError):
        c.Prediction(claim_id="C1", verdict=c.Verdict.SUPPORTED)
    with pytest.raises(ValidationError):
        c.Prediction(claim_id="C1", verdict=c.Verdict.UNPROVEN, supported_basis="ai_reviewed")


# ------------------------------------------------------------ stipulations


def test_only_an_expert_confirms_a_stipulation():
    base = dict(
        id=c.stipulation_id(c.StipulationKind.DEVICE_OWNER, "dev:item1"),
        kind=c.StipulationKind.DEVICE_OWNER,
        subject_id="dev:item1",
        person_id="p:petrov",
        statement="Item 1 is PETROV's phone.",
    )
    c.Stipulation(status=c.StipulationStatus.PROPOSED, **base)
    c.Stipulation(
        status=c.StipulationStatus.CONFIRMED, decided_by="expert:pat", decided_at_utc=T0, **base
    )
    with pytest.raises(ValidationError):
        c.Stipulation(status=c.StipulationStatus.CONFIRMED, **base)
    with pytest.raises(ValidationError):
        c.Stipulation(
            status=c.StipulationStatus.CONFIRMED, decided_by="ai:x", decided_at_utc=T0, **base
        )


# ------------------------------------------------------------ ids


def test_ids_are_deterministic():
    p1 = c.AssumptionParams(account_ids=("a", "b"), channels=("Telegram",))
    p2 = c.AssumptionParams(channels=("Telegram",), account_ids=("a", "b"))
    assert c.assumption_id("C1", "t", p1) == c.assumption_id("C1", "t", p2)
    assert c.assumption_id("C1", "t", p1) != c.assumption_id(
        "C1", "t", c.AssumptionParams(account_ids=("a",))
    )
    e1 = c.evidence_id("asm:x", "msg:item1:Chats!1", c.Stance.SUPPORTS, "hi")
    assert e1 == c.evidence_id("asm:x", "msg:item1:Chats!1", c.Stance.SUPPORTS, "hi")
    # a changed label is a new item, so an old review never carries over to it
    assert e1 != c.evidence_id("asm:x", "msg:item1:Chats!1", c.Stance.CONTRADICTS, "hi")
    assert e1 != c.evidence_id("asm:x", "msg:item1:Chats!1", c.Stance.SUPPORTS, "hi!")
    assert c.check_id("asm:x", "sender", "1") == "chk:asm:x|sender@1"
    assert c.review_id(e1, 2) == f"rv:{e1}#2"
    assert c.verdict_id("C1", "run:1") == "vd:C1@run:1"
    assert c.model_call_id("m1", 3) == "mc:m1#3"


def test_canonical_json_is_stable():
    assert c.canonical_json({"b": 1, "a": "ж"}) == '{"a":"ж","b":1}'


# ------------------------------------------------------------ schema behaviour


def _seed_evidence(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        INSERT INTO sources VALUES ('item1','synthetic','full_extraction','logical','f',
            'x','t',NULL,NULL,'2026-01-01T00:00:00Z');
        INSERT INTO govdocs VALUES ('g','item1','t','affidavit');
        INSERT INTO govdoc_paragraphs VALUES ('p','g',1,1,'1',0,1,'t',0);
        INSERT INTO claims VALUES ('C1','p','t','identity','accepted',NULL);
        INSERT INTO assumptions VALUES ('a1','C1','identity','t','1','{}','t',1,'inferred');
        INSERT INTO pipeline_runs VALUES ('run:1','2026-01-01T00:00:00Z',NULL,'running',
            '0.0.1','0.2.0','0.1.0','{}',NULL);
        INSERT INTO model_runs VALUES ('m1','run:1','review','m','h','1',NULL,'{}',0,
            '2026-01-01T00:00:00Z');
        INSERT INTO evidence_items VALUES ('e1','a1','item1','Chats!1','msg:item1:Chats!1',
            'supports','q','r','observed','m1');
        """
    )


def test_review_history_is_append_only(db):
    _seed_evidence(db)
    status = "SELECT status FROM evidence_status WHERE evidence_id='e1'"
    assert db.execute(status).fetchone() == ("open",)
    db.execute(
        "INSERT INTO evidence_reviews VALUES ('rv:e1#1','e1',1,'ai','ai:m','ai_accepted',"
        "'r','m1',NULL,'2026-01-01T00:00:00Z')"
    )
    assert db.execute(status).fetchone() == ("ai_accepted",)
    db.execute(
        "INSERT INTO evidence_reviews VALUES ('rv:e1#2','e1',2,'expert','expert:pat',"
        "'dismissed','r',NULL,NULL,'2026-01-01T00:00:00Z')"
    )
    assert db.execute(status).fetchone() == ("dismissed",)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE evidence_reviews SET status='accepted'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM evidence_reviews")


def test_schema_blocks_ai_confirmation(db):
    _seed_evidence(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO evidence_reviews VALUES ('rv:e1#1','e1',1,'ai','ai:m','accepted',"
            "'r','m1',NULL,'2026-01-01T00:00:00Z')"
        )


def test_schema_evidence_tier_is_record_tier(db):
    _seed_evidence(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO evidence_items VALUES ('e2','a1','item1','Chats!2','msg:item1:Chats!2',"
            "'supports','q','r','ai_reviewed','m1')"
        )


def test_schema_supported_needs_basis(db):
    _seed_evidence(db)
    row = "INSERT INTO verdicts VALUES (?,'C1','run:1',?,?,'0.1.0','[]','[]','{}','t',NULL,NULL)"
    db.execute(row, ("v1", "supported", "ai_reviewed"))
    db.execute(row, ("v2", "unproven", None))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(row, ("v3", "supported", None))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(row, ("v4", "contradicted", "confirmed"))


def test_model_calls_and_audit_log_are_append_only(db):
    _seed_evidence(db)
    db.execute("INSERT INTO model_calls VALUES ('mc:m1#1','m1',1,'[]','p','','error','boom','t')")
    db.execute("INSERT INTO audit_log VALUES (1,'t','system','x','{}','','h')")
    for sql in (
        "UPDATE model_calls SET raw_output='x'",
        "DELETE FROM model_calls",
        "UPDATE audit_log SET actor='y'",
        "DELETE FROM audit_log",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(sql)


def test_stipulation_needs_expert_in_schema(db):
    db.execute("INSERT INTO persons VALUES ('p1','PETROV','expert:pat')")
    db.execute(
        "INSERT INTO stipulations VALUES ('s1','device_owner','dev:item1','p1','x','proposed',"
        "NULL,NULL)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO stipulations VALUES ('s2','device_owner','dev:item2','p1','x',"
            "'confirmed','ai:m','t')"
        )

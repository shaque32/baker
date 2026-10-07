"""Assumption templates: typed parameters, deterministic output, fail-closed building."""

from datetime import UTC, datetime

import pytest

from core.audit.assumptions import (
    TEMPLATES,
    Proposal,
    TemplateAssumptionBuilder,
    instantiate,
    local_window,
    parse_params,
    template_of,
    templates_for,
)
from core.audit.checks import CHECKS, checks_for
from core.contracts import AssumptionParams, Claim, ClaimStatus, ClaimType, ProvenanceTier

NY = "America/New_York"
GAP = local_window(datetime(2026, 3, 20), datetime(2026, 3, 24), NY, "March 20 to 23")
PEOPLE = {"person_ids": ["person:petrov", "person:reyes"]}


def claim(claim_type: ClaimType = ClaimType.ABSENCE) -> Claim:
    return Claim(
        id="C14",
        paragraph_id="p:11",
        text="No contact between March 20 and March 23.",
        claim_type=claim_type,
        status=ClaimStatus.ACCEPTED,
    )


def test_every_template_names_only_known_checks_and_real_fields() -> None:
    fields = set(AssumptionParams.model_fields)
    for t in TEMPLATES.values():
        assert set(t.checks) <= set(CHECKS), t.id
        assert t.required <= t.allowed <= fields, t.id
        assert t.claim_types, t.id


def test_local_window_is_half_open_wall_clock_resolved_to_inclusive_utc() -> None:
    assert GAP.start_utc == datetime(2026, 3, 20, 4, tzinfo=UTC)  # EDT after Mar 8
    assert GAP.end_utc == datetime(2026, 3, 24, 3, 59, 59, 999999, tzinfo=UTC)
    assert GAP.raw == "March 20 to 23" and GAP.tz == NY
    winter = local_window(datetime(2026, 3, 4, 21), datetime(2026, 3, 4, 22), NY, "9 p.m.")
    assert winter.start_utc == datetime(2026, 3, 5, 2, tzinfo=UTC)  # EST before Mar 8
    with pytest.raises(ValueError):
        local_window(datetime(2026, 3, 20, tzinfo=UTC), datetime(2026, 3, 24), NY, "x")
    with pytest.raises(ValueError):
        local_window(datetime(2026, 3, 20), datetime(2026, 3, 24), "Eastern", "x")
    with pytest.raises(ValueError):
        local_window(datetime(2026, 3, 24), datetime(2026, 3, 20), NY, "x")


@pytest.mark.parametrize(
    ("template_id", "params", "problem"),
    [
        ("no_contact", {"person_ids": ["person:petrov"], "window": GAP}, "two parties"),
        ("no_contact", PEOPLE, "needs window"),
        ("no_contact", {**PEOPLE, "window": GAP, "quoted_text": "x"}, "does not take"),
        ("sender", {"quoted_text": "ok"}, "exactly one party"),
        ("sender", {"quoted_text": "ok", **PEOPLE}, "exactly one party"),
        ("record_time", {"window": GAP, **PEOPLE}, "quoted text"),
        ("record_time", {"window": GAP, "channels": ["call"]}, "at least one"),
        (
            "record_time",
            {"window": GAP, "quoted_text": "ok", "duration_s": (1, 2)},
            "only applies to calls",
        ),
        ("no_contact", {**PEOPLE, "window": GAP, "duration_s": (1, 2)}, "does not take"),
        (
            "message_count",
            {**PEOPLE, "window": GAP, "expected_count": 3, "count_op": "eq"},
            "needs device_ids",
        ),
        (
            "message_count",
            {
                **PEOPLE,
                "window": GAP,
                "expected_count": 3,
                "count_op": "eq",
                "device_ids": ["dev:item1", "dev:item2"],
            },
            "one phone",
        ),  # fmt: skip
        ("same_account", {"channels": ["Telegram"], "handles": ["@a"]}, "two handles"),
        ("same_account", {"channels": ["Telegram", "SMS"], "handles": ["@a", "@b"]}, "one app"),
        ("contact_entry", {"device_ids": ["d"], "quoted_text": "x"}, "needs account_ids"),
        ("no_such_template", {}, "unknown template"),
    ],
)
def test_bad_parameters_are_refused(template_id: str, params: dict, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        parse_params(template_id, params)


def test_contract_rules_still_apply() -> None:
    with pytest.raises(ValueError):
        parse_params("message_count", {**PEOPLE, "window": GAP, "expected_count": 3,
                                       "device_ids": ["dev:item1"]})  # fmt: skip


def test_instantiate_is_deterministic_and_always_inferred() -> None:
    a = instantiate("C14", "no_contact", {**PEOPLE, "window": GAP})
    b = instantiate("C14", "no_contact", {"window": GAP, **PEOPLE})
    assert a == b
    assert a.id.startswith("asm:C14:no_contact:")
    assert a.tier is ProvenanceTier.INFERRED
    assert a.template_id == "no_contact" and a.template_version
    assert a.text == (
        'No contact between person:petrov and person:reyes "March 20 to 23" (America/New_York) '
        "on every phone"
    )
    assert [c.name for c in checks_for(a)] == ["absence"]


def test_builder_fails_closed_and_keeps_duplicates_once() -> None:
    good = {**PEOPLE, "window": GAP}
    proposals = [
        Proposal("no_contact", good),
        Proposal("no_contact", dict(good)),  # duplicate
        Proposal("no_such_template", {}),
        # same_account is not allowed for absence claims
        Proposal("same_account", {"channels": ["Telegram"], "handles": ["@a", "@b"]}),
        Proposal("no_contact", {"person_ids": ["person:petrov"], "window": GAP}),
        Proposal("event", {"person_ids": ["person:petrov"], "channels": ["WhatsApp"]}, False),
    ]  # fmt: skip
    builder = TemplateAssumptionBuilder(lambda c, allowed: proposals)
    built = builder.build(claim())
    assert [a.template_id for a in built] == ["no_contact", "event"]
    assert [a.is_core for a in built] == [True, False]
    assert len(builder.rejected) == 3


def test_filler_only_sees_templates_allowed_for_the_claim_type() -> None:
    seen: list[str] = []

    def filler(c: Claim, allowed: list) -> list[Proposal]:
        seen.extend(t.id for t in allowed)
        return []

    TemplateAssumptionBuilder(filler).build(claim(ClaimType.ABSENCE))
    assert "no_contact" in seen and "message_count" not in seen
    assert {t.id for t in templates_for(ClaimType.COUNT)} >= {"message_count", "same_account"}


def test_model_only_templates_have_no_checks() -> None:
    a = instantiate("C06", "meaning", {"quoted_text": "the package will be at marcs"})
    assert template_of(a) is TEMPLATES["meaning"]
    assert checks_for(a) == []

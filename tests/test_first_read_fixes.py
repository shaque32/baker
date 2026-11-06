"""Fixes from the first-time-user review of the demo pages (2026-11-04): counts that add up,
no pick list starting on a person, the records a failed check cites shown as that claim's
evidence, the same record shown twice said so, an untested claim's plain reason first, a
timeline note that names the phone without a zone, and the demo exhibit."""

from __future__ import annotations

import re

import pytest

from core.casework import cases
from core.db import connect
from core.review.status import claim_states
from eval import demo
from ui import pages
from ui.app import App, Request

PORT = 8766
HOST = {"host": f"127.0.0.1:{PORT}"}


@pytest.fixture(scope="module")
def app(tmp_path_factory) -> App:
    root = tmp_path_factory.mktemp("demo")
    demo.reset(root)
    (case,) = cases.list_cases(demo.cases_dir(root))
    a = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    a.open_case(case)
    a.case_db = case.db  # type: ignore[attr-defined]
    return a


def _get(app: App, path: str, **query: str) -> str:
    return app.handle(Request("GET", path, query, dict(HOST))).body.decode()


def _tiles(body: str) -> dict[str, int]:
    return {
        name: int(n)
        for name, n in re.findall(
            r"<span class='name'>([^<]+)</span><span class='n'>(\d+)</span>", body
        )
    }


def test_verdict_counts_add_up_to_every_claim_and_needs_you_counts_across_them(app):
    body = _get(app, "/claims")
    tiles = _tiles(body)
    conn = connect(app.case_db)  # type: ignore[attr-defined]
    total = len(claim_states(conn))
    verdicts = sum(n for name, n in tiles.items() if name != "Needs you")
    assert verdicts == total, tiles
    assert 0 < tiles["Needs you"] < total
    # a claim that waits on the expert is listed under its verdict too, tagged
    assert "<span class='gap you'>Needs you</span>" in body
    # contradicted claims stay open; only supported folds while claims wait
    con = body.split("<section class='group' id='con'>", 1)[1].split("</section>", 1)[0]
    assert "<details class='fold'>" not in con


def test_case_page_counts_match_the_claims_tiles(app):
    body = _get(app, "/")
    found = dict(re.findall(r"<span class='name t-[a-z]+'>([^<]+)</span> <b>(\d+)</b>", body))
    tiles = _tiles(_get(app, "/claims"))
    for name, n in found.items():
        assert tiles[name] == int(n), name


def test_identity_pick_lists_start_on_choose_not_a_person(app):
    body = _get(app, "/identities")
    for sel in re.findall(r"<select name='(?:id|account|person)'[^>]*>.*?</select>", body, re.S):
        first = re.search(r"<option[^>]*>", sel).group(0)
        assert "value=''" in first and "selected" in first, sel[:200]
        assert " required" in sel.split(">", 1)[0]


def test_a_contradicted_claim_shows_the_records_its_failed_check_cites(app):
    body = _get(app, "/claim", id="C14")
    assert "Records the failed check cites" in body
    assert "No relevant evidence items." not in body


def test_an_untested_claim_leads_with_the_plain_reason_and_points_to_its_paragraph(app):
    body = _get(app, "/claim", id="D03")
    plain = body.index("Not tested: Mabillon could not set up what to check")
    assert body.index("Why code could not set it up") > plain
    assert "Other claims from the same paragraph:" in body and ">C09</a>" in body


def test_an_absence_gap_shows_what_was_searched_in_the_verdict_box(app):
    body = _get(app, "/claim", id="D01")
    verdict = body.split("<div class='card' id='verdict'>", 1)[1].split("id='evidence'", 1)[0]
    assert "<b>Searched</b>" in verdict
    assert "cannot show that something is absent" in verdict


def test_timeline_names_no_phone_as_zoneless_when_every_phone_states_one(app):
    # both demo phones state America/New_York; the old note counted distinct zones (1) against
    # phones (2) and told every row that a phone states none
    body = _get(app, "/timeline")
    assert "not state its time zone" not in body and "not state their time zone" not in body


def test_the_demo_has_one_exhibit_and_its_messages_are_found(app):
    body = _get(app, "/exhibits")
    assert demo.DEMO_EXHIBIT_LABEL in body and "2 of 2" in body


def test_help_defines_the_screens_words(app):
    body = _get(app, "/help")
    for word in ("Unproven", "observed", "derived", "inferred", "ai_reviewed", "confirmed"):
        assert f"<dt>{word}</dt>" in body
    assert "It does not mean the claim is false." in body


def test_the_request_letter_has_its_own_tab(app):
    body = _get(app, "/request-letter")
    assert "<a href='/request-letter' class=on>Request letter</a>" in body


def test_the_folded_stand_in_banner_is_built_from_the_run(app):
    conn = connect(app.case_db)  # type: ignore[attr-defined]
    note = pages.stand_in_note(conn)
    assert note.startswith("<div class='banner'><details>") and "not made by a person" in note


def test_selection_says_where_each_quote_not_placed_is_listed(app):
    body = _get(app, "/selection")
    assert "Each quote not placed is listed with its paragraph below." in body
    # demo: four paragraphs place no quote, and one more quote not placed sits with ¶15
    assert "1 more quote not placed is listed above" in body


def test_the_gaps_strip_gives_each_app_the_cards_pace(app):
    body = _get(app, "/gaps")
    q = r"<span class=\"q\">([^<]+)</span>"
    checked = 0
    for phone in body.split("<h2>")[1:]:  # each phone's strip, then its cards
        strip = rf"<div class='strip'><div>{q}</div>.*?([\d.]+) a day</div>"
        paces = dict(re.findall(strip, phone))
        # each phone-wide app stretch: "No WhatsApp messages on ...", then its card's pace
        for app_name, pace in re.findall(
            rf"No {q} messages on .*?<dt>Pace</dt><dd>([\d.]+)", phone
        ):
            assert paces[app_name] == pace, app_name
            checked += 1
    assert checked


def test_the_report_reads_plainly_and_keeps_every_id_in_its_appendix(app):
    body = _get(app, "/report")
    limits = body.split("<h2>Limitations</h2>", 1)[1].split("<h2>", 1)[0]
    for tier in ("observed", "derived", "inferred", "ai_reviewed", "confirmed"):
        assert f"<strong>{tier}</strong>:" in limits
    # no claim here is Supported (AI-reviewed), so that label is not defined; the rule stays
    assert "would mean a local AI reviewer" not in limits
    assert "no claim reaches supported on AI review alone" in limits
    claims = body.split("<h2>Claims</h2>", 1)[1].split("<h2>Searches and coverage</h2>", 1)[0]
    assert "Rule 3:" not in claims and "How this verdict was reached" not in claims
    assert "<a href='#ids-C01'>Appendix, C01</a>" in claims
    appendix = body.split("<h2 id='appendix'>", 1)[1]
    assert "Rule 3:" in appendix and "How this verdict was reached" in appendix
    assert "<div class='claim-ids' id='ids-C01'>" in appendix


def test_a_zoneless_phone_label_prints_as_cited_text(app):
    # a phone label is source text: one holding a word the tool never says (Codex on #216)
    # must print cited, so the report's word check passes
    import dataclasses

    from core.audit.invariants import check_report_text
    from core.report import timeline as timeline_html

    conn = connect(app.case_db)  # type: ignore[attr-defined]
    views = timeline_html.compute(conn, timeline_html.Settings())
    row = dataclasses.replace(views.rows[0], zoneless=("Deleted records",))
    out = timeline_html.timeline_rows([row], views.data)
    assert "does not state its time zone" in out
    check_report_text(out)

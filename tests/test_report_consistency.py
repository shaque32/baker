"""The review screen and the report agree, and the report is reproducible. On synthetic case01.

Both the screen (ui/pages.py) and the report (core/report/html.py) read claims through
core/review/status.py. These tests render the same case both ways, at several points of an
expert's review, and compare what each says per claim: the claim's status, its verdict label
(and pill style) and the ids of the evidence items it shows.

Reproducibility: the same inputs, versions and expert decisions give the same report hash. With
the clocks pinned, byte for byte. With the audit and the expert working at other times, after
masking only the time fields core/report/html.py lists (decision times, run ids named for their
start time, the run's start time, the audit log's entry times and its last hash).

case02 is the held-out case and is never used here.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from core import build, pipeline
from core.audit import quotes
from core.contracts import ClaimStatus, ClaimType, EvidenceStatus, ModelRun, Stance, Verdict
from core.report.html import record_line, render_report
from core.review import actions
from core.review.redecide import redecide
from core.review.status import (
    AWAITING_EXPERT,
    CONTRADICTION_FOUND,
    LABELING_INCOMPLETE,
    NOT_AUDITED,
    NOT_TESTED,
    SUPPORTED_EXPERT,
    claim_state,
)
from eval import run_pipeline
from tests.test_review_screen import (
    EXPERT,
    PORT,
    AcceptsEverything,
    EverythingSupports,
    _filler,
    _spec,
    get,
    key_items,
    post,
)
from ui.app import App

START = datetime(2026, 10, 7, tzinfo=UTC)


class ContradictsOn(EverythingSupports):
    """Every record supports, except that it contradicts each assumption of the claims named."""

    def __init__(self, *claim_ids: str) -> None:
        self.claim_ids = claim_ids

    def label(self, assumption, candidate):  # noqa: ANN001, ANN201
        out = super().label(assumption, candidate)
        if assumption.claim_id in self.claim_ids:
            return out.model_copy(update={"stance": Stance.CONTRADICTS})
        return out


def _audit(
    conn: sqlite3.Connection,
    at: datetime,
    progress=None,  # noqa: ANN001
    labeler: EverythingSupports | None = None,
) -> None:
    comps = pipeline.real_components(
        conn,
        replace={"labeler": labeler or EverythingSupports(), "reviewer": AcceptsEverything()},
        filler=_filler(_spec()),
    )
    comps.model_runs = (
        *comps.model_runs,
        *(
            ModelRun(
                id=f"mr:test-{p}",
                purpose=p,
                model_name=f"test-{p}",
                model_sha256="0" * 64,
                prompt_version="none",
                params={},
                seed=0,
                started_at_utc=START,
            )
            for p in ("stance", "review")
        ),
    )
    pipeline.run_audit(conn, comps, clock=lambda: at, progress=progress)


def _review(conn: sqlite3.Connection, start: datetime) -> None:
    """One expert's review, each step at its own time after start: accept C05's key evidence,
    dismiss a supporting item on C06, re-run the verdicts, confirm C05, override C07, restate
    a device-owner stipulation and link an account to a person (both print their time)."""
    at = lambda h: lambda: start + timedelta(hours=h)  # noqa: E731
    for eid in key_items(conn, "C05"):
        actions.decide_evidence(conn, eid, EvidenceStatus.ACCEPTED, EXPERT, "Matches.", at(1))
    first = next(e.id for e in claim_state(conn, "C06").evidence if e.stance == Stance.SUPPORTS)
    actions.decide_evidence(conn, first, EvidenceStatus.DISMISSED, EXPERT, "Not it.", at(1))
    redecide(conn, EXPERT, at(2))
    actions.confirm_verdict(conn, "C05", EXPERT, clock=at(3))
    actions.override_verdict(conn, "C07", Verdict.CONTRADICTED, EXPERT, "Reads x.", clock=at(3))
    actions.stipulate_device_owner(conn, "dev:item1", "Daniel Petrov", EXPERT, at(3))
    actions.link_account(
        conn, "acct:item1:Instagram:m.reyes.auto", "person:dev:item2:owner", EXPERT, "Bio.", at(3)
    )


def _build(path: Path, start: datetime) -> sqlite3.Connection:
    conn = run_pipeline.build_case("case01", path)
    _audit(conn, start)
    _review(conn, start)
    return conn


# ---------------------------------------------------------------- what each side says


def _report_claims(text: str) -> dict[str, dict]:
    """claim id -> status, verdict label, pill classes and evidence ids, read from the report."""
    end = text.index("<h2>Searches and coverage</h2>")
    starts = [m.start() for m in re.finditer(r'<div class="claim" id="', text)]
    out: dict[str, dict] = {}
    for i, s in enumerate(starts):
        block = text[s : starts[i + 1] if i + 1 < len(starts) else end]
        cid = html.unescape(re.match(r'<div class="claim" id="([^"]*)"', block).group(1))
        pill = re.search(r'<span class="verdict ([^"]*)">(.*?)</span>', block)
        table = block.split("<th>Evidence</th>", 1)
        out[cid] = {
            "status": re.search(r"· claim ([a-z_]+)", block).group(1),
            "label": html.unescape(pill.group(2)),
            "css": pill.group(1),
            "evidence": [html.unescape(x) for x in re.findall(r"<tr id='([^']*)'>", table[-1])]
            if len(table) == 2
            else [],
        }
    return out


def _screen_claims(app: App, conn: sqlite3.Connection) -> dict[str, dict]:
    """The same, read from the claims queue and each claim's page on the review screen."""
    ledger = get(app, "/claims").text.split("<ul class='ledger'>", 1)[1].split("</ul>", 1)[0]
    out: dict[str, dict] = {}
    for href, css, label in re.findall(
        r"<a href='([^']*)'>[^<]*</a>.*?<span class='verdict ([^']*)'>(.*?)</span>", ledger
    ):
        cid = parse_qs(urlparse(html.unescape(href)).query)["id"][0]
        page = get(app, "/claim", id=cid).text
        main = page.split("<div class='claim-head'>", 1)[1]  # past the side ledger
        card = main.split("<div class='card' id='verdict'>", 1)[1]
        pill = re.search(r"<span class='verdict ([^']*)'>(.*?)</span>", card)
        out[cid] = {
            "status": re.search(r"· claim ([a-z_]+)", main).group(1),
            "label": html.unescape(pill.group(2)),
            "css": pill.group(1),
            "evidence": [
                html.unescape(x) for x in re.findall(r"<div class='item' id='([^']*)'>", main)
            ],
            "ledger": (html.unescape(label), css),
        }
    return out


def _assert_agree(app: App, conn: sqlite3.Connection) -> Counter:
    report = _report_claims(render_report(conn))
    screen = _screen_claims(app, conn)
    assert screen, "nothing parsed from the screen"
    assert set(screen) == set(report), "the screen and the report list different claims"
    for cid, r in report.items():
        s = screen[cid]
        assert s["ledger"] == (s["label"], s["css"]), f"{cid}: queue and claim page differ"
        for key in ("status", "label", "css"):
            assert s[key] == r[key], f"{cid}: {key} {s[key]!r} on screen, {r[key]!r} in report"
        # the same items, in any order (the screen groups them by what the expert should do)
        assert sorted(s["evidence"]) == sorted(r["evidence"]), f"{cid}: evidence differs"
        assert len(set(r["evidence"])) == len(r["evidence"])
    return Counter(r["label"] for r in report.values())


def test_screen_and_report_agree_on_every_claim_through_a_review(tmp_path):
    db = tmp_path / "case01.db"
    conn = run_pipeline.build_case("case01", db)
    app = App(db, expert="Test Expert", port=PORT)
    try:
        assert set(_assert_agree(app, conn)) == {NOT_AUDITED}  # before any audit

        _audit(conn, START)
        labels = _assert_agree(app, conn)
        assert labels[AWAITING_EXPERT] > 0

        _review(conn, START)
        labels = _assert_agree(app, conn)
        assert labels[SUPPORTED_EXPERT] >= 1 and labels["Contradicted (expert override)"] == 1

        # decided after the run, a claim added, one edited and one removed after the audit
        later = lambda: START + timedelta(hours=4)  # noqa: E731
        eid = next(e.id for e in claim_state(conn, "C08").evidence if e.stance != Stance.IRRELEVANT)
        actions.decide_evidence(conn, eid, EvidenceStatus.ACCEPTED, EXPERT, "Seen.", later)
        para = conn.execute("SELECT paragraph_id FROM claims WHERE id = 'C01'").fetchone()[0]
        actions.add_claim(conn, "C21", para, 'Sent "ok".', ClaimType.EVENT, EXPERT, later)
        actions.set_claim_status(
            conn, "C02", ClaimStatus.EDITED, EXPERT, text="New wording.", clock=later
        )
        actions.set_claim_status(conn, "C03", ClaimStatus.REMOVED, EXPERT, clock=later)
        labels = _assert_agree(app, conn)
        assert labels[NOT_AUDITED] == 1 and "C03" not in _report_claims(render_report(conn))

        # a full audit again: the added claim has no assumption to check (not tested), and the
        # model reads C16's records as contradicting it: under rules 0.3.0 that waits for the
        # expert, on the screen and in the report alike
        _audit(conn, START + timedelta(hours=5), labeler=ContradictsOn("C16"))
        labels = _assert_agree(app, conn)
        assert labels[NOT_TESTED] == 1
        assert claim_state(conn, "C16").label == CONTRADICTION_FOUND
        assert CONTRADICTION_FOUND in get(app, "/claim", id="C16").text

        # an audit stopped after two claims: the rest print as labeling incomplete on both
        def stop_after_two(done, total, decision):  # noqa: ANN001, ANN202
            if done == 2:
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            _audit(conn, START + timedelta(hours=6), progress=stop_after_two)
        assert pipeline.view_run(conn).get("partial")
        assert _assert_agree(app, conn)[LABELING_INCOMPLETE] > 0
    finally:
        conn.close()


def test_one_click_confirms_a_contradiction_the_same_on_screen_and_in_the_report(tmp_path):
    """Rules 0.3.0: a model's contradiction waits for the expert. One click on the claim page
    records the acceptance and its reason in the audit log and re-runs the verdicts."""
    db = tmp_path / "case01.db"
    conn = run_pipeline.build_case("case01", db)
    app = App(db, expert="Test Expert", port=PORT)
    try:
        _audit(conn, START, labeler=ContradictsOn("C16"))
        labels = _assert_agree(app, conn)
        assert labels[CONTRADICTION_FOUND] >= 1
        st = claim_state(conn, "C16")
        assert st.label == CONTRADICTION_FOUND and st.decision.verdict == Verdict.UNPROVEN
        page = get(app, "/claim", id="C16").text
        assert "Confirm contradiction" in page
        assert CONTRADICTION_FOUND in render_report(conn)
        for word in ("uncertain", "low confidence", "confidence score"):
            assert word not in page.lower()

        eid = next(x.id for x in st.evidence if st.to_confirm(x))

        def decisions() -> int:
            return conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE action = 'evidence.decide'"
            ).fetchone()[0]

        # a confirm needs a reason, like every expert decision
        post(app, "/evidence/confirm", id=eid, status="accepted", reason=" ")
        assert app.flash[1] is True and decisions() == 0
        r = post(app, "/evidence/confirm", id=eid, status="accepted", reason="Two people.")
        assert r.status == 303
        assert claim_state(conn, "C16").label == "Contradicted"
        labels = _assert_agree(app, conn)
        assert labels["Contradicted"] >= 1
        (payload,) = conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = 'evidence.decide'"
            " AND payload_json LIKE ?",
            (f'%"{eid}"%',),
        ).fetchone()
        assert json.loads(payload)["reason"] == "Two people."
        assert json.loads(payload)["status"] == "accepted"

        # an item no longer waiting (here the claim is already contradicted; a page left open
        # across a later audit is the same) is refused, and nothing more is recorded (Codex)
        before = decisions()
        post(app, "/evidence/confirm", id=eid, status="accepted", reason="Again.")
        assert app.flash[1] is True and "not waiting" in app.flash[0]
        assert decisions() == before
    finally:
        conn.close()


def test_a_confirm_whose_verdict_rerun_fails_still_says_it_was_recorded(tmp_path, monkeypatch):
    """Codex on #98: the decision is committed before the re-run, so a failing re-run must not
    read as "Not recorded", or a retry records the decision twice."""
    from core.audit.invariants import InvariantViolation

    db = tmp_path / "case01.db"
    conn = run_pipeline.build_case("case01", db)
    app = App(db, expert="Test Expert", port=PORT)
    try:
        _audit(conn, START, labeler=ContradictsOn("C16"))
        st = claim_state(conn, "C16")
        eid = next(x.id for x in st.evidence if st.to_confirm(x))

        def broken(conn):  # noqa: ANN001, ANN202
            raise InvariantViolation("stand-in failure")

        monkeypatch.setattr(app, "_redecide", broken)
        post(app, "/evidence/confirm", id=eid, status="accepted", reason="Two people.")
        assert app.flash[1] is False
        assert "recorded" in app.flash[0] and "not re-run" in app.flash[0]
    finally:
        conn.close()


def test_the_screen_and_the_report_show_a_call_with_the_same_times(tmp_path):
    # Grok review on #76: the report shows a call's UTC and printed time beside its line, and the
    # claim page must show the same. Both render it with core.report.html.record_line.
    db = tmp_path / "case01.db"
    conn = run_pipeline.build_case("case01", db)
    try:
        _audit(conn, START)
        app = App(db, expert="Test Expert", port=PORT)
        report = render_report(conn)
        calls = conn.execute(
            "SELECT DISTINCT e.record_id, a.claim_id FROM evidence_items e"
            " JOIN assumptions a ON a.id = e.assumption_id WHERE e.record_id LIKE 'call:%'"
            " ORDER BY e.record_id, a.claim_id"
        ).fetchall()
        assert calls
        for record_id, claim_id in calls:
            line = record_line(conn, record_id)
            utc, raw = conn.execute(
                "SELECT ts_utc, ts_raw FROM calls WHERE id = ?", (record_id,)
            ).fetchone()
            assert f"UTC {html.escape(utc)}" in line and html.escape(raw) in line
            assert line in report, f"{record_id}: not in the report as {line!r}"
            page = get(app, "/claim", id=claim_id).text
            assert line in page, f"{record_id}: the claim page for {claim_id} shows it otherwise"
    finally:
        conn.close()


def test_the_report_and_the_screen_stamp_every_version_a_result_depends_on(tmp_path):
    # Pilot gate 3 (docs/PILOT_GATES.md): every report records each model file's SHA-256 and
    # seed, the Baker version, the rule version and the quote-check version. The report's top
    # line carries the run's versions so a printed first page names them; the screen says the
    # same; the eval's run.json stamps them too.
    db = tmp_path / "case01.db"
    conn = run_pipeline.build_case("case01", db)
    try:
        _audit(conn, START)
        run = pipeline.view_run(conn)
        assert run is not None
        built = build.build_info()
        assert run["config"]["build"] == built  # the release and commit that ran, not a constant
        assert built["release"] == build.release() != build.NOT_RECORDED
        here = html.escape(build.label(built))
        stamp = (
            f"Baker {here} · pipeline {html.escape(run['baker_version'])} · rules "
            f"{html.escape(run['rule_version'])} · quote check {quotes.VERSION}"
        )
        report = render_report(conn)
        top = report.split("<h1>Baker claims report</h1>", 1)[1].split("</p>", 1)[0]
        assert stamp in top
        assert f"<tr><td>Quote check</td><td class='mono'>{quotes.VERSION}</td></tr>" in report
        models = conn.execute("SELECT purpose, model_sha256, seed FROM model_runs").fetchall()
        assert models
        for purpose, sha, seed in models:
            assert re.search(
                rf"<tr><td>Model for {re.escape(purpose)}</td><td class='mono'>[^<]*"
                rf"SHA-256 {sha}, seed {seed if seed is not None else 'not recorded'}</td></tr>",
                report,
            ), purpose
        app = App(db, expert="Test Expert", port=PORT)
        screen = get(app, "/").text
        assert (
            f"Baker {here}, rule version {html.escape(run['rule_version'])}, quote check "
            f"{quotes.VERSION}," in (screen)
        )
        versions = run_pipeline.run_versions(conn)
        assert versions["quote_check"] == quotes.VERSION
        assert versions["rules"] == run["rule_version"]
        assert versions["pipeline"] == run["baker_version"]
        assert versions["build"] == built
        assert f"<tr><td>Baker build</td><td class='mono'>{here}</td></tr>" in report
        assert {(m["purpose"], m["sha256"], m["seed"]) for m in versions["models"]} == set(models)
    finally:
        conn.close()


def test_a_rules_only_rerun_on_a_newer_build_names_the_build_its_evidence_came_from(tmp_path):
    # Codex on #91: the re-run reuses the full audit's labels, so its stamp names that build too.
    conn = run_pipeline.build_case("case01", tmp_path / "case01.db")
    try:
        _audit(conn, START)
        old = {"release": "0.0.0", "commit": "a" * 40, "dirty": False}
        with conn:  # as if the full audit had run on an older build
            conn.execute(
                "UPDATE pipeline_runs SET config_json = json_set(config_json, '$.build', json(?))",
                (json.dumps(old),),
            )
        redecide(conn, EXPERT, lambda: START + timedelta(hours=1))
        run = pipeline.view_run(conn)
        assert run["config"]["mode"] == "rules_only"
        assert run["config"]["build"] == build.build_info()
        assert run["config"]["evidence_build"] == old
        here = html.escape(build.label(build.build_info()))
        stamp = f"Baker {here}; its evidence and labels from 0.0.0, commit {'a' * 12} · pipeline"
        assert stamp in render_report(conn)
        assert run_pipeline.run_versions(conn)["evidence_build"] == old
    finally:
        conn.close()


# ---------------------------------------------------------------- reproducibility

# The fields core/report/html.py documents as time-dependent, masked before hashing.
TIME = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z"
MASKS = (
    (re.compile(rf"decided {TIME} in "), "decided <time> in "),  # each verdict's decision time
    (re.compile(r"run:\d{8}T\d{6}Z(?:-\d+)?"), "run:<start>"),  # run ids name their start time
    (re.compile(rf"started {TIME}\."), "started <time>."),  # the Run section
    (re.compile(rf"entries from {TIME} to {TIME}\."), "entries from <time> to <time>."),
    (re.compile(r"Last hash <span class='mono'>[0-9a-f]{64}</span>"), "Last hash <hash>"),
    (re.compile(rf"<tr><td>(\d+)</td><td>{TIME}</td>"), r"<tr><td>\1</td><td><time></td>"),
    (re.compile(rf" stipulated on {TIME}:"), " stipulated on <time>:"),  # limitations
    (re.compile(rf" confirmed on {TIME} that "), " confirmed on <time> that "),  # limitations
)


def report_hash(text: str, mask_times: bool = False) -> str:
    if mask_times:
        for pattern, repl in MASKS:
            text = pattern.sub(repl, text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def first_report(tmp_path_factory) -> str:
    conn = _build(tmp_path_factory.mktemp("repro-a") / "case01.db", START)
    try:
        return render_report(conn)
    finally:
        conn.close()


def test_same_inputs_versions_and_decisions_give_a_byte_identical_report(first_report, tmp_path):
    conn = _build(tmp_path / "case01.db", START)
    try:
        again = render_report(conn)
    finally:
        conn.close()
    assert report_hash(again) == report_hash(first_report)
    # the masks do not hide what matters: verdicts, evidence and expert decisions are present
    assert SUPPORTED_EXPERT in again and "<tr id='" in again and EXPERT in again


def test_report_made_at_other_times_differs_only_in_its_time_fields(first_report, tmp_path):
    conn = _build(tmp_path / "case01.db", START + timedelta(days=3, minutes=7))
    try:
        later = render_report(conn)
    finally:
        conn.close()
    assert report_hash(later) != report_hash(first_report)  # the times are really different
    assert report_hash(later, mask_times=True) == report_hash(first_report, mask_times=True)


def test_every_mask_matches_a_field_in_the_report(first_report):
    """A mask that matches nothing would hide a renamed field; each must still find its field."""
    for pattern, _ in MASKS:
        assert pattern.search(first_report), pattern.pattern


def test_the_screen_reads_the_case_without_writing_it(tmp_path):
    """Rendering both ways is read-only, so comparing them cannot change what they compare."""
    conn = _build(tmp_path / "case01.db", START)
    try:
        before = conn.execute("SELECT COUNT(*), MAX(seq) FROM audit_log").fetchone()
        app = App(tmp_path / "case01.db", expert="Test Expert", port=PORT)
        _screen_claims(app, conn)
        render_report(conn)
        assert conn.execute("SELECT COUNT(*), MAX(seq) FROM audit_log").fetchone() == before
    finally:
        conn.close()


def test_the_screen_and_the_report_show_an_embedded_copy_with_the_same_note(tmp_path):
    # Grok review on #103: a forwarded or quoted copy imported from inside another message gets
    # one note, rendered by record_line on the claim page and in the report alike.
    from core.ingest import forwarded

    db = tmp_path / "case01.db"
    conn = run_pipeline.build_case("case01", db)
    try:
        _audit(conn, START)
        record_id, claim_id = conn.execute(
            "SELECT e.record_id, a.claim_id FROM evidence_items e"
            " JOIN assumptions a ON a.id = e.assumption_id WHERE e.record_id LIKE 'msg:%'"
            " AND e.stance != 'irrelevant' ORDER BY e.record_id, a.claim_id LIMIT 1"
        ).fetchone()
        sid, payload = conn.execute(
            "SELECT c.source_id, c.payload_json FROM source_coverage c"
            " JOIN messages m ON m.source_id = c.source_id WHERE m.id = ?",
            (record_id,),
        ).fetchone()
        data = json.loads(payload)
        data.setdefault(forwarded.PAYLOAD_KEY, {})["embedded_copy"] = [record_id]
        with conn:
            conn.execute(
                "UPDATE source_coverage SET payload_json = ? WHERE source_id = ?",
                (json.dumps(data), sid),
            )
        found = forwarded.affected(conn)
        assert found[record_id] == "embedded_copy"
        line = record_line(conn, record_id, found)
        assert "Forwarded or quoted copy carried inside record" in line
        assert "whoever forwarded" not in line
        assert line in render_report(conn)
        app = App(db, expert="Test Expert", port=PORT)
        assert line in get(app, "/claim", id=claim_id).text
    finally:
        conn.close()

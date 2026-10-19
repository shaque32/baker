"""Opening a case checks its audit log's hash chain and fails closed when it is broken.

The chain was checked when a report was built or a case encrypted, but not when a case was
opened, so a case changed outside Baker could still be reviewed and written to. Now the review
screen and every CLI command that reviews refuse it and say why; `verify-log` and `report`
still read it, and both state the failed chain themselves. Synthetic data only.
"""

from __future__ import annotations

import io
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from cli.main import main as cli_main
from core import encryption
from core.casework import cases, protect
from core.casework.cases import Case
from core.db import connect
from core.review import audit_log
from ui.app import App, Request

PORT = 8765
HOST = {"host": f"127.0.0.1:{PORT}"}
AT = datetime(2026, 10, 15, tzinfo=UTC)
PASS = "correct horse battery staple"
EXPERT = "expert:Test Expert"


class _AnyHash(str):
    def __eq__(self, other: object) -> bool:
        return isinstance(other, str) and len(other) == 64

    __hash__ = str.__hash__


ANY_HASH = _AnyHash()


def get(app: App, path: str, **query: str):  # noqa: ANN201
    return app.handle(Request("GET", path, dict(query), dict(HOST)))


def post(app: App, path: str, **form: str):  # noqa: ANN201
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def tamper(conn: sqlite3.Connection, seq: int) -> None:
    """Change one logged entry the way an edit outside Baker would (past the append-only
    trigger)."""
    conn.execute("DROP TRIGGER audit_log_no_update")
    conn.execute(
        "UPDATE audit_log SET payload_json = ? WHERE seq = ?", ('{"edited": "outside"}', seq)
    )
    conn.commit()


def log_three(conn: sqlite3.Connection) -> None:
    for i in range(3):
        audit_log.append(conn, AT, EXPERT, "test.entry", {"n": i})
    conn.commit()


@pytest.fixture
def broken_db(tmp_path) -> Path:
    db = tmp_path / "case.db"
    assert cli_main(["init", "--db", str(db)]) == 0
    conn = connect(db)
    log_three(conn)
    tamper(conn, 2)
    conn.close()
    return db


# ---------------------------------------------------------------- the check itself


def test_first_break_names_the_first_entry_that_does_not_match(tmp_path):
    conn = connect(tmp_path / "c.db")
    conn.executescript((Path(__file__).resolve().parents[1] / "core/schema.sql").read_text())
    log_three(conn)
    assert audit_log.first_break(conn) is None and audit_log.verify_chain(conn)
    audit_log.require_intact(conn)
    tamper(conn, 2)
    assert audit_log.first_break(conn) == 2 and not audit_log.verify_chain(conn)
    with pytest.raises(audit_log.ChainBroken, match="broken at entry 2"):
        audit_log.require_intact(conn)


# ---------------------------------------------------------------- the CLI


@pytest.mark.parametrize(
    "args",
    [
        ["claims", "list"],
        ["evidence", "--id", "ev:x", "--status", "dismissed", "--reason", "r", "--by", EXPERT],
        ["verdict", "--claim", "C01", "--confirm", "--by", EXPERT],
        ["redecide", "--by", EXPERT],
        ["stipulate", "--device", "dev:item1", "--person", "Test Person", "--by", EXPERT],
    ],
)
def test_cli_review_commands_refuse_a_broken_chain_and_write_nothing(broken_db, args):
    before = broken_db.read_bytes()
    cmd, *rest = args
    with pytest.raises(SystemExit, match="hash chain is broken at entry 2"):
        cli_main([cmd, "--db", str(broken_db), *rest])
    assert broken_db.read_bytes() == before


def test_cli_report_refuses_a_broken_chain_and_verify_log_says_why(broken_db, tmp_path, capsys):
    out = tmp_path / "report.html"
    with pytest.raises(SystemExit, match="hash chain is broken at entry 2"):
        cli_main(["report", "--db", str(broken_db), "--out", str(out)])
    assert not out.exists()  # nothing exported
    assert cli_main(["verify-log", "--db", str(broken_db)]) == 1
    assert "FAILED: the audit log's hash chain is broken at entry 2" in capsys.readouterr().out


# ---------------------------------------------------------------- anchors outside the database


def cut_tail(db: Path, keep: int) -> None:
    """Remove the newest entries the way an edit outside Baker would. The chain that is left
    still verifies on its own."""
    conn = connect(db)
    conn.execute("DROP TRIGGER audit_log_no_delete")
    conn.execute("DELETE FROM audit_log WHERE seq > ?", (keep,))
    conn.commit()
    assert audit_log.verify_chain(conn)
    conn.close()


@pytest.fixture
def anchored_db(tmp_path) -> Path:
    db = tmp_path / "case.db"
    assert cli_main(["init", "--db", str(db)]) == 0
    conn = connect(db)
    log_three(conn)
    conn.close()
    assert cli_main(["claims", "--db", str(db), "list"]) == 0  # opening anchors entry 3
    return db


def test_opening_anchors_the_newest_entry_once(anchored_db):
    anchors = audit_log.anchors_path(anchored_db)
    assert anchors.name == "case.db.anchors.jsonl"
    assert cli_main(["claims", "--db", str(anchored_db), "list"]) == 0
    lines = anchors.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # the same newest entry is not anchored twice
    assert json.loads(lines[0]) == {"seq": 3, "hash": ANY_HASH}  # no times, no reasons


def test_a_log_cut_short_of_its_anchor_is_refused(anchored_db, tmp_path, capsys):
    cut_tail(anchored_db, keep=2)
    with pytest.raises(SystemExit, match="no entry 3.*removed from the end of the log"):
        cli_main(["claims", "--db", str(anchored_db), "list"])
    out = tmp_path / "report.html"
    with pytest.raises(SystemExit, match="no entry 3"):
        cli_main(["report", "--db", str(anchored_db), "--out", str(out)])
    assert not out.exists()
    assert cli_main(["verify-log", "--db", str(anchored_db)]) == 1
    assert "FAILED: the audit log has no entry 3" in capsys.readouterr().out


def test_a_log_rewritten_after_its_anchor_is_refused(anchored_db):
    cut_tail(anchored_db, keep=2)
    conn = connect(anchored_db)
    audit_log.append(conn, AT, EXPERT, "test.rewritten", {"n": 99})  # a new entry 3
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit, match="entry 3 of the audit log does not match"):
        cli_main(["claims", "--db", str(anchored_db), "list"])


def test_an_unreadable_anchor_file_is_refused(anchored_db):
    audit_log.anchors_path(anchored_db).write_text("not json\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="line 1 of the audit log's anchor file"):
        cli_main(["claims", "--db", str(anchored_db), "list"])


def test_an_anchor_file_that_is_not_text_is_refused(anchored_db):
    audit_log.anchors_path(anchored_db).write_bytes(b"\xff\xfe\x00garbage")
    with pytest.raises(SystemExit, match="anchor file case.db.anchors.jsonl cannot be read"):
        cli_main(["claims", "--db", str(anchored_db), "list"])


def test_cli_encrypt_refuses_a_blocked_case_before_asking_for_a_passphrase(anchored_db):
    cut_tail(anchored_db, keep=2)
    with pytest.raises(SystemExit, match="no entry 3"):  # not "needs a passphrase typed..."
        cli_main(["encrypt", "--db", str(anchored_db), "--by", EXPERT])
    assert not (anchored_db.parent / "case.key").exists()


def test_encrypting_a_blocked_case_writes_nothing(anchored_db):
    cut_tail(anchored_db, keep=2)
    before = anchored_db.read_bytes()
    with pytest.raises(audit_log.ChainBroken, match="no entry 3"):
        protect.encrypt_case(Case(anchored_db), PASS, EXPERT, again=PASS)
    assert not (anchored_db.parent / "case.key").exists()
    assert anchored_db.read_bytes() == before


# ---------------------------------------------------------------- the review screen


def test_screen_on_one_database_starts_but_keeps_a_broken_case_shut(broken_db):
    app = App(db_path=broken_db, port=PORT, model_check=None)
    assert app.case is None
    page = get(app, "/cases").text
    assert "Review blocked" in page and "broken at entry 2" in page
    assert get(app, "/").header("Location") == "/cases"
    assert get(app, "/claims").header("Location") == "/cases"
    post(app, "/expert", name="Test Expert")
    post(app, "/case/open")
    assert app.case is None
    assert "Not opened: the audit log" in get(app, "/cases").text


def test_screen_lists_a_broken_case_as_blocked_and_will_not_open_it(tmp_path):
    home = tmp_path / "cases"
    first = App(home=home, port=PORT, model_check=None)
    post(first, "/expert", name="Test Expert")
    post(first, "/case/new", name="Synthetic broken case")
    case = first.case
    assert case is not None
    conn = connect(case.db)
    log_three(conn)
    tamper(conn, 1)
    conn.close()

    app = App(home=home, port=PORT, model_check=None)  # a fresh screen on the same folder
    post(app, "/expert", name="Test Expert")
    listing = get(app, "/cases").text
    assert "Review blocked" in listing and "broken at entry 1" in listing
    before = case.db.read_bytes()
    post(app, "/case/open", case=case.folder.name)
    assert app.case is None
    assert "Not opened: the audit log" in get(app, "/cases").text
    assert get(app, "/claims").header("Location") == "/cases"
    assert case.db.read_bytes() == before  # opening wrote nothing (no stale-run marking)


def test_an_intact_case_still_opens(tmp_path):
    home = tmp_path / "cases"
    app = App(home=home, port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic intact case")
    case = app.case
    assert case is not None
    app.case = None
    post(app, "/case/open", case=case.folder.name)
    assert app.case == case and "Opened" in get(app, "/setup").text


def test_an_encrypted_broken_case_is_locked_again_after_the_refused_open(tmp_path):
    home = tmp_path / "cases"
    app = App(home=home, port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic sealed case", encrypt="1", passphrase=PASS,
         passphrase2=PASS)  # fmt: skip
    case = app.case
    assert case is not None and protect.state(case) == "encrypted"
    conn = connect(case.db)  # unlocked in this process
    log_three(conn)
    tamper(conn, 3)
    conn.close()
    post(app, "/case/lock")
    assert protect.is_locked(case)

    post(app, "/case/open", case=case.folder.name, passphrase=PASS)
    assert app.case is None
    assert not encryption.is_unlocked(case.db)  # its key did not stay in memory
    assert "Not opened: the audit log" in get(app, "/cases").text
    assert cases.list_cases(home) == [case]


@pytest.mark.parametrize("encrypt", [False, True])
def test_reopening_the_open_case_after_tampering_closes_it(tmp_path, encrypt):
    app = App(home=tmp_path / "cases", port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    extra = {"encrypt": "1", "passphrase": PASS, "passphrase2": PASS} if encrypt else {}
    post(app, "/case/new", name="Synthetic open case", **extra)
    case = app.case
    assert case is not None
    conn = connect(case.db)
    log_three(conn)
    tamper(conn, 2)
    conn.close()

    post(app, "/case/open", case=case.folder.name)  # the request's own check closes it
    assert app.case is None
    assert "Case closed: the audit log" in get(app, "/cases").text
    assert get(app, "/claims").header("Location") == "/cases"
    assert protect.is_locked(case) == encrypt


def test_screen_refuses_a_report_when_the_log_changed_after_opening(tmp_path):
    app = App(home=tmp_path / "cases", port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic reported case")
    case = app.case
    assert case is not None
    assert get(app, "/report").status == 200  # intact: the report builds
    conn = connect(case.db)
    log_three(conn)
    tamper(conn, 2)
    conn.close()

    for path in ("/report", "/report.html"):
        if app.case is None:
            post(app, "/case/open", case=case.folder.name)  # refused: still closed
        r = get(app, path)
        assert r.header("Location") == "/cases"
        assert app.case is None
    assert "broken at entry 2" in get(app, "/cases").text


def test_screen_blocks_a_case_whose_log_was_cut_short(tmp_path):
    home = tmp_path / "cases"
    app = App(home=home, port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic cut case")
    case = app.case
    assert case is not None
    conn = connect(case.db)
    log_three(conn)
    conn.close()
    app.case = None
    post(app, "/case/open", case=case.folder.name)  # anchors the newest entry
    assert app.case == case
    newest = connect(case.db).execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
    cut_tail(case.db, keep=newest - 1)

    fresh = App(home=home, port=PORT, model_check=None)
    post(fresh, "/expert", name="Test Expert")
    assert f"Review blocked: the audit log has no entry {newest}" in get(fresh, "/cases").text
    post(fresh, "/case/open", case=case.folder.name)
    assert fresh.case is None
    assert "removed from the end of the log" in get(fresh, "/cases").text


def test_every_page_rechecks_the_log_and_stops_a_job_on_the_case(tmp_path):
    app = App(home=tmp_path / "cases", port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic log page case")
    case = app.case
    assert case is not None
    assert "Hash chain verified" in get(app, "/log").text
    newest = connect(case.db).execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
    cut_tail(case.db, keep=newest - 1)  # the chain left still verifies on its own
    job = SimpleNamespace(running=True, db=case.db, stop=threading.Event(), kind="audit")
    app.jobs.current = job  # type: ignore[assignment]

    r = get(app, "/log")
    assert r.header("Location") == "/cases" and app.case is None
    assert job.stop.is_set()
    app.jobs.current = None
    assert f"Case closed: the audit log has no entry {newest}" in get(app, "/cases").text


def test_changing_the_passphrase_of_a_blocked_case_changes_nothing(tmp_path):
    app = App(home=tmp_path / "cases", port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic sealed blocked case", encrypt="1", passphrase=PASS,
         passphrase2=PASS)  # fmt: skip
    case = app.case
    assert case is not None
    conn = connect(case.db)
    log_three(conn)
    tamper(conn, 2)
    conn.close()
    key_before = (case.folder / "case.key").read_bytes()
    with pytest.raises(audit_log.ChainBroken, match="broken at entry 2"):
        protect.change_passphrase(case, PASS, "another long passphrase", "another long passphrase",
                                  EXPERT)  # fmt: skip
    assert (case.folder / "case.key").read_bytes() == key_before


def test_a_non_text_value_in_a_logged_row_is_a_broken_chain(broken_db):
    conn = connect(broken_db)
    conn.execute("UPDATE audit_log SET actor = ? WHERE seq = 1", (b"\x00bytes",))
    conn.commit()
    assert audit_log.first_break(conn) == 1
    conn.close()
    with pytest.raises(SystemExit, match="broken at entry 1"):
        cli_main(["claims", "--db", str(broken_db), "list"])


def test_an_upload_to_a_case_blocked_since_it_opened_is_refused(tmp_path):
    app = App(home=tmp_path / "cases", port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic upload case")
    case = app.case
    assert case is not None
    conn = connect(case.db)
    log_three(conn)
    tamper(conn, 2)
    conn.close()
    before = case.db.read_bytes()
    b = "baker-test-boundary-chain"
    body = (
        f'--{b}\r\nContent-Disposition: form-data; name="token"\r\n\r\n{app.token}\r\n'
        f'--{b}\r\nContent-Disposition: form-data; name="kind"\r\n\r\nreport\r\n'
        f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="x.xlsx"\r\n'
        "Content-Type: application/octet-stream\r\n\r\nnot a report\r\n"
        f"--{b}--\r\n"
    ).encode()
    req = Request(
        "POST", "/case/import", {}, {**HOST, "content-type": f"multipart/form-data; boundary={b}"}
    )
    r = app.handle_upload(req, io.BytesIO(body), len(body))
    assert r.header("Location") == "/cases" and app.case is None
    assert case.db.read_bytes() == before
    assert not any(case.inputs.iterdir()) if case.inputs.exists() else True
    assert "Not imported: the audit log" in get(app, "/cases").text


def test_databases_sharing_a_stem_get_their_own_anchor_files(tmp_path):
    assert audit_log.anchors_path(tmp_path / "matter.db") != audit_log.anchors_path(
        tmp_path / "matter.sqlite"
    )


def test_an_anchor_that_cannot_be_written_is_a_clear_error(anchored_db, monkeypatch):
    conn = connect(anchored_db)
    audit_log.append(conn, AT, EXPERT, "test.entry", {"n": 9})  # a new newest entry
    conn.commit()
    conn.close()

    def refuse(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise PermissionError("read-only media")

    monkeypatch.setattr("builtins.open", refuse)
    with pytest.raises(SystemExit, match="cannot write case.db.anchors.jsonl"):
        cli_main(["claims", "--db", str(anchored_db), "list"])


def test_an_anchor_number_too_large_to_read_is_refused(anchored_db):
    audit_log.anchors_path(anchored_db).write_text('{"hash": "x", "seq": 1e999}\n', "utf-8")
    with pytest.raises(SystemExit, match="line 1 of the audit log's anchor file"):
        cli_main(["claims", "--db", str(anchored_db), "list"])


def test_a_removed_audit_table_is_a_blocked_case_not_a_crash(anchored_db):
    conn = connect(anchored_db)
    conn.execute("DROP TABLE audit_log")
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit, match="the audit log cannot be read"):
        cli_main(["claims", "--db", str(anchored_db), "list"])
    app = App(db_path=anchored_db, port=PORT, model_check=None)  # the screen still starts
    assert app.case is None
    assert "Not opened: the audit log cannot be read" in (app.flash or ("", False))[0]


def test_an_anchor_file_missing_its_last_newline_gets_one_before_the_next_anchor(anchored_db):
    anchors = audit_log.anchors_path(anchored_db)
    anchors.write_text(anchors.read_text("utf-8").rstrip("\n"), "utf-8")  # a cut-off append
    conn = connect(anchored_db)
    audit_log.append(conn, AT, EXPERT, "test.entry", {"n": 9})
    conn.commit()
    conn.close()
    assert cli_main(["claims", "--db", str(anchored_db), "list"]) == 0
    assert cli_main(["claims", "--db", str(anchored_db), "list"]) == 0  # still reads cleanly
    seqs = [json.loads(x)["seq"] for x in anchors.read_text("utf-8").splitlines()]
    assert seqs == [3, 4]


def _refuse_anchor(conn, anchors):  # noqa: ANN001, ANN202
    raise audit_log.AnchorUnwritable(anchors, PermissionError("read-only media"))


def test_an_unwritable_anchor_is_found_before_stale_runs_are_changed(tmp_path, monkeypatch):
    home = tmp_path / "cases"
    app = App(home=home, port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic stale-run case")
    case = app.case
    assert case is not None
    app.case = None
    marked: list[object] = []
    monkeypatch.setattr("ui.app.pipeline.mark_stale_runs_stopped", lambda c: marked.append(c))
    monkeypatch.setattr(audit_log, "anchor", _refuse_anchor)
    post(app, "/case/open", case=case.folder.name)
    assert app.case is None and marked == []  # refused before anything was written


def test_a_new_case_that_cannot_be_anchored_leaves_the_open_case_alone(tmp_path, monkeypatch):
    home = tmp_path / "cases"
    app = App(home=home, port=PORT, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic case A")
    first = app.case
    assert first is not None
    monkeypatch.setattr(audit_log, "anchor", _refuse_anchor)
    post(app, "/case/new", name="Synthetic case B")
    assert app.case == first  # case A stays open
    assert [c.name for c in cases.list_cases(home)] == ["Synthetic case A"]  # B was not kept
    assert "the case was not made" in (app.flash or ("", False))[0]


# ---------------------------------------------------------------- the expert's typed reason

SEED_EVIDENCE = """
INSERT INTO sources VALUES ('item1','synthetic','full_extraction','logical','f',
    'x','t',NULL,NULL,'2026-01-01T00:00:00Z');
INSERT INTO govdocs VALUES ('g','item1','t','affidavit');
INSERT INTO govdoc_paragraphs VALUES ('p','g',1,1,'1',0,1,'t',0);
INSERT INTO claims VALUES ('C1','p','t','identity','accepted',NULL);
INSERT INTO assumptions VALUES ('a1','C1','identity','t','1','{}','t',1,'inferred');
INSERT INTO pipeline_runs VALUES ('run:1','2026-01-01T00:00:00Z',NULL,'stopped',
    '0.0.1','0.2.0','0.1.0','{}',NULL);
INSERT INTO model_runs VALUES ('m1','run:1','review','m','h','1',NULL,'{}',0,
    '2026-01-01T00:00:00Z');
INSERT INTO evidence_items VALUES ('e1','a1','item1','Chats!1','msg:item1:Chats!1',
    'supports','q','r','observed','m1');
"""


@pytest.fixture
def decided_db(tmp_path) -> Path:
    from core.contracts import EvidenceStatus
    from core.review import actions

    db = tmp_path / "case.db"
    assert cli_main(["init", "--db", str(db)]) == 0
    conn = connect(db)
    conn.executescript(SEED_EVIDENCE)
    conn.commit()
    actions.decide_evidence(conn, "e1", EvidenceStatus.ACCEPTED, EXPERT, "Matches the record.")
    conn.close()
    return db


def test_the_logged_decision_carries_the_experts_reason(decided_db):
    conn = connect(decided_db)
    (payload,) = conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = 'evidence.decide'"
    ).fetchone()
    conn.close()
    assert json.loads(payload)["reason"] == "Matches the record."
    assert cli_main(["claims", "--db", str(decided_db), "list"]) == 0


def test_a_reason_edited_after_it_was_logged_blocks_the_case(decided_db, capsys):
    conn = connect(decided_db)
    conn.execute("DROP TRIGGER evidence_reviews_no_update")
    conn.execute("UPDATE evidence_reviews SET reason = 'Does not match.'")
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit, match="reason for evidence decision .* was changed"):
        cli_main(["claims", "--db", str(decided_db), "list"])
    assert cli_main(["verify-log", "--db", str(decided_db)]) == 1
    assert "was changed after it was logged" in capsys.readouterr().out


def test_a_decision_logged_before_reasons_were_still_verifies(tmp_path):
    db = tmp_path / "case.db"
    assert cli_main(["init", "--db", str(db)]) == 0
    conn = connect(db)
    conn.executescript(SEED_EVIDENCE)
    conn.execute(
        "INSERT INTO evidence_reviews VALUES ('rv:e1#1','e1',1,'expert',?,'accepted',"
        "'Old reason.',NULL,NULL,'2026-01-01T00:00:00Z')",
        (EXPERT,),
    )
    old = {"evidence_id": "e1", "review_id": "rv:e1#1", "status": "accepted"}  # no reason
    audit_log.append(conn, AT, EXPERT, "evidence.decide", old)
    conn.commit()
    assert audit_log.decision_problem(conn) is None
    conn.close()
    assert cli_main(["claims", "--db", str(db), "list"]) == 0


def test_an_expert_review_added_outside_baker_blocks_the_case(decided_db):
    conn = connect(decided_db)
    conn.execute(
        "INSERT INTO evidence_reviews VALUES ('rv:e1#2','e1',2,'expert',?,'dismissed',"
        "'Planted.',NULL,NULL,'2026-01-02T00:00:00Z')",
        (EXPERT,),
    )
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit, match="expert review rv:e1#2 is in the case database but not"):
        cli_main(["claims", "--db", str(decided_db), "list"])


def test_ai_reviews_need_no_log_entry(decided_db):
    conn = connect(decided_db)
    conn.execute(
        "INSERT INTO evidence_reviews VALUES ('rv:e1#2','e1',2,'ai','ai:m','dismissed',"
        "'Model said no.','m1',NULL,'2026-01-02T00:00:00Z')"
    )
    conn.commit()
    assert audit_log.decision_problem(conn) is None
    conn.close()

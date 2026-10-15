"""Opening a case checks its audit log's hash chain and fails closed when it is broken.

The chain was checked when a report was built or a case encrypted, but not when a case was
opened, so a case changed outside Baker could still be reviewed and written to. Now the review
screen and every CLI command that reviews refuse it and say why; `verify-log` and `report`
still read it, and both state the failed chain themselves. Synthetic data only.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core import encryption
from core.casework import cases, protect
from core.db import connect
from core.review import audit_log
from ui.app import App, Request

PORT = 8765
HOST = {"host": f"127.0.0.1:{PORT}"}
AT = datetime(2026, 10, 15, tzinfo=UTC)
PASS = "correct horse battery staple"
EXPERT = "expert:Test Expert"


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


def test_cli_verify_log_and_report_still_read_it(broken_db, tmp_path, capsys):
    assert cli_main(["verify-log", "--db", str(broken_db)]) == 1
    assert "FAILED" in capsys.readouterr().out
    out = tmp_path / "report.html"
    assert cli_main(["report", "--db", str(broken_db), "--out", str(out)]) == 0
    assert "FAILED VERIFICATION" in out.read_text(encoding="utf-8")


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

    post(app, "/case/open", case=case.folder.name)
    assert app.case is None
    assert get(app, "/claims").header("Location") == "/cases"
    assert "Not opened: the audit log" in get(app, "/cases").text
    assert protect.is_locked(case) == encrypt

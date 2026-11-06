"""Backing up a case folder and restoring the backup (core/casework/backup.py): the copy opens,
its audit log and anchors verify, every row and file is the same, and an encrypted case stays
encrypted under the same passphrase. Synthetic data only."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core import encryption
from core.casework import backup, cases, protect
from core.db import CaseLocked, connect
from core.review import audit_log
from core.review.actions import ReviewError
from eval import run_pipeline
from tests.test_encryption import _dump, _import, get, post
from ui.app import App

PASS = "correct horse battery staple"
EXPERT = "expert:Test Expert"
NOW = datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 6, 12, 0, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def inputs(tmp_path_factory) -> dict[str, Path]:
    meta = run_pipeline.ensure_reports("case01")
    folder = tmp_path_factory.mktemp("originals")
    out = {s["source_id"]: run_pipeline.synthetic_dir("case01") / s["file"] for s in
           meta["sources"]}  # fmt: skip
    out["affidavit"] = run_pipeline.render_affidavit_pdf("case01", folder / "affidavit.pdf")
    return out


def _case(home: Path, inputs: dict[str, Path], passphrase: str | None) -> cases.Case:
    case = cases.create_case(home, "Synthetic backup", EXPERT, passphrase=passphrase)
    _import(case, inputs["affidavit"], "govdoc")
    _import(case, inputs["item1"], "report")
    conn = connect(case.db)
    try:
        audit_log.anchor(conn, audit_log.anchors_path(case.db))
    finally:
        conn.close()
    return case


def _files(folder: Path) -> dict[str, str]:
    """Every file but the database, by path, with its SHA-256 (the database is a snapshot, so
    its bytes may differ; its rows are compared instead)."""
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.name != cases.DB_NAME
    }


def _restore(backed: Path, home: Path) -> cases.Case:
    """Restoring is copying the backup folder back whole."""
    restored = home / "restored"
    shutil.copytree(backed, restored)
    return cases.Case(restored / cases.DB_NAME)


@pytest.mark.parametrize("passphrase", [None, PASS], ids=["plain", "encrypted"])
def test_a_backup_restores_with_every_row_file_and_the_audit_log(tmp_path, inputs, passphrase):
    case = _case(tmp_path / "cases", inputs, passphrase)
    conn = connect(case.db)
    before = _dump(conn)
    conn.close()
    files_before = _files(case.folder)

    done = backup.back_up(case, EXPERT, root=tmp_path / "backups", clock=lambda: NOW)
    assert done.folder == tmp_path / "backups" / f"{case.folder.name}-backup-20261106T120000Z"
    assert done.files == len(files_before) + 1  # the database too

    restored = _restore(done.folder, tmp_path / "elsewhere")
    if passphrase is not None:
        assert protect.state(restored) == "encrypted"
        encryption.lock(case.db)  # the same key: locking one locks both
        with pytest.raises(CaseLocked):
            connect(restored.db)
        encryption.unlock(restored.db, PASS)  # the same passphrase opens the backup
    conn = connect(restored.db)
    try:
        audit_log.require_intact(conn, audit_log.anchors_path(restored.db))
        assert _dump(conn) == before  # the backup entry is logged in the case, not the copy
    finally:
        conn.close()
    assert _files(restored.folder) == files_before
    for copy in restored.inputs.iterdir():
        assert encryption.is_encrypted_file(copy) is (passphrase is not None)

    conn = connect(case.db)
    last = conn.execute(
        "SELECT actor, action, payload_json FROM audit_log ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert last[:2] == (EXPERT, "case.backup")
    assert json.loads(last[2])["to"] == str(done.folder)


def test_a_later_case_does_not_break_an_earlier_backup(tmp_path, inputs):
    """The case goes on after the backup; the backup's own anchors still match its own log."""
    case = _case(tmp_path / "cases", inputs, None)
    first = backup.back_up(case, EXPERT, root=tmp_path / "backups", clock=lambda: NOW)
    _import(case, inputs["item2"], "report")
    conn = connect(case.db)
    audit_log.anchor(conn, audit_log.anchors_path(case.db))
    conn.close()
    second = backup.back_up(case, EXPERT, root=tmp_path / "backups", clock=lambda: LATER)
    for done in (first, second):
        copy = connect(done.folder / cases.DB_NAME)
        try:
            audit_log.require_intact(copy, audit_log.anchors_path(done.folder / cases.DB_NAME))
        finally:
            copy.close()
    assert len(list((second.folder / "inputs").iterdir())) == 3


def test_a_restore_of_only_the_older_database_is_still_blocked(tmp_path, inputs):
    """Restoring the folder whole is the rule: an old database beside newer anchors is a log
    cut short, and stays blocked."""
    case = _case(tmp_path / "cases", inputs, None)
    done = backup.back_up(case, EXPERT, root=tmp_path / "backups", clock=lambda: NOW)
    conn = connect(case.db)
    audit_log.anchor(conn, audit_log.anchors_path(case.db))  # anchors the backup entry
    conn.close()
    shutil.copy2(done.folder / cases.DB_NAME, case.db)
    conn = connect(case.db)
    try:
        with pytest.raises(audit_log.ChainBroken):
            audit_log.require_intact(conn, audit_log.anchors_path(case.db))
    finally:
        conn.close()


def test_a_backup_is_refused_where_it_cannot_be_trusted(tmp_path, inputs):
    case = _case(tmp_path / "cases", inputs, PASS)
    with pytest.raises(ReviewError, match="inside the case folder"):
        backup.back_up(case, EXPERT, root=case.folder / "b")
    encryption.lock(case.db)
    with pytest.raises(CaseLocked):
        backup.back_up(case, EXPERT, root=tmp_path / "backups")
    assert not (tmp_path / "backups").exists() or not any((tmp_path / "backups").iterdir())


def test_a_case_with_a_broken_log_is_not_backed_up(tmp_path, inputs):
    case = _case(tmp_path / "cases", inputs, None)
    with audit_log.anchors_path(case.db).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"seq": 999, "hash": "0" * 64}) + "\n")  # entries cut from the end
    with pytest.raises(ReviewError, match="does not verify"):
        backup.back_up(case, EXPERT, root=tmp_path / "backups")
    assert not (tmp_path / "backups").exists() or not any((tmp_path / "backups").iterdir())


def test_a_backup_that_does_not_verify_is_deleted(tmp_path, inputs, monkeypatch):
    case = _case(tmp_path / "cases", inputs, None)

    def broken(_case: cases.Case, dest: Path) -> None:
        raise ReviewError("the backup did not verify (test)")

    monkeypatch.setattr(backup, "_verify", broken)
    with pytest.raises(ReviewError, match="did not verify"):
        backup.back_up(case, EXPERT, root=tmp_path / "backups")
    assert list((tmp_path / "backups").iterdir()) == []


def test_the_screen_backs_up_the_open_case(tmp_path, inputs):
    app = App(home=tmp_path / "cases", port=8765, model_check=None)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic screen backup")
    case = app.case
    assert case is not None
    _import(case, inputs["item1"], "report")
    page = get(app, "/setup").text
    assert "Back up this case" in page and str(tmp_path / "backups") in page
    r = post(app, "/case/backup", to=str(tmp_path / "chosen"), next="/setup")
    assert r.status == 303
    made = list((tmp_path / "chosen").iterdir())
    assert len(made) == 1 and (made[0] / cases.DB_NAME).is_file()
    assert "Backed up Synthetic screen backup" in get(app, "/setup").text


def test_a_backup_never_removes_a_folder_another_backup_made(tmp_path, inputs, monkeypatch):
    """Two backups in the same second pick the same name: the second refuses, and the first
    one's folder stays as it is (Greptile on #230)."""
    case = _case(tmp_path / "cases", inputs, None)
    root = tmp_path / "backups"
    taken = root / f"{case.folder.name}-backup-20261106T120000Z"
    real = audit_log.require_intact

    def other_backup_wins(conn, anchors):  # noqa: ANN001, ANN202 - after the exists() check
        real(conn, anchors)
        taken.mkdir(parents=True)
        (taken / "theirs.txt").write_text("the other backup", encoding="utf-8")

    monkeypatch.setattr(backup.audit_log, "require_intact", other_backup_wins)
    with pytest.raises(ReviewError, match="already exists"):
        backup.back_up(case, EXPERT, root=root, clock=lambda: NOW)
    assert (taken / "theirs.txt").read_text(encoding="utf-8") == "the other backup"


def test_a_backup_missing_a_file_copy_is_not_kept(tmp_path, inputs, monkeypatch):
    """A file copy the snapshot names but the backup lacks (say, removed on the screen during
    the backup) fails the check, and the backup is deleted (Greptile on #230)."""
    case = _case(tmp_path / "cases", inputs, PASS)
    real = backup._skip

    def lose_one(rel: Path, c: cases.Case) -> bool:
        return real(rel, c) or (rel.parts[0] == "inputs" and rel.name == sorted(
            p.name for p in c.inputs.iterdir())[0])  # fmt: skip

    monkeypatch.setattr(backup, "_skip", lose_one)
    with pytest.raises(ReviewError, match="missing 1 of the case's file copies"):
        backup.back_up(case, EXPERT, root=tmp_path / "backups", clock=lambda: NOW)
    assert list((tmp_path / "backups").iterdir()) == []


def test_removing_a_file_finds_a_renamed_copy_its_log_does_not_name(tmp_path, inputs):
    """An import that stopped after an encrypted copy was renamed but before its log entry was
    written leaves the log naming another path; removal still finds the copy, by hash."""
    from core.casework import remove

    case = cases.create_case(tmp_path / "cases", "Synthetic removal", EXPERT, passphrase=PASS)
    got = _import(case, inputs["item1"], "report")
    moved = got.path.with_name(f"{cases.HIDDEN_PREFIX}{'0' * 24}")
    got.path.rename(moved)  # the log now names a path that is not there
    conn = connect(case.db)
    try:
        remove.remove_file(case, conn, got.source_id, EXPERT, "Wrong phone.", clock=lambda: LATER)
    finally:
        conn.close()
    assert not moved.exists() and list(case.inputs.iterdir()) == []
